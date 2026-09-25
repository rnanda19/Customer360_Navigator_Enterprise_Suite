"""
tests/bp3_complaint_escalation_prediction/test_gate_artifacts.py — Customer360 Navigator

Schema and cross-artifact consistency checks for BP3 Gates 1-5's real, already-delivered output
files, mirroring tests/bp2_customer_friction_classification/test_gate_artifacts.py's pattern
exactly (BP3 Gate 6 governance requirement). These tests validate the SHAPE and internal
consistency of whatever the gate notebooks actually wrote on the user's last real run - they do
not re-derive or assert specific model numbers (that is Gates 3/4/5's own job, checked live inside
each notebook at run time). Any gate whose artifacts don't exist yet is skipped, not failed, since
not every gate need be complete for CI to still pass on what IS done.
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
    return project_root / "notebooks" / "bp3_complaint_escalation_prediction" / "artifacts"


@pytest.fixture(scope="module")
def bp3_config(project_root):
    config_path = project_root / "configs" / "bp3_complaint_escalation_prediction.yaml"
    if not config_path.exists():
        pytest.skip("bp3_complaint_escalation_prediction.yaml not found - BP3 Gate 1 has not run yet.")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Gate 1 - target definition
# ---------------------------------------------------------------------------


def test_gate1_target_definition_present(bp3_config):
    target_def = bp3_config.get("target_definition")
    if target_def is None:
        pytest.skip("BP3 Gate 1 has not run yet (target_definition is null).")
    assert target_def["primary_target"] == "intervention_required"


def test_gate1_policy_json_records_live_tags_finding(artifacts_dir):
    policy_path = artifacts_dir / "policy.json"
    if not policy_path.exists():
        pytest.skip("BP3 Gate 1 has not run yet.")
    with open(policy_path, "r", encoding="utf-8") as f:
        policy = json.load(f)
    # The real, live-re-checked ECOA/Reg B finding Gate 1 records and Gate 4/5 later act on -
    # must never be silently dropped from the artifact.
    assert "demographic_adjacent_tags_found" in policy["live_checks"]
    assert len(policy["live_checks"]["demographic_adjacent_tags_found"]) > 0


# ---------------------------------------------------------------------------
# Gate 2 - data verification / feature engineering (row accounting)
# ---------------------------------------------------------------------------


def test_gate2_row_accounting_present_and_consistent(bp3_config):
    n_trainable = bp3_config.get("n_trainable_total")
    if n_trainable is None:
        pytest.skip("BP3 Gate 2 has not run yet.")
    n_pos = bp3_config["n_intervention_required"]
    n_neg = bp3_config["n_no_intervention_required"]
    assert n_pos + n_neg == n_trainable
    n_excluded = bp3_config["n_excluded_total"]
    assert (
        bp3_config["n_excluded_in_progress"]
        + bp3_config["n_excluded_untimely_response"]
        + bp3_config["n_excluded_null_response"]
        == n_excluded
    )


def test_gate2_no_barred_column_used_as_feature_flag_is_true(bp3_config):
    if "no_barred_column_used_as_feature" not in bp3_config:
        pytest.skip("BP3 Gate 2 has not run yet.")
    assert bp3_config["no_barred_column_used_as_feature"] is True


# ---------------------------------------------------------------------------
# Gate 3 - model benchmark
# ---------------------------------------------------------------------------


def test_gate3_cv_results_schema_and_champion(artifacts_dir, bp3_config):
    csv_path = artifacts_dir / "gate3_cv_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("BP3 Gate 3 has not run yet.")
    df = pd.read_csv(csv_path)
    expected_cols = {
        "model",
        "status",
        "elapsed_seconds",
        "mean_average_precision",
        "std_average_precision",
        "mean_roc_auc",
        "mean_recall",
        "mean_precision",
        "mean_f1",
    }
    assert expected_cols.issubset(set(df.columns))

    gate3_block = bp3_config.get("gate3_model_benchmark")
    assert gate3_block is not None, "gate3_model_benchmark missing from config despite gate3 CSV existing"
    champion = gate3_block["champion_model"]
    passing = df[df["status"] == "OK"]
    assert len(passing) >= 1, "No candidate passed in gate3_cv_benchmark_results.csv"
    best_row = passing.sort_values("mean_average_precision", ascending=False, kind="mergesort").iloc[0]
    assert best_row["model"] == champion, (
        f"Config's recorded champion '{champion}' does not match the best-scoring PASSING model in the "
        f"CSV ('{best_row['model']}') - these must agree. A failed candidate (status != 'OK') is never "
        "eligible, by construction, whatever its score."
    )


def test_gate3_failed_candidates_never_carry_a_usable_score(artifacts_dir):
    csv_path = artifacts_dir / "gate3_cv_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("BP3 Gate 3 has not run yet.")
    df = pd.read_csv(csv_path)
    failed = df[df["status"] != "OK"]
    if failed.empty:
        pytest.skip("No failed candidates on this run - nothing to check.")
    assert not (failed["mean_average_precision"].notna()).any(), (
        "A failed candidate row has a non-null mean_average_precision - a failed candidate must "
        "never carry a usable score."
    )


def test_gate3_champion_selection_metric_is_pr_auc_not_accuracy(bp3_config):
    # BP3's own standing rule (Master Plan's explicit class-imbalance methodology clause): never
    # accuracy. Structural check that the recorded champion block never introduces one.
    gate3_block = bp3_config.get("gate3_model_benchmark")
    if gate3_block is None:
        pytest.skip("BP3 Gate 3 has not run yet.")
    assert "held_out_test_accuracy" not in gate3_block
    assert "cv_mean_average_precision" in gate3_block


# ---------------------------------------------------------------------------
# Gate 4 - statistical validation
# ---------------------------------------------------------------------------


def test_gate4_statistical_validation_schema(artifacts_dir, bp3_config):
    json_path = artifacts_dir / "gate4_statistical_validation.json"
    if not json_path.exists():
        pytest.skip("BP3 Gate 4 has not run yet.")
    with open(json_path, "r", encoding="utf-8") as f:
        gate4 = json.load(f)

    required_keys = {
        "champion_model",
        "runner_up_model",
        "champion_fold_average_precision",
        "runner_up_fold_average_precision",
        "held_out_test_pr_auc_point_estimate",
        "held_out_test_pr_auc_bootstrap_ci_95",
        "held_out_test_roc_auc_bootstrap_ci_95",
        "brier_score",
        "adverse_impact_ratio_tags",
    }
    assert required_keys.issubset(gate4.keys())
    assert len(gate4["champion_fold_average_precision"]) == len(gate4["runner_up_fold_average_precision"])
    ci_low, ci_high = gate4["held_out_test_pr_auc_bootstrap_ci_95"]
    assert ci_low <= ci_high

    gate3_block = bp3_config.get("gate3_model_benchmark")
    if gate3_block is not None:
        assert (
            gate4["champion_model"] == gate3_block["champion_model"]
        ), "Gate 4's recorded champion does not match Gate 3's - these must agree."


def test_gate4_disparate_impact_check_present_and_bounded(artifacts_dir):
    # BP3-specific (ECOA/Reg B) - not present in BP1/BP2 Gate 4's schema. A ratio must be a
    # fraction in [0, 1] whenever it was computed at all.
    json_path = artifacts_dir / "gate4_statistical_validation.json"
    if not json_path.exists():
        pytest.skip("BP3 Gate 4 has not run yet.")
    with open(json_path, "r", encoding="utf-8") as f:
        gate4 = json.load(f)
    ratio = gate4.get("adverse_impact_ratio_tags")
    if ratio is None:
        pytest.skip("adverse_impact_ratio_tags is null on this run.")
    assert 0.0 <= ratio <= 1.0


# ---------------------------------------------------------------------------
# Gate 5 - decision layer
# ---------------------------------------------------------------------------


def test_gate5_decision_records_schema_and_row_count(artifacts_dir):
    csv_path = artifacts_dir / "gate5_decision_records.csv"
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not csv_path.exists() or not summary_path.exists():
        pytest.skip("BP3 Gate 5 has not run yet.")

    df = pd.read_csv(csv_path)
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    expected_cols = {
        "row_index",
        "true_label",
        "predicted_label",
        "predicted_probability",
        "correct",
        "predicted_label_at_best_f1_threshold",
        "tags_group",
        "in_shap_sample",
        "reason_codes",
        "feature_summary",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) == summary["n_decision_records"]
    assert df["in_shap_sample"].sum() == summary["n_with_reason_codes"]
    assert df["predicted_probability"].between(0.0, 1.0).all()
    assert set(df["predicted_label"].unique()).issubset({0, 1})

    # Every row marked outside the SHAP sample must never carry reason codes - the grounding
    # boundary this project enforces for every BP.
    out_of_sample = df[~df["in_shap_sample"]]
    assert (
        out_of_sample["reason_codes"].fillna("") == ""
    ).all(), "A row marked outside the SHAP sample has non-empty reason_codes - grounding boundary violated."


def test_gate5_recomputed_pr_auc_matches_gate3_recorded(artifacts_dir, bp3_config):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP3 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    gate3_block = bp3_config.get("gate3_model_benchmark")
    if gate3_block is None:
        pytest.skip("BP3 Gate 3 config block missing - cannot cross-check.")
    diff = abs(summary["held_out_test_pr_auc_recomputed"] - gate3_block["held_out_test_pr_auc"])
    assert diff < 1e-2, (
        f"Gate 5's recomputed PR-AUC ({summary['held_out_test_pr_auc_recomputed']}) drifted from "
        f"Gate 3's recorded PR-AUC ({gate3_block['held_out_test_pr_auc']}) by more than the "
        "rounding-only tolerance expected between config and JSON precision."
    )


def test_gate5_disparate_impact_recompute_matches_gate4_recorded(artifacts_dir):
    # The real cross-check this gate's own code performs at run time - re-verified here from the
    # written artifact so a future silent drift (e.g. someone editing Gate 5's Tags logic without
    # re-running it) would be caught by CI, not just by the notebook's own inline assertion.
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP3 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    dic = summary.get("disparate_impact_check")
    if dic is None or dic.get("adverse_impact_ratio_recomputed") is None:
        pytest.skip("disparate_impact_check not present or null on this run.")
    if dic.get("gate4_recorded_adverse_impact_ratio") is None:
        pytest.skip("No Gate 4 recorded value to cross-check against on this run.")
    diff = abs(dic["adverse_impact_ratio_recomputed"] - dic["gate4_recorded_adverse_impact_ratio"])
    assert diff < 1e-2


def test_gate5_compliance_touchpoint_documents_no_genai(artifacts_dir):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP3 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert "compliance_touchpoint" in summary
    assert summary["compliance_touchpoint"]["genai_api_used"] is False


# ---------------------------------------------------------------------------
# Cross-gate model inventory consistency
# ---------------------------------------------------------------------------


def test_model_inventory_entry_accumulates_all_completed_gates(artifacts_dir):
    inventory_path = artifacts_dir / "model_inventory_entry.json"
    if not inventory_path.exists():
        pytest.skip("No BP3 gate has written model_inventory_entry.json yet.")
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    assert inventory["bp_id"] == "bp3"
    assert "model_name" in inventory
    # If gate5 fields are present, gate3/gate4 fields must be too (gates run in order - a gate5
    # entry with no gate3/gate4 history would mean the inventory was corrupted or hand-edited).
    if "gate5_n_decision_records" in inventory:
        assert "cv_mean_average_precision" in inventory, "gate5 fields present without gate3's own fields"
        assert (
            "gate4_adverse_impact_ratio_tags" in inventory
        ), "gate5 fields present without gate4's own fields"


def test_no_barred_column_ever_appears_in_recorded_feature_columns(artifacts_dir):
    inventory_path = artifacts_dir / "model_inventory_entry.json"
    if not inventory_path.exists():
        pytest.skip("No BP3 gate has written model_inventory_entry.json yet.")
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    if "feature_columns" not in inventory or "barred_columns" not in inventory:
        pytest.skip("model_inventory_entry.json does not yet record feature/barred columns.")
    assert set(inventory["feature_columns"]) & set(inventory["barred_columns"]) == set()
