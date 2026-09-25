"""
tests/bp4_customer_journey_analytics/test_gate_artifacts.py — Customer360 Navigator

Schema and cross-artifact consistency checks for BP4 Gates 1-6's real, already-delivered output
files, mirroring tests/bp3_complaint_escalation_prediction/test_gate_artifacts.py's pattern
(BP4 Gate 6 governance requirement). These tests validate the SHAPE and internal consistency of
whatever the gate notebooks actually wrote on the user's last real run - they do not re-derive or
assert specific numbers (that is each gate's own job, checked live inside its own notebook at run
time). Any gate whose artifacts don't exist yet is skipped, not failed, since not every gate need
be complete for CI to still pass on what IS done.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
import yaml

from utils.performance_setup import resolve_project_root


@pytest.fixture(scope="module")
def project_root():
    try:
        return resolve_project_root()
    except RuntimeError:
        pytest.skip("Not running inside the Customer360 Navigator project tree - set C360_PROJECT_ROOT.")


@pytest.fixture(scope="module")
def artifacts_dir(project_root):
    return project_root / "notebooks" / "bp4_customer_journey_analytics" / "artifacts"


@pytest.fixture(scope="module")
def bp4_config(project_root):
    config_path = project_root / "configs" / "bp4_customer_journey_analytics.yaml"
    if not config_path.exists():
        pytest.skip("bp4_customer_journey_analytics.yaml not found - BP4 Gate 1 has not run yet.")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Gate 1 - business understanding & policy
# ---------------------------------------------------------------------------


def test_gate1_journey_definition_present(bp4_config):
    journey_def = bp4_config.get("journey_definition")
    if journey_def is None:
        pytest.skip("BP4 Gate 1 has not run yet (journey_definition is null).")
    assert journey_def["no_customer_identifier_in_scope"] is True


def test_gate1_policy_json_records_compliance_touchpoint(artifacts_dir):
    policy_path = artifacts_dir / "policy.json"
    if not policy_path.exists():
        pytest.skip("BP4 Gate 1 has not run yet.")
    with open(policy_path, "r", encoding="utf-8") as f:
        policy = json.load(f)
    assert "compliance_touchpoint" in policy
    assert "statement" in policy["compliance_touchpoint"]


def test_gate1_barred_journey_columns_never_in_scope_boundaries_as_a_grouping_key(bp4_config):
    scope_boundaries = bp4_config.get("scope_boundaries")
    if scope_boundaries is None:
        pytest.skip("BP4 Gate 1 has not run yet.")
    joined = " ".join(scope_boundaries)
    assert "'Tags' barred" in joined or "Tags' is barred" in joined


# ---------------------------------------------------------------------------
# Gate 2 - data verification / taxonomy engineering (row accounting)
# ---------------------------------------------------------------------------


def test_gate2_journey_row_count_matches_raw(bp4_config):
    if bp4_config.get("journey_row_count") is None:
        pytest.skip("BP4 Gate 2 has not run yet.")
    assert bp4_config["journey_row_count_matches_raw"] is True


def test_gate2_no_barred_column_used_as_feature_flag_is_true(bp4_config):
    if "no_barred_column_used_as_feature" not in bp4_config:
        pytest.skip("BP4 Gate 2 has not run yet.")
    assert bp4_config["no_barred_column_used_as_feature"] is True


def test_gate2_cluster_count_matches_gate1(bp4_config):
    if "cluster_count_matches_gate1" not in bp4_config:
        pytest.skip("BP4 Gate 2 has not run yet.")
    assert bp4_config["cluster_count_matches_gate1"] is True


# ---------------------------------------------------------------------------
# Gate 3 - aggregation-pipeline benchmark & champion selection
# ---------------------------------------------------------------------------


def test_gate3_benchmark_results_schema_and_champion(artifacts_dir, bp4_config):
    csv_path = artifacts_dir / "gate3_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("BP4 Gate 3 has not run yet.")
    df = pd.read_csv(csv_path)
    # Real schema (confirmed against the delivered gate3_benchmark_results.csv): a "status" column
    # holding the literal string "CORRECT" for a passing candidate (never a boolean "correct"
    # column), plus its own "is_champion" boolean flag.
    expected_cols = {"candidate", "status", "min_seconds", "mean_seconds", "is_champion"}
    assert expected_cols.issubset(set(df.columns))

    champion = bp4_config.get("champion_pipeline")
    assert champion is not None, "champion_pipeline missing from config despite gate3 CSV existing"
    passing = df[df["status"] == "CORRECT"]
    assert len(passing) >= 1, "No candidate passed in gate3_benchmark_results.csv"
    best_row = passing.sort_values("min_seconds", ascending=True, kind="mergesort").iloc[0]
    assert best_row["candidate"] == champion, (
        f"Config's recorded champion_pipeline '{champion}' does not match the fastest real "
        f"CORRECT candidate in the CSV ('{best_row['candidate']}') - these must agree. An "
        "incorrect candidate is never eligible, by construction, whatever its speed."
    )
    champion_flagged_rows = df[df["is_champion"] == True]  # noqa: E712
    assert len(champion_flagged_rows) == 1, "Exactly one candidate row must carry is_champion=True."
    assert (
        champion_flagged_rows.iloc[0]["candidate"] == champion
    ), "The row flagged is_champion=True must be the same candidate as config's champion_pipeline."


def test_gate3_incorrect_candidates_never_carry_a_usable_timing(artifacts_dir):
    csv_path = artifacts_dir / "gate3_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("BP4 Gate 3 has not run yet.")
    df = pd.read_csv(csv_path)
    incorrect = df[df["status"] != "CORRECT"]
    if incorrect.empty:
        pytest.skip("No incorrect/unavailable candidates on this run - nothing to check.")
    assert not (incorrect["min_seconds"].notna()).any(), (
        "An incorrect/unavailable candidate row has a non-null min_seconds - a candidate that "
        "failed correctness must never carry a usable timing."
    )
    assert not (incorrect["is_champion"] == True).any(), (  # noqa: E712
        "An incorrect/unavailable candidate row is flagged is_champion=True - impossible by " "construction."
    )


def test_gate3_champion_selection_never_uses_a_predictive_metric(bp4_config):
    # BP4-specific structural check: Gate 3 benchmarks real execution engines, not classifiers -
    # there must be no accuracy/F1/PR-AUC-style key anywhere near the champion record.
    if bp4_config.get("champion_pipeline") is None:
        pytest.skip("BP4 Gate 3 has not run yet.")
    forbidden_keys = {"accuracy", "f1", "pr_auc", "roc_auc", "recall", "precision"}
    assert not (forbidden_keys & set(bp4_config.keys()))


# ---------------------------------------------------------------------------
# Gate 4 - statistical validation
# ---------------------------------------------------------------------------


def test_gate4_bootstrap_cis_schema_and_bounds(bp4_config):
    mean_lag = bp4_config.get("mean_response_lag_days")
    if mean_lag is None:
        pytest.skip("BP4 Gate 4 has not run yet.")
    for key in ("mean_response_lag_days", "recurring_cluster_rate", "mean_cluster_size"):
        ci = bp4_config[key]
        assert {"point_estimate", "ci_95_low", "ci_95_high"}.issubset(ci.keys())
        assert ci["ci_95_low"] <= ci["point_estimate"] <= ci["ci_95_high"]


def test_gate4_ecoa_touchpoint_stated_not_applicable(bp4_config):
    if bp4_config.get("ecoa_disparate_impact_applicability") is None:
        pytest.skip("BP4 Gate 4 has not run yet.")
    assert bp4_config["ecoa_disparate_impact_applicability"] == "NOT_APPLICABLE"
    assert bp4_config["no_barred_column_in_cluster_key"] is True


def test_gate4_reproducibility_confirmed(bp4_config):
    if "reproducibility_confirmed" not in bp4_config:
        pytest.skip("BP4 Gate 4 has not run yet.")
    assert bp4_config["reproducibility_confirmed"] is True


def test_gate4_performance_report_champion_matches_gate3(bp4_config):
    perf = bp4_config.get("performance_report")
    if perf is None:
        pytest.skip("BP4 Gate 4 has not run yet.")
    gate3_champion = bp4_config.get("champion_pipeline")
    if gate3_champion is None:
        pytest.skip("BP4 Gate 3 config missing - cannot cross-check.")
    assert perf["champion_pipeline"] == gate3_champion


# ---------------------------------------------------------------------------
# Gate 5 - decision layer & reporting
# ---------------------------------------------------------------------------


def test_gate5_cluster_decision_report_schema_and_row_count(artifacts_dir, bp4_config):
    csv_path = artifacts_dir / "gate5_cluster_decision_report.csv"
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not csv_path.exists() or not summary_path.exists():
        pytest.skip("BP4 Gate 5 has not run yet.")

    df = pd.read_csv(csv_path, low_memory=False)
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    expected_cols = {
        "n_complaints_total",
        "recurring_flag",
        "elevated_lag_flag",
        "high_volume_flag",
        "review_priority_score",
        "review_priority_tier",
        "reason_codes",
        "reason_evidence",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) == summary["n_clusters"]
    assert set(df["review_priority_tier"].unique()).issubset({"HIGH", "MEDIUM", "LOW", "NONE"})
    assert df["review_priority_score"].between(0, 3).all()

    n_clusters = bp4_config.get("n_clusters")
    if n_clusters is not None:
        assert len(df) == n_clusters


def test_gate5_row_coverage_matches_gate1_journey_row_count(artifacts_dir, bp4_config):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP4 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    journey_row_count = bp4_config.get("journey_row_count")
    if journey_row_count is None:
        pytest.skip("BP4 Gate 2 config missing - cannot cross-check.")
    assert summary["total_rows_covered_check"] == journey_row_count
    assert summary["total_rows_covered_matches_gate1"] is True


def test_gate5_compliance_touchpoint_documents_no_genai(artifacts_dir):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP4 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert "compliance_touchpoint" in summary
    assert summary["compliance_touchpoint"]["genai_api_used"] is False
    assert "bp7_decision_engine_boundary" in summary["compliance_touchpoint"]


def test_gate5_elevated_lag_reference_matches_gate4_recorded_point_estimate(artifacts_dir, bp4_config):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP4 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    gate4_mean_lag = bp4_config.get("mean_response_lag_days")
    if gate4_mean_lag is None:
        pytest.skip("BP4 Gate 4 config missing - cannot cross-check.")
    diff = abs(summary["gate4_population_mean_lag_reference"] - gate4_mean_lag["point_estimate"])
    assert diff < 1e-9, (
        "Gate 5's reused Gate 4 mean-lag reference drifted from Gate 4's own recorded point "
        f"estimate (diff={diff}) - these must be read from the identical live source."
    )


# ---------------------------------------------------------------------------
# Cross-gate: no barred column ever leaks into any journey-grouping key
# ---------------------------------------------------------------------------


def test_no_barred_column_ever_appears_in_cluster_key(bp4_config):
    from features.bp4_journey_features import BARRED_JOURNEY_COLUMNS, CLUSTER_KEY

    assert set(CLUSTER_KEY) & set(BARRED_JOURNEY_COLUMNS) == set()
    if bp4_config.get("no_barred_column_in_cluster_key") is not None:
        assert bp4_config["no_barred_column_in_cluster_key"] is True
