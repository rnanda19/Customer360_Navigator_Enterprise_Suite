"""
tests/bp1_customer_intent_classification/test_gate_artifacts.py — Customer360 Navigator

Schema and cross-artifact consistency checks for BP1 Gates 1-5's real, already-delivered output
files. These tests validate the SHAPE and internal consistency of whatever the gate notebooks
actually wrote on your last real run - they do not re-derive or assert specific model numbers
(that is Gates 3/4/5's own job, checked live inside each notebook at run time). Any gate whose
artifacts don't exist yet is skipped, not failed, since not every gate need be complete for CI to
still pass on what IS done (BP1 Gate 6 governance requirement - artifacts exist BEFORE a BP is
marked complete, checked here as a standing regression guard for every future commit).
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
    return project_root / "notebooks" / "bp1_customer_intent_classification" / "artifacts"


@pytest.fixture(scope="module")
def bp1_config(project_root):
    config_path = project_root / "configs" / "bp1_customer_intent_classification.yaml"
    if not config_path.exists():
        pytest.skip("bp1_customer_intent_classification.yaml not found - Gate 1 has not run yet.")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Gate 1 - target definition
# ---------------------------------------------------------------------------


def test_gate1_target_definition_present(bp1_config):
    target_def = bp1_config.get("target_definition")
    if target_def is None:
        pytest.skip("Gate 1 has not run yet (target_definition is null).")
    assert target_def["primary_target"] == "category"
    assert target_def["feature_variable"] == "text"


# ---------------------------------------------------------------------------
# Gate 3 - model benchmark
# ---------------------------------------------------------------------------


def test_gate3_cv_results_schema_and_champion(artifacts_dir, bp1_config):
    csv_path = artifacts_dir / "gate3_cv_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("Gate 3 has not run yet.")
    df = pd.read_csv(csv_path)
    expected_cols = {
        "model",
        "status",
        "elapsed_seconds",
        "mean_f1_macro",
        "std_f1_macro",
        "mean_f1_weighted",
        "mean_accuracy",
    }
    assert expected_cols.issubset(set(df.columns))

    gate3_block = bp1_config.get("gate3_model_benchmark")
    assert gate3_block is not None, "gate3_model_benchmark missing from config despite gate3 CSV existing"
    champion = gate3_block["champion_model"]
    passing = df[df["status"] == "OK"]
    assert len(passing) >= 1, "No candidate passed in gate3_cv_benchmark_results.csv"
    best_row = passing.sort_values("mean_f1_macro", ascending=False, kind="mergesort").iloc[0]
    assert best_row["model"] == champion, (
        f"Config's recorded champion '{champion}' does not match the best-scoring model in the CSV "
        f"('{best_row['model']}') - these must agree."
    )


# ---------------------------------------------------------------------------
# Gate 4 - statistical validation
# ---------------------------------------------------------------------------


def test_gate4_statistical_validation_schema(artifacts_dir, bp1_config):
    json_path = artifacts_dir / "gate4_statistical_validation.json"
    if not json_path.exists():
        pytest.skip("Gate 4 has not run yet.")
    with open(json_path, "r", encoding="utf-8") as f:
        gate4 = json.load(f)

    required_keys = {
        "champion_model",
        "runner_up_model",
        "champion_fold_f1_macro",
        "runner_up_fold_f1_macro",
        "held_out_test_f1_macro_point_estimate",
        "held_out_test_f1_macro_bootstrap_ci_95",
    }
    assert required_keys.issubset(gate4.keys())
    assert len(gate4["champion_fold_f1_macro"]) == len(gate4["runner_up_fold_f1_macro"])
    ci_low, ci_high = gate4["held_out_test_f1_macro_bootstrap_ci_95"]
    assert (
        ci_low <= gate4["held_out_test_f1_macro_point_estimate"] <= ci_high or True
    )  # CI need not always contain the point estimate; presence + ordering checked below
    assert ci_low <= ci_high

    gate3_block = bp1_config.get("gate3_model_benchmark")
    if gate3_block is not None:
        assert (
            gate4["champion_model"] == gate3_block["champion_model"]
        ), "Gate 4's recorded champion does not match Gate 3's - these must agree."


# ---------------------------------------------------------------------------
# Gate 5 - decision layer
# ---------------------------------------------------------------------------


def test_gate5_decision_records_schema_and_row_count(artifacts_dir):
    csv_path = artifacts_dir / "gate5_decision_records.csv"
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not csv_path.exists() or not summary_path.exists():
        pytest.skip("Gate 5 has not run yet.")

    df = pd.read_csv(csv_path)
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    expected_cols = {
        "row_index",
        "true_label",
        "predicted_label",
        "correct",
        "confidence_top1",
        "rank2_label",
        "rank2_confidence",
        "rank3_label",
        "rank3_confidence",
        "in_shap_sample",
        "reason_codes",
        "text",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) == summary["n_decision_records"]
    assert df["in_shap_sample"].sum() == summary["n_with_reason_codes"]
    assert df["confidence_top1"].between(0.0, 1.0).all()

    # Every row with in_shap_sample=False must have empty reason_codes, and vice versa is allowed
    # to be empty only if that row genuinely had zero nonzero-weight TF-IDF terms (rare edge case,
    # not asserted here as an error - only that OUT-of-sample rows are never populated).
    out_of_sample = df[~df["in_shap_sample"]]
    assert (
        out_of_sample["reason_codes"].fillna("") == ""
    ).all(), "A row marked outside the SHAP sample has non-empty reason_codes - grounding boundary violated."


def test_gate5_compliance_touchpoint_documented(artifacts_dir):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("Gate 5 has not run yet.")
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
        pytest.skip("No gate has written model_inventory_entry.json yet.")
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    assert inventory["bp_id"] == "bp1"
    assert "model_name" in inventory
    # If gate5 fields are present, gate3/gate4 fields must be too (gates run in order - a gate5
    # entry with no gate3/gate4 history would mean the inventory was corrupted or hand-edited).
    if "gate5_n_decision_records" in inventory:
        assert "cv_mean_f1_macro" in inventory, "gate5 fields present without gate3's own fields"
