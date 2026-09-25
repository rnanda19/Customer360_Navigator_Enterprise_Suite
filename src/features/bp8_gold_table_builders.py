"""
src/features/bp8_gold_table_builders.py — Customer360 Navigator

Shared BP8 (Executive & Product Analytics) Gold-table-build module. Built AT Gate 2
(Data Verification & Gold-Table Aggregation) for BP8, the cross-BP Gold-layer aggregation
and Power BI reporting layer described in BP8's own policy.json: "BP8 is a cross-BP
Gold-layer aggregation and Power BI reporting layer, never a ninth modeling problem - no
target, no classifier, no GenAI call." Every function in this module builds a Gold/semantic
table purely by rolling up fields that an upstream BP1-BP7 gate already computed and
governed; none of them recompute an upstream BP's own classification/severity/tier logic,
and none of them read raw CFPB/BANKING77 row-level narrative text or a demographic-adjacent
field (`Tags`, `ZIP code`) as an output dimension.

This module is import-only shared logic (HYPER). It performs no I/O side effects at import
time and is never executed by Claude - only the user runs it, in their own environment (via
the BP8 Gate 2 orchestrator notebook that imports it), per the project's execution-boundary
rule.

Two disclosed corrections vs BP8 Gate 1 are implemented here and must not be silently
re-broken by a future edit:

1. review_priority_tier source-table correction. BP8 Gate 1's own policy.json
   (kpi_category_scope.product_opportunity_flags.source_table) names
   `cfpb_issue_cluster_summary_gold.parquet` as the source of `review_priority_tier`. That
   parquet's real columns (verified live at Gate 2) are: Company, Product, Sub-product,
   Issue, Sub-issue, n_complaints_total, first_complaint_date, last_complaint_date,
   n_active_months, avg_response_lag_days, banking77_coverage_fraction,
   is_recurring_cluster — there is no `review_priority_tier` column in it. The real source
   of `review_priority_tier` is BP4's own decision-artifact index,
   `models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet`, which is
   joinable to the same table at the same grain, (Company, Product, Sub-product, Issue,
   Sub-issue). `build_product_opportunity_flags_gold()` below reads from that file, not
   from `cfpb_issue_cluster_summary_gold.parquet`.

2. check_gate6_reached() multi-signal correction. BP8 Gate 1's own live-check computed
   gate6_reached as `bool(status) and "gate6" in status.lower()`. That is correct for
   bp1-bp4 (their real status strings do gain a "gate6" substring once Gate6 completes),
   but it is structurally blind to bp5/bp6/bp7, whose real status strings never grow a
   "gate6" substring even after their real Gate6 completes — Gate6 deliberately never
   writes to `status:` for bp6/bp7, and bp5's Gate6 likewise never appends to `status:`.
   `check_gate6_reached()` below adds two more real, independent signals (a flat
   `gate6_generated_at_utc` key, and a nested per-bp gate6 dict carrying its own
   `generated_at_utc` field) so bp5/bp6/bp7's real, current Gate6 status is read correctly
   instead of being permanently under-reported.

Public functions:
  check_gate6_reached(bp_id, config) -> bool
  build_friction_trends_gold(friction_gold_path) -> pl.DataFrame
  build_escalation_trends_gold(escalation_gold_path) -> pl.DataFrame
  build_product_opportunity_flags_gold(bp4_decision_artifact_index_path) -> pl.DataFrame
  build_customer_intent_taxonomy_trends_gold(cfpb_taxonomy_gold_path) -> pl.DataFrame
  build_customer_intent_banking77_categories_gold(banking77_gold_path) -> pl.DataFrame
  build_root_cause_outcome_trends_gold(root_cause_gold_path) -> pl.DataFrame
  build_root_cause_field_driver_ranking_gold(gate5_report_outcome_1_path,
      gate5_report_outcome_2_path) -> pl.DataFrame
  gold_table_manifest(tables_written) -> dict
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

UPSTREAM_BPS: list[dict[str, str]] = [
    {"bp_id": "bp1", "bp_name": "bp1_customer_intent_classification"},
    {"bp_id": "bp2", "bp_name": "bp2_customer_friction_classification"},
    {"bp_id": "bp3", "bp_name": "bp3_complaint_escalation_prediction"},
    {"bp_id": "bp4", "bp_name": "bp4_customer_journey_analytics"},
    {"bp_id": "bp5", "bp_name": "bp5_root_cause_driver_analytics"},
    {"bp_id": "bp6", "bp_name": "bp6_genai_resolution_assistant"},
    {"bp_id": "bp7", "bp_name": "bp7_customer_navigator_decision_engine"},
]

# Real config keys used by the nested-dict Gate6 signal (see check_gate6_reached docstring).
_NESTED_GATE6_KEYS: dict[str, str] = {
    "bp1": "gate6_governance",
    "bp6": "gate6_productization_monitoring_governance",
}

# Real CFPB date format, matching BP4's own real precedent ("3/29/2024" style, M/D/YYYY,
# not necessarily zero-padded).
_CFPB_DATE_FORMAT = "%m/%d/%Y"
UNPARSEABLE_DATE_SENTINEL = "UNPARSEABLE_DATE"
UNSPECIFIED_TIER_SENTINEL = "UNSPECIFIED"
EXCLUDED_UNKNOWN_SENTINEL = "EXCLUDED_UNKNOWN"


def check_gate6_reached(bp_id: str, config: dict[str, Any]) -> bool:
    """Multi-signal Gate6-completion check, correcting BP8 Gate1's own status-substring-only
    check (bool(status) and "gate6" in status.lower()), which is structurally blind to
    BP5/BP6/BP7's real config convention: none of their `status:` fields ever grow a "gate6"
    substring, even after their real Gate6 completes, because Gate6 deliberately never writes
    to `status:` for bp6/bp7, and bp5's Gate6 likewise never appends to `status:`. This
    function checks three independent real signals, any one of which is sufficient:
      1. status substring (works for bp1-bp4, kept for backward compatibility / cheap common
         case)
      2. a flat top-level `gate6_generated_at_utc` key on the config dict (bp5's and bp7's
         real config convention for Gate6's own output)
      3. a nested dict at a bp-specific gate6 key with its own `generated_at_utc` field
         inside it (bp1's `gate6_governance` and bp6's
         `gate6_productization_monitoring_governance` real config convention)
    """
    status = str(config.get("status") or "").lower()
    if "gate6" in status:
        return True
    if config.get("gate6_generated_at_utc"):
        return True
    nested_key = _NESTED_GATE6_KEYS.get(bp_id)
    if nested_key:
        nested = config.get(nested_key)
        if isinstance(nested, dict) and nested.get("generated_at_utc"):
            return True
    return False


def _complaint_month_expr(date_col: str = "Date received") -> pl.Expr:
    """Parse the real `Date received` string column (M/D/YYYY, e.g. "3/29/2024") into a
    "%Y-%m" complaint_month string, with any real parse failure bucketed into the explicit
    UNPARSEABLE_DATE_SENTINEL rather than silently dropped (this project's standing Gate 2
    "zero nulls silently dropped" exit criterion)."""
    parsed = pl.col(date_col).str.strptime(pl.Date, _CFPB_DATE_FORMAT, strict=False)
    return (
        pl.when(parsed.is_not_null())
        .then(parsed.dt.strftime("%Y-%m"))
        .otherwise(pl.lit(UNPARSEABLE_DATE_SENTINEL))
        .alias("complaint_month")
    )


def _three_way_status_expr(intervention_col: str, exclusion_col: str, alias: str) -> pl.Expr:
    """Derive a 3-way status string from a real float intervention/outcome column (1.0 / 0.0 /
    null) plus its paired exclusion-reason string column, used identically by
    build_escalation_trends_gold and (for outcome_1) build_root_cause_outcome_trends_gold."""
    return (
        pl.when(pl.col(intervention_col) == 1.0)
        .then(pl.lit("INTERVENTION_REQUIRED"))
        .when(pl.col(intervention_col) == 0.0)
        .then(pl.lit("NO_INTERVENTION_REQUIRED"))
        .when(pl.col(exclusion_col).is_not_null())
        .then("EXCLUDED_" + pl.col(exclusion_col).str.to_uppercase())
        .otherwise(pl.lit(EXCLUDED_UNKNOWN_SENTINEL))
        .alias(alias)
    )


def build_friction_trends_gold(friction_gold_path: Path) -> pl.DataFrame:
    """Grain (complaint_month, Product, friction_severity_class) -> n_complaints, built from
    the real BP2 Gold table `cfpb_friction_severity_gold.parquet`. BP8 never recomputes
    friction_severity_class here; it only rolls up what BP2's own gates already computed."""
    lf = pl.scan_parquet(friction_gold_path)
    result = (
        lf.with_columns(_complaint_month_expr())
        .group_by(["complaint_month", "Product", "friction_severity_class"])
        .agg(pl.len().alias("n_complaints"))
        .sort(["complaint_month", "Product", "friction_severity_class"])
    )
    return result.collect()


def build_escalation_trends_gold(escalation_gold_path: Path) -> pl.DataFrame:
    """Grain (complaint_month, Product, intervention_status) -> n_complaints, built from the
    real BP3 Gold table `cfpb_intervention_escalation_gold.parquet`. `intervention_status` is
    derived from the real float `intervention_required` column: 1.0 -> INTERVENTION_REQUIRED,
    0.0 -> NO_INTERVENTION_REQUIRED, null -> EXCLUDED_<exclusion_reason> (or EXCLUDED_UNKNOWN
    when exclusion_reason is also null). BP8 never recomputes intervention_required itself."""
    lf = pl.scan_parquet(escalation_gold_path)
    result = (
        lf.with_columns(
            _complaint_month_expr(),
            _three_way_status_expr(
                "intervention_required", "exclusion_reason", "intervention_status"
            ),
        )
        .group_by(["complaint_month", "Product", "intervention_status"])
        .agg(pl.len().alias("n_complaints"))
        .sort(["complaint_month", "Product", "intervention_status"])
    )
    return result.collect()


def build_product_opportunity_flags_gold(bp4_decision_artifact_index_path: Path) -> pl.DataFrame:
    """Near-direct select/rename pass-through of
    `models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet`.

    Disclosed correction vs BP8 Gate 1: Gate1's own policy.json named
    `cfpb_issue_cluster_summary_gold.parquet` (kpi_category_scope.product_opportunity_flags.
    source_table) as the source of `review_priority_tier`. That file has no
    `review_priority_tier` column. This function correctly reads `review_priority_tier` (and
    the other product-opportunity fields) from `bp4_decision_artifact_index.parquet` instead,
    which is joinable to every other BP4/BP8 table at the same grain,
    (Company, Product, Sub-product, Issue, Sub-issue).

    A blank/null `review_priority_tier` is bucketed into the explicit UNSPECIFIED_TIER_SENTINEL
    rather than dropped, since a small number of rows are known to carry a blank tier."""
    lf = pl.scan_parquet(bp4_decision_artifact_index_path)
    cols = [
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
    result = (
        lf.select(cols)
        .with_columns(
            pl.when(
                pl.col("review_priority_tier").is_null()
                | (pl.col("review_priority_tier").cast(pl.Utf8).str.strip_chars() == "")
            )
            .then(pl.lit(UNSPECIFIED_TIER_SENTINEL))
            .otherwise(pl.col("review_priority_tier").cast(pl.Utf8))
            .alias("review_priority_tier")
        )
        .sort(["Company", "Product", "Sub-product", "Issue", "Sub-issue"])
    )
    return result.collect()


def build_customer_intent_taxonomy_trends_gold(cfpb_taxonomy_gold_path: Path) -> pl.DataFrame:
    """Grain (complaint_month, Product, common_taxonomy_bucket) -> n_complaints, built from the
    real BP1 Gold table `cfpb_common_taxonomy_gold.parquet`."""
    lf = pl.scan_parquet(cfpb_taxonomy_gold_path)
    result = (
        lf.with_columns(_complaint_month_expr())
        .group_by(["complaint_month", "Product", "common_taxonomy_bucket"])
        .agg(pl.len().alias("n_complaints"))
        .sort(["complaint_month", "Product", "common_taxonomy_bucket"])
    )
    return result.collect()


def build_customer_intent_banking77_categories_gold(banking77_gold_path: Path) -> pl.DataFrame:
    """Grain (category, common_taxonomy_bucket, split) -> n_examples, built from the real BP1
    Gold table `banking77_common_taxonomy_gold.parquet`."""
    lf = pl.scan_parquet(banking77_gold_path)
    result = (
        lf.group_by(["category", "common_taxonomy_bucket", "split"])
        .agg(pl.len().alias("n_examples"))
        .sort(["category", "common_taxonomy_bucket", "split"])
    )
    return result.collect()


def build_root_cause_outcome_trends_gold(root_cause_gold_path: Path) -> pl.DataFrame:
    """Grain (complaint_month, Product, outcome_1_status, outcome_2_status) -> n_complaints,
    built from the real BP5 Gold table `cfpb_root_cause_driver_gold.parquet`. `outcome_1_status`
    uses the same 3-way sentinel scheme as build_escalation_trends_gold, driven by the real
    `outcome_1_intervention_required` / `outcome_1_exclusion_reason` columns. `outcome_2_status`
    is derived from the real int `outcome_2_timely_response_failure` column (no nulls in the
    real data): 1 -> TIMELY_RESPONSE_FAILURE, 0 -> TIMELY_RESPONSE_OK."""
    lf = pl.scan_parquet(root_cause_gold_path)
    outcome_2_expr = (
        pl.when(pl.col("outcome_2_timely_response_failure") == 1)
        .then(pl.lit("TIMELY_RESPONSE_FAILURE"))
        .otherwise(pl.lit("TIMELY_RESPONSE_OK"))
        .alias("outcome_2_status")
    )
    result = (
        lf.with_columns(
            _complaint_month_expr(),
            _three_way_status_expr(
                "outcome_1_intervention_required",
                "outcome_1_exclusion_reason",
                "outcome_1_status",
            ),
            outcome_2_expr,
        )
        .group_by(["complaint_month", "Product", "outcome_1_status", "outcome_2_status"])
        .agg(pl.len().alias("n_complaints"))
        .sort(["complaint_month", "Product", "outcome_1_status", "outcome_2_status"])
    )
    return result.collect()


def build_root_cause_field_driver_ranking_gold(
    gate5_report_outcome_1_path: Path, gate5_report_outcome_2_path: Path
) -> pl.DataFrame:
    """Flatten BP5's real Gate5 `field_level_ranking` arrays (one JSON file per outcome) into a
    single Gold table, tagged with an added `outcome_field` column. Reads however many rows are
    really present in each file's `field_level_ranking` list (never hardcodes a row count); the
    `citation` sub-dict on each real entry is intentionally dropped rather than flattened."""
    fields = [
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
    sources = [
        ("outcome_1_intervention_required", gate5_report_outcome_1_path),
        ("outcome_2_timely_response_failure", gate5_report_outcome_2_path),
    ]
    # Explicit schema so an empty `field_level_ranking` list (never observed in real Gate5
    # output for either outcome, but not structurally impossible) still yields a DataFrame with
    # the real 9 columns rather than polars' zero-column empty-schema inference - otherwise
    # `pl.concat` below would fail (or silently drop a real outcome's rows) the one time a real
    # outcome's ranking list is genuinely empty. A defensive schema fix, not a fabricated value -
    # every row still comes straight from the real on-disk JSON.
    row_schema = {
        "rank": pl.Int64,
        "driver_field": pl.Utf8,
        "cramers_v": pl.Float64,
        "association_strength": pl.Utf8,
        "chi2_statistic": pl.Float64,
        "degrees_of_freedom": pl.Int64,
        "p_value": pl.Float64,
        "n_rows_tested": pl.Int64,
        "n_distinct_levels": pl.Int64,
    }
    frames: list[pl.DataFrame] = []
    for outcome_name, path in sources:
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
        rankings = report["field_level_ranking"]
        rows = []
        for entry in rankings:
            row: dict[str, Any] = {field: entry.get(field) for field in fields}
            row["outcome_field"] = outcome_name
            rows.append(row)
        frames.append(pl.DataFrame(rows, schema={**row_schema, "outcome_field": pl.Utf8}, orient="row"))
    combined = pl.concat(frames, how="vertical_relaxed")
    ordered_cols = ["outcome_field"] + fields
    return combined.select(ordered_cols).sort(["outcome_field", "rank"])


def gold_table_manifest(tables_written: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble the `gold_tables_written` portion of the Gate 2 manifest from a list of
    {category, filename, path, n_rows, columns} dicts already built by the orchestrator
    notebook after each table was written. Performs no I/O of its own."""
    return {
        "gold_tables_written": tables_written,
        "gold_tables_written_count": len(tables_written),
        "total_rows_written": sum(int(t.get("n_rows", 0)) for t in tables_written),
    }
