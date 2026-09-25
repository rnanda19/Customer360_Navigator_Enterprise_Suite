"""
tests/bp8_executive_product_analytics/test_bp8_gold_tables.py — Customer360 Navigator

Pytest coverage for BP8's two real src/ modules:
  - src/features/bp8_gold_table_builders.py   (Gate 2 Gold-table builders)
  - src/features/bp8_gate3_decision_engine_kpi_builders.py (Gate 3 decision-engine KPI builders)

BP8 has no FastAPI service (explicit, standing project scope decision: "Packaging + CI/tests
only, no service") so, unlike BP1-BP7's own test suites, there is no service smoke test here.
This file is BP8's real test coverage, matching this project's standing "full test coverage is
the standing standard" rule (tests/bp8_executive_product_analytics/README.md).

Every fixture below is a small, synthetic Parquet/CSV/JSON file built fresh per test with
tmp_path - never real CFPB/BANKING77-scale data, and this suite never reads anything from the
real device project. Each real function's docstring-documented, real column contract is used
verbatim so a schema drift in the real source module would break a test here, not silently pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from features import bp8_gate3_decision_engine_kpi_builders as kpi
from features import bp8_gold_table_builders as gt

# ---------------------------------------------------------------------------------------------
# check_gate6_reached
# ---------------------------------------------------------------------------------------------


class TestCheckGate6Reached:
    def test_status_substring_true_for_bp1_style_status(self):
        assert gt.check_gate6_reached("bp4", {"status": "gate1_confirmed_gate6_complete"}) is True

    def test_status_substring_false_when_absent_and_no_other_signal(self):
        assert gt.check_gate6_reached("bp5", {"status": "gate1_confirmed"}) is False

    def test_flat_gate6_generated_at_utc_signal_true_for_bp5_bp7_style(self):
        config = {"status": "gate1_confirmed", "gate6_generated_at_utc": "2026-09-24T11:15:03Z"}
        assert gt.check_gate6_reached("bp5", config) is True

    def test_nested_dict_signal_true_for_bp1_gate6_governance(self):
        config = {
            "status": "gate1_confirmed",
            "gate6_governance": {"generated_at_utc": "2026-09-24T00:00:00Z"},
        }
        assert gt.check_gate6_reached("bp1", config) is True

    def test_nested_dict_signal_true_for_bp6_productization_monitoring_governance(self):
        config = {
            "status": "gate1_confirmed",
            "gate6_productization_monitoring_governance": {"generated_at_utc": "2026-09-24T16:45:52Z"},
        }
        assert gt.check_gate6_reached("bp6", config) is True

    def test_nested_dict_present_but_no_generated_at_utc_is_false(self):
        config = {"status": "gate1_confirmed", "gate6_governance": {"other_key": "value"}}
        assert gt.check_gate6_reached("bp1", config) is False

    def test_bp_without_a_nested_key_mapping_only_uses_flat_and_substring_signals(self):
        # bp3 has no entry in _NESTED_GATE6_KEYS - a bp3-only nested dict must never be checked.
        config = {
            "status": "gate1_confirmed",
            "gate6_governance": {"generated_at_utc": "2026-01-01T00:00:00Z"},
        }
        assert gt.check_gate6_reached("bp3", config) is False

    def test_empty_config_is_false(self):
        assert gt.check_gate6_reached("bp1", {}) is False


# ---------------------------------------------------------------------------------------------
# build_friction_trends_gold
# ---------------------------------------------------------------------------------------------


def _write_parquet(path: Path, rows: list[dict]) -> None:
    pl.DataFrame(rows).write_parquet(path)


class TestBuildFrictionTrendsGold:
    def test_groups_and_counts_by_month_product_severity(self, tmp_path):
        src = tmp_path / "cfpb_friction_severity_gold.parquet"
        _write_parquet(
            src,
            [
                {"Date received": "3/29/2024", "Product": "Credit card", "friction_severity_class": "HIGH"},
                {"Date received": "3/1/2024", "Product": "Credit card", "friction_severity_class": "HIGH"},
                {"Date received": "3/15/2024", "Product": "Credit card", "friction_severity_class": "LOW"},
                {"Date received": "4/2/2024", "Product": "Mortgage", "friction_severity_class": "HIGH"},
            ],
        )
        result = gt.build_friction_trends_gold(src)
        assert result.columns == ["complaint_month", "Product", "friction_severity_class", "n_complaints"]
        row = result.filter(
            (pl.col("complaint_month") == "2024-03")
            & (pl.col("Product") == "Credit card")
            & (pl.col("friction_severity_class") == "HIGH")
        )
        assert row["n_complaints"][0] == 2
        assert result.height == 3

    def test_unparseable_date_is_bucketed_into_sentinel_not_dropped(self, tmp_path):
        src = tmp_path / "friction.parquet"
        _write_parquet(
            src,
            [
                {"Date received": "not-a-date", "Product": "Credit card", "friction_severity_class": "HIGH"},
                {"Date received": "3/29/2024", "Product": "Credit card", "friction_severity_class": "HIGH"},
            ],
        )
        result = gt.build_friction_trends_gold(src)
        assert gt.UNPARSEABLE_DATE_SENTINEL in result["complaint_month"].to_list()
        # Zero rows silently dropped - both input rows are represented in the output.
        assert result["n_complaints"].sum() == 2

    def test_empty_input_returns_empty_frame_with_correct_schema(self, tmp_path):
        src = tmp_path / "empty_friction.parquet"
        pl.DataFrame(
            schema={"Date received": pl.Utf8, "Product": pl.Utf8, "friction_severity_class": pl.Utf8}
        ).write_parquet(src)
        result = gt.build_friction_trends_gold(src)
        assert result.columns == ["complaint_month", "Product", "friction_severity_class", "n_complaints"]
        assert result.height == 0


# ---------------------------------------------------------------------------------------------
# build_escalation_trends_gold
# ---------------------------------------------------------------------------------------------


class TestBuildEscalationTrendsGold:
    def test_three_way_status_derivation(self, tmp_path):
        src = tmp_path / "cfpb_intervention_escalation_gold.parquet"
        _write_parquet(
            src,
            [
                {
                    "Date received": "3/29/2024",
                    "Product": "Credit card",
                    "intervention_required": 1.0,
                    "exclusion_reason": None,
                },
                {
                    "Date received": "3/29/2024",
                    "Product": "Credit card",
                    "intervention_required": 0.0,
                    "exclusion_reason": None,
                },
                {
                    "Date received": "3/29/2024",
                    "Product": "Credit card",
                    "intervention_required": None,
                    "exclusion_reason": "no_response",
                },
                {
                    "Date received": "3/29/2024",
                    "Product": "Credit card",
                    "intervention_required": None,
                    "exclusion_reason": None,
                },
            ],
        )
        result = gt.build_escalation_trends_gold(src)
        statuses = set(result["intervention_status"].to_list())
        assert statuses == {
            "INTERVENTION_REQUIRED",
            "NO_INTERVENTION_REQUIRED",
            "EXCLUDED_NO_RESPONSE",
            gt.EXCLUDED_UNKNOWN_SENTINEL,
        }
        assert result["n_complaints"].sum() == 4


# ---------------------------------------------------------------------------------------------
# build_product_opportunity_flags_gold
# ---------------------------------------------------------------------------------------------


class TestBuildProductOpportunityFlagsGold:
    COLS = [
        "Company",
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "n_complaints_total",
        "first_complaint_date",
        "last_complaint_date",
        "review_priority_score",
        "review_priority_tier",
        "reason_codes",
        "recurring_flag",
        "elevated_lag_flag",
        "high_volume_flag",
    ]

    def _row(self, **overrides) -> dict:
        base = {
            "Company": "Acme Bank",
            "Product": "Credit card",
            "Sub-product": "General",
            "Issue": "Billing",
            "Sub-issue": "Fee dispute",
            "n_complaints_total": 10,
            "first_complaint_date": "1/1/2024",
            "last_complaint_date": "3/1/2024",
            "review_priority_score": 0.5,
            "review_priority_tier": "HIGH",
            "reason_codes": "r1,r2",
            "recurring_flag": True,
            "elevated_lag_flag": False,
            "high_volume_flag": True,
        }
        base.update(overrides)
        return base

    def test_blank_and_null_tier_bucketed_to_unspecified_sentinel(self, tmp_path):
        src = tmp_path / "bp4_decision_artifact_index.parquet"
        _write_parquet(
            src,
            [
                self._row(Company="B Bank", review_priority_tier=""),
                self._row(Company="C Bank", review_priority_tier=None),
                self._row(Company="A Bank", review_priority_tier="HIGH"),
            ],
        )
        result = gt.build_product_opportunity_flags_gold(src)
        assert set(result.columns) == set(self.COLS)
        tiers = dict(zip(result["Company"].to_list(), result["review_priority_tier"].to_list()))
        assert tiers["B Bank"] == gt.UNSPECIFIED_TIER_SENTINEL
        assert tiers["C Bank"] == gt.UNSPECIFIED_TIER_SENTINEL
        assert tiers["A Bank"] == "HIGH"

    def test_sorted_by_grain_columns(self, tmp_path):
        src = tmp_path / "bp4_decision_artifact_index.parquet"
        _write_parquet(
            src,
            [
                self._row(Company="Z Bank"),
                self._row(Company="A Bank"),
                self._row(Company="M Bank"),
            ],
        )
        result = gt.build_product_opportunity_flags_gold(src)
        assert result["Company"].to_list() == ["A Bank", "M Bank", "Z Bank"]


# ---------------------------------------------------------------------------------------------
# build_customer_intent_taxonomy_trends_gold / build_customer_intent_banking77_categories_gold
# ---------------------------------------------------------------------------------------------


class TestBuildCustomerIntentGold:
    def test_taxonomy_trends_grouping(self, tmp_path):
        src = tmp_path / "cfpb_common_taxonomy_gold.parquet"
        _write_parquet(
            src,
            [
                {"Date received": "3/1/2024", "Product": "Credit card", "common_taxonomy_bucket": "DISPUTE"},
                {"Date received": "3/2/2024", "Product": "Credit card", "common_taxonomy_bucket": "DISPUTE"},
                {"Date received": "4/1/2024", "Product": "Mortgage", "common_taxonomy_bucket": "SERVICE"},
            ],
        )
        result = gt.build_customer_intent_taxonomy_trends_gold(src)
        assert result.columns == ["complaint_month", "Product", "common_taxonomy_bucket", "n_complaints"]
        assert result.filter(pl.col("common_taxonomy_bucket") == "DISPUTE")["n_complaints"][0] == 2

    def test_banking77_categories_grouping(self, tmp_path):
        src = tmp_path / "banking77_common_taxonomy_gold.parquet"
        _write_parquet(
            src,
            [
                {"category": "card_arrival", "common_taxonomy_bucket": "CARD", "split": "train"},
                {"category": "card_arrival", "common_taxonomy_bucket": "CARD", "split": "train"},
                {"category": "card_arrival", "common_taxonomy_bucket": "CARD", "split": "test"},
            ],
        )
        result = gt.build_customer_intent_banking77_categories_gold(src)
        assert result.columns == ["category", "common_taxonomy_bucket", "split", "n_examples"]
        train_row = result.filter(pl.col("split") == "train")
        assert train_row["n_examples"][0] == 2


# ---------------------------------------------------------------------------------------------
# build_root_cause_outcome_trends_gold
# ---------------------------------------------------------------------------------------------


class TestBuildRootCauseOutcomeTrendsGold:
    def test_combined_three_way_and_two_way_status(self, tmp_path):
        src = tmp_path / "cfpb_root_cause_driver_gold.parquet"
        _write_parquet(
            src,
            [
                {
                    "Date received": "3/29/2024",
                    "Product": "Credit card",
                    "outcome_1_intervention_required": 1.0,
                    "outcome_1_exclusion_reason": None,
                    "outcome_2_timely_response_failure": 1,
                },
                {
                    "Date received": "3/29/2024",
                    "Product": "Credit card",
                    "outcome_1_intervention_required": 0.0,
                    "outcome_1_exclusion_reason": None,
                    "outcome_2_timely_response_failure": 0,
                },
            ],
        )
        result = gt.build_root_cause_outcome_trends_gold(src)
        assert result.columns == [
            "complaint_month",
            "Product",
            "outcome_1_status",
            "outcome_2_status",
            "n_complaints",
        ]
        statuses = set(zip(result["outcome_1_status"].to_list(), result["outcome_2_status"].to_list()))
        assert statuses == {
            ("INTERVENTION_REQUIRED", "TIMELY_RESPONSE_FAILURE"),
            ("NO_INTERVENTION_REQUIRED", "TIMELY_RESPONSE_OK"),
        }


# ---------------------------------------------------------------------------------------------
# build_root_cause_field_driver_ranking_gold
# ---------------------------------------------------------------------------------------------


class TestBuildRootCauseFieldDriverRankingGold:
    FIELDS = [
        "rank",
        "driver_field",
        "cramers_v",
        "association_strength",
        "chi2_statistic",
        "degrees_of_freedom",
        "p_value",
        "n_rows_tested",
        "n_distinct_levels",
    ]

    def _entry(self, rank: int, driver_field: str) -> dict:
        return {
            "rank": rank,
            "driver_field": driver_field,
            "cramers_v": 0.1 * rank,
            "association_strength": "weak",
            "chi2_statistic": 12.3,
            "degrees_of_freedom": 3,
            "p_value": 0.01,
            "n_rows_tested": 1000,
            "n_distinct_levels": 5,
            "citation": {"source": "internal"},  # deliberately dropped by the real function
        }

    def test_flattens_two_outcome_reports_tags_outcome_field_and_drops_citation(self, tmp_path):
        report_1 = {
            "outcome_field": "outcome_1_intervention_required",
            "field_level_ranking": [self._entry(2, "Product"), self._entry(1, "Company")],
        }
        report_2 = {
            "outcome_field": "outcome_2_timely_response_failure",
            "field_level_ranking": [self._entry(1, "Issue")],
        }
        p1 = tmp_path / "gate5_report_outcome_1.json"
        p2 = tmp_path / "gate5_report_outcome_2.json"
        p1.write_text(json.dumps(report_1), encoding="utf-8")
        p2.write_text(json.dumps(report_2), encoding="utf-8")

        result = gt.build_root_cause_field_driver_ranking_gold(p1, p2)
        assert result.columns == ["outcome_field"] + self.FIELDS
        assert "citation" not in result.columns
        assert result.height == 3
        # Sorted by (outcome_field, rank) - outcome_1's rank 1 (Company) before rank 2 (Product).
        outcome_1_rows = result.filter(pl.col("outcome_field") == "outcome_1_intervention_required")
        assert outcome_1_rows["driver_field"].to_list() == ["Company", "Product"]

    def test_reads_however_many_rows_are_really_present(self, tmp_path):
        # Both real BP5 outcomes always carry at least one ranked driver in production - this
        # exercises two DIFFERENT non-zero counts (never a hardcoded row count assumption).
        # The separate empty-field_level_ranking edge case (one outcome with zero ranked
        # drivers - not a real BP5 production shape, but not structurally impossible either) is
        # covered by test_handles_empty_field_level_ranking_for_one_outcome below - an explicit
        # schema fix in src/features/bp8_gold_table_builders.py resolved a real zero-column
        # empty-DataFrame concat failure that used to trip here.
        report_1 = {
            "outcome_field": "outcome_1_intervention_required",
            "field_level_ranking": [self._entry(1, "Company")],
        }
        report_2 = {
            "outcome_field": "outcome_2_timely_response_failure",
            "field_level_ranking": [self._entry(i, f"field_{i}") for i in range(1, 6)],
        }
        p1 = tmp_path / "r1.json"
        p2 = tmp_path / "r2.json"
        p1.write_text(json.dumps(report_1), encoding="utf-8")
        p2.write_text(json.dumps(report_2), encoding="utf-8")
        result = gt.build_root_cause_field_driver_ranking_gold(p1, p2)
        assert result.height == 6

    def test_handles_empty_field_level_ranking_for_one_outcome(self, tmp_path):
        # Real edge case fixed in src/features/bp8_gold_table_builders.py: one outcome's
        # field_level_ranking is genuinely empty (zero ranked drivers). Before the fix, an
        # empty `rows` list made pl.DataFrame(rows) infer a zero-column schema, and
        # pl.concat(..., how="vertical_relaxed") against the other outcome's real 10-column
        # frame raised. The fix gives every frame an explicit schema so this concat always
        # succeeds, honestly returning only the non-empty outcome's real rows.
        report_1 = {
            "outcome_field": "outcome_1_intervention_required",
            "field_level_ranking": [],
        }
        report_2 = {
            "outcome_field": "outcome_2_timely_response_failure",
            "field_level_ranking": [self._entry(1, "Company")],
        }
        p1 = tmp_path / "r1.json"
        p2 = tmp_path / "r2.json"
        p1.write_text(json.dumps(report_1), encoding="utf-8")
        p2.write_text(json.dumps(report_2), encoding="utf-8")
        result = gt.build_root_cause_field_driver_ranking_gold(p1, p2)
        assert result.columns == ["outcome_field"] + self.FIELDS
        assert result.height == 1
        assert result["outcome_field"].to_list() == ["outcome_2_timely_response_failure"]
        assert result["driver_field"].to_list() == ["Company"]


# ---------------------------------------------------------------------------------------------
# gold_table_manifest (Gate 2 assembly-only manifest helper)
# ---------------------------------------------------------------------------------------------


class TestGoldTableManifest:
    def test_assembles_counts_and_total_rows(self):
        tables = [
            {"category": "friction_trends", "filename": "a.parquet", "n_rows": 700},
            {"category": "escalation_trends", "filename": "b.parquet", "n_rows": 521},
        ]
        manifest = gt.gold_table_manifest(tables)
        assert manifest["gold_tables_written_count"] == 2
        assert manifest["total_rows_written"] == 1221
        assert manifest["gold_tables_written"] == tables

    def test_empty_list_is_a_clean_zero_not_a_crash(self):
        manifest = gt.gold_table_manifest([])
        assert manifest["gold_tables_written_count"] == 0
        assert manifest["total_rows_written"] == 0


# =================================================================================================
# BP8 Gate 3 — src/features/bp8_gate3_decision_engine_kpi_builders.py
# =================================================================================================


class TestBuildDecisionEngineActionBreakdownGold:
    def test_casts_and_passes_through_bp7_gate5_values_unchanged(self, tmp_path):
        csv_path = tmp_path / "gate5_recommended_action_breakdown.csv"
        csv_path.write_text(
            "recommended_action,n_rows,mean_priority_score,intervention_flag_rate,pct_of_population\n"
            "STANDARD_QUEUE,242834,0.31,0.12,0.2316\n"
            "PRIORITY_QUEUE_REVIEW,16786,0.61,0.55,0.016\n"
            "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER,788955,0.72,0.81,0.7524\n",
            encoding="utf-8",
        )
        result = kpi.build_decision_engine_action_breakdown_gold(csv_path)
        assert result.columns == [
            "recommended_action",
            "n_rows",
            "mean_priority_score",
            "intervention_flag_rate",
            "pct_of_population",
        ]
        assert result.height == 3
        standard = result.filter(pl.col("recommended_action") == "STANDARD_QUEUE")
        assert standard["n_rows"][0] == 242834
        assert standard["n_rows"].dtype == pl.Int64
        assert standard["mean_priority_score"].dtype == pl.Float64


class TestBuildDecisionEngineTierCrosstabGold:
    def test_blank_tier_bucketed_to_shared_unspecified_sentinel(self, tmp_path):
        csv_path = tmp_path / "gate5_bp4_tier_intervention_crosstab.csv"
        csv_path.write_text(
            "bp4_review_priority_tier,intervention_flag,n_rows\n" "HIGH,True,100\n" ",True,5\n" ",False,3\n",
            encoding="utf-8",
        )
        result = kpi.build_decision_engine_tier_crosstab_gold(csv_path)
        # The sentinel is imported, not redefined, in the Gate 3 module - same value as Gate 2's.
        assert kpi.UNSPECIFIED_TIER_SENTINEL == gt.UNSPECIFIED_TIER_SENTINEL
        tiers = result["bp4_review_priority_tier"].to_list()
        assert tiers.count(gt.UNSPECIFIED_TIER_SENTINEL) == 2
        assert result["intervention_flag"].dtype == pl.Boolean
        assert result["n_rows"].dtype == pl.Int64

    def test_whitespace_only_tier_is_also_bucketed(self, tmp_path):
        csv_path = tmp_path / "crosstab.csv"
        csv_path.write_text(
            "bp4_review_priority_tier,intervention_flag,n_rows\n   ,True,1\n", encoding="utf-8"
        )
        result = kpi.build_decision_engine_tier_crosstab_gold(csv_path)
        assert result["bp4_review_priority_tier"][0] == gt.UNSPECIFIED_TIER_SENTINEL


class TestBuildDecisionEngineDisparateImpactGold:
    def test_comma_containing_value_is_correctly_csv_parsed_not_split(self, tmp_path):
        csv_path = tmp_path / "gate5_disparate_impact_breakdown.csv"
        csv_path.write_text(
            "tags_group,n_rows,n_intervention_flagged,selection_rate\n"
            '"Older American, Servicemember",500,50,0.1\n'
            "None,900000,90000,0.1\n",
            encoding="utf-8",
        )
        result = kpi.build_decision_engine_disparate_impact_gold(csv_path)
        assert result.height == 2
        groups = result["tags_group"].to_list()
        assert "Older American, Servicemember" in groups
        row = result.filter(pl.col("tags_group") == "Older American, Servicemember")
        assert row["n_rows"][0] == 500
        assert row["selection_rate"][0] == 0.1


class TestBuildDecisionEngineSummaryGold:
    def test_reads_every_field_by_key_and_ignores_unused_extra_keys(self, tmp_path):
        report = {
            "bp_id": "bp7",
            "gate": 5,
            "generated_at_utc": "2026-09-25T06:49:02.757522+00:00",
            "live_row_count": 1048575,
            "champion_rule_scheme": "weighted_sum",
            "champion_weights_normalized": {"bp2": 0.33, "bp3": 0.33, "bp4": 0.34},
            "intervention_threshold": 0.5,
            "champion_stats": {
                "coverage_pct": 0.99,
                "intervention_flag_rate": 0.75,
                "bp3_agreement_rate": 0.88,
                "avg_reason_codes_per_row": 2.1,
            },
            "contribution_decomposition_summary": {
                "mean_contribution_bp2": 0.3,
                "mean_contribution_bp3": 0.4,
                "mean_contribution_bp4": 0.3,
                "max_abs_reconstruction_error": 1e-9,
            },
            "disparate_impact_audit": {
                "adverse_impact_ratio": 0.85,
                "flagged_four_fifths_rule": False,
                "lowest_selection_rate_group": "GroupA",
                "highest_selection_rate_group": "GroupB",
            },
            # Real extra keys the function must not assume are the only keys present.
            "weight_rederivation_cross_check": {"ok": True},
            "cross_checks_vs_gate3_gate4": {},
            "gate4_bootstrap_ci_carried_forward": {},
            "upstream_field_coverage": {},
            "compliance_touchpoint": "reviewed",
        }
        json_path = tmp_path / "gate5_decision_layer_summary.json"
        json_path.write_text(json.dumps(report), encoding="utf-8")

        result = kpi.build_decision_engine_summary_gold(json_path)
        assert result.height == 1
        row = result.to_dicts()[0]
        assert row["bp_id"] == "bp7"
        assert row["champion_weight_bp2"] == 0.33
        assert row["coverage_pct"] == 0.99
        assert row["mean_contribution_bp2"] == 0.3
        assert row["adverse_impact_ratio"] == 0.85
        assert row["flagged_four_fifths_rule"] is False
        assert "weight_rederivation_cross_check" not in result.columns

    def test_missing_required_nested_key_raises_keyerror_not_silently_defaulted(self, tmp_path):
        # Zero-fabrication contract: a genuinely missing real field must raise, never default to
        # a fabricated placeholder value.
        report = {"bp_id": "bp7", "champion_weights_normalized": {"bp2": 0.33}}
        json_path = tmp_path / "incomplete.json"
        json_path.write_text(json.dumps(report), encoding="utf-8")
        with pytest.raises(KeyError):
            kpi.build_decision_engine_summary_gold(json_path)


class TestGate3Manifest:
    def test_assembles_tables_written_and_count(self):
        tables = [{"category": "decision_engine_kpis__summary", "filename": "s.parquet"}]
        manifest = kpi.gate3_manifest(tables)
        assert manifest == {"gold_tables_written": tables, "n_gold_tables_written": 1}

    def test_empty_list_is_a_clean_zero(self):
        assert kpi.gate3_manifest([]) == {"gold_tables_written": [], "n_gold_tables_written": 0}
