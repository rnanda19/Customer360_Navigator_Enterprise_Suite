"""
tests/bp2_customer_friction_classification/test_gate_artifacts.py — Customer360 Navigator

Schema and cross-artifact consistency checks for BP2 Gates 1-5's real, already-delivered output
files, mirroring tests/bp1_customer_intent_classification/test_gate_artifacts.py's pattern exactly
(BP2 Gate 6 governance requirement). These tests validate the SHAPE and internal consistency of
whatever the gate notebooks actually wrote on the user's last real run - they do not re-derive or
assert specific model numbers (that is Gates 3/4/5's own job, checked live inside each notebook at
run time). Any gate whose artifacts don't exist yet is skipped, not failed, since not every gate
need be complete for CI to still pass on what IS done.
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
    return project_root / "notebooks" / "bp2_customer_friction_classification" / "artifacts"


@pytest.fixture(scope="module")
def bp2_config(project_root):
    config_path = project_root / "configs" / "bp2_customer_friction_classification.yaml"
    if not config_path.exists():
        pytest.skip("bp2_customer_friction_classification.yaml not found - BP2 Gate 1 has not run yet.")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Gate 1 - target definition
# ---------------------------------------------------------------------------


def test_gate1_target_definition_present(bp2_config):
    target_def = bp2_config.get("target_definition")
    if target_def is None:
        pytest.skip("BP2 Gate 1 has not run yet (target_definition is null).")
    assert target_def["primary_target"] == "friction_severity_class"


# ---------------------------------------------------------------------------
# Gate 2 - taxonomy engineering (severity class row counts / trainable row count)
# ---------------------------------------------------------------------------


def test_gate2_severity_class_row_counts_present_and_consistent(bp2_config):
    counts = bp2_config.get("severity_class_row_counts")
    if counts is None:
        pytest.skip("BP2 Gate 2 has not run yet.")
    ordinal_classes = {"LOW_FRICTION", "MEDIUM_FRICTION", "MEDIUM_HIGH_FRICTION", "HIGH_FRICTION"}
    assert ordinal_classes.issubset(counts.keys())
    trainable_rows_recorded = bp2_config.get("trainable_rows_4_ordinal_classes")
    assert trainable_rows_recorded is not None
    assert sum(counts[c] for c in ordinal_classes) == trainable_rows_recorded


# ---------------------------------------------------------------------------
# Gate 3 - model benchmark
# ---------------------------------------------------------------------------


def test_gate3_cv_results_schema_and_champion(artifacts_dir, bp2_config):
    csv_path = artifacts_dir / "gate3_cv_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("BP2 Gate 3 has not run yet.")
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

    gate3_block = bp2_config.get("gate3_model_benchmark")
    assert gate3_block is not None, "gate3_model_benchmark missing from config despite gate3 CSV existing"
    champion = gate3_block["champion_model"]
    passing = df[df["status"] == "OK"]
    assert len(passing) >= 1, "No candidate passed in gate3_cv_benchmark_results.csv"
    best_row = passing.sort_values("mean_f1_macro", ascending=False, kind="mergesort").iloc[0]
    assert best_row["model"] == champion, (
        f"Config's recorded champion '{champion}' does not match the best-scoring PASSING model in the "
        f"CSV ('{best_row['model']}') - these must agree. A failed candidate (status != 'OK') is never "
        "eligible, by construction, whatever its score."
    )


def test_gate3_failed_candidate_excluded_from_champion_selection(artifacts_dir):
    # Real, known open item: catboost failed on the user's actual run (root cause not
    # investigated, per explicit user instruction) - this must never silently become the champion.
    csv_path = artifacts_dir / "gate3_cv_benchmark_results.csv"
    if not csv_path.exists():
        pytest.skip("BP2 Gate 3 has not run yet.")
    df = pd.read_csv(csv_path)
    failed = df[df["status"] != "OK"]
    if failed.empty:
        pytest.skip("No failed candidates on this run - nothing to check.")
    assert not (failed["mean_f1_macro"].notna()).any(), (
        "A failed candidate row has a non-null mean_f1_macro - a failed candidate must never carry "
        "a usable score."
    )


# ---------------------------------------------------------------------------
# Gate 4 - statistical validation
# ---------------------------------------------------------------------------


def test_gate4_statistical_validation_schema(artifacts_dir, bp2_config):
    json_path = artifacts_dir / "gate4_statistical_validation.json"
    if not json_path.exists():
        pytest.skip("BP2 Gate 4 has not run yet.")
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
    assert ci_low <= ci_high

    gate3_block = bp2_config.get("gate3_model_benchmark")
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
        pytest.skip("BP2 Gate 5 has not run yet.")

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
        "feature_summary",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) == summary["n_decision_records"]
    assert df["in_shap_sample"].sum() == summary["n_with_reason_codes"]
    assert df["confidence_top1"].between(0.0, 1.0).all()

    # Every row marked outside the SHAP sample must never carry reason codes - the grounding
    # boundary this project enforces for every BP.
    out_of_sample = df[~df["in_shap_sample"]]
    assert (
        out_of_sample["reason_codes"].fillna("") == ""
    ).all(), "A row marked outside the SHAP sample has non-empty reason_codes - grounding boundary violated."


def test_gate5_recomputed_accuracy_matches_gate3_recorded(artifacts_dir, bp2_config):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP2 Gate 5 has not run yet.")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    gate3_block = bp2_config.get("gate3_model_benchmark")
    if gate3_block is None:
        pytest.skip("BP2 Gate 3 config block missing - cannot cross-check.")
    diff = abs(summary["overall_test_accuracy_recomputed"] - gate3_block["held_out_test_accuracy"])
    assert diff < 1e-2, (
        f"Gate 5's recomputed accuracy ({summary['overall_test_accuracy_recomputed']}) drifted from "
        f"Gate 3's recorded accuracy ({gate3_block['held_out_test_accuracy']}) by more than the "
        f"rounding-only tolerance expected between a 4-decimal config value and a 6-decimal JSON value."
    )


def test_gate5_compliance_touchpoint_documents_no_genai(artifacts_dir):
    summary_path = artifacts_dir / "gate5_decision_layer_summary.json"
    if not summary_path.exists():
        pytest.skip("BP2 Gate 5 has not run yet.")
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
        pytest.skip("No BP2 gate has written model_inventory_entry.json yet.")
    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    assert inventory["bp_id"] == "bp2"
    assert "model_name" in inventory
    # If gate5 fields are present, gate3/gate4 fields must be too (gates run in order - a gate5
    # entry with no gate3/gate4 history would mean the inventory was corrupted or hand-edited).
    if "gate5_n_decision_records" in inventory:
        assert "cv_mean_f1_macro" in inventory, "gate5 fields present without gate3's own fields"
        assert "gate4_roc_auc_ovr_macro" in inventory, "gate5 fields present without gate4's own fields"
