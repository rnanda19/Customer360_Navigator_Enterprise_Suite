"""
tests/shared/test_bp1_rollup_helpers.py — Customer360 Navigator

Full pytest coverage for the pure-logic (non-rendering) functions in
src/reporting/bp1_rollup_helpers.py - the BP1 executive-rollup report's shared component library
(BP1 Rollup governance requirement, same "full test coverage, never smoke-testing-only" standard
as every other src/ module in this project). Matplotlib figure builders and the DOCX/XLSX/PPTX
writers are intentionally NOT unit-tested here (rendering/export code, not business logic) - same
convention already used for every gate notebook's own chart cells, which are also not separately
unit-tested.

This module has no financial-impact / illustrative-assumption code path - see the module's own
docstring. There is nothing to test for that removed functionality.
"""

from __future__ import annotations

import pandas as pd
import pytest

from reporting import bp1_rollup_helpers as rh


# ---------------------------------------------------------------------------
# per_class_report_to_df / worst_best_intents
# ---------------------------------------------------------------------------

def _make_classification_report():
    return {
        "intent_a": {"precision": 0.95, "recall": 0.90, "f1-score": 0.925, "support": 40.0},
        "intent_b": {"precision": 0.40, "recall": 0.35, "f1-score": 0.374, "support": 40.0},
        "intent_c": {"precision": 0.70, "recall": 0.72, "f1-score": 0.710, "support": 40.0},
        "accuracy": 0.70,
        "macro avg": {"precision": 0.683, "recall": 0.657, "f1-score": 0.670, "support": 120.0},
        "weighted avg": {"precision": 0.683, "recall": 0.657, "f1-score": 0.670, "support": 120.0},
        "True": {"precision": 0.683, "recall": 0.657, "f1-score": 0.670, "support": 120.0},
    }


def test_per_class_report_to_df_excludes_aggregate_rows():
    df = rh.per_class_report_to_df(_make_classification_report())
    assert set(df["intent"]) == {"intent_a", "intent_b", "intent_c"}
    assert "accuracy" not in df["intent"].values
    assert "macro avg" not in df["intent"].values


def test_per_class_report_to_df_sorted_descending_by_f1():
    df = rh.per_class_report_to_df(_make_classification_report())
    assert list(df["f1-score"]) == sorted(df["f1-score"], reverse=True)
    assert df.iloc[0]["intent"] == "intent_a"


def test_worst_best_intents_returns_correct_ends():
    best, worst = rh.worst_best_intents(_make_classification_report(), n=2)
    assert list(best["intent"]) == ["intent_a", "intent_c"]
    assert list(worst["intent"]) == ["intent_b", "intent_c"]


# ---------------------------------------------------------------------------
# top_confused_pairs
# ---------------------------------------------------------------------------

def test_top_confused_pairs_excludes_diagonal_and_zero_counts():
    df = pd.DataFrame(
        [[10, 3, 0], [1, 8, 0], [0, 0, 5]],
        index=["a", "b", "c"], columns=["a", "b", "c"],
    )
    result = rh.top_confused_pairs(df, n=10)
    assert not any((result["true_intent"] == result["predicted_intent"]))
    assert len(result) == 2  # (a->b, count 3) and (b->a, count 1); zero-count pairs excluded
    assert result.iloc[0]["true_intent"] == "a"
    assert result.iloc[0]["predicted_intent"] == "b"
    assert result.iloc[0]["count"] == 3


def test_top_confused_pairs_respects_n_limit():
    df = pd.DataFrame(
        [[0, 5, 4, 3], [1, 0, 1, 1], [1, 1, 0, 1], [1, 1, 1, 0]],
        index=["a", "b", "c", "d"], columns=["a", "b", "c", "d"],
    )
    result = rh.top_confused_pairs(df, n=2)
    assert len(result) == 2
    assert list(result["count"]) == sorted(result["count"], reverse=True)


# ---------------------------------------------------------------------------
# build_smart_suggestions
# ---------------------------------------------------------------------------

def _make_bundle_for_suggestions(near_random=True, high_variance=True):
    rows = [
        {"model": "logistic_regression", "status": "OK", "elapsed_seconds": 5.0, "mean_f1_macro": 0.80, "std_f1_macro": 0.01},
    ]
    if near_random:
        rows.append({"model": "hist_gradient_boosting", "status": "OK", "elapsed_seconds": 1730.0, "mean_f1_macro": 0.013, "std_f1_macro": 0.026})
    if high_variance:
        rows.append({"model": "lightgbm", "status": "OK", "elapsed_seconds": 17.0, "mean_f1_macro": 0.44, "std_f1_macro": 0.355})
    return {
        "gate3_cv_df": pd.DataFrame(rows),
        "gate5_summary": {"overlap_count_with_gate4": 4, "n_with_reason_codes": 150, "n_decision_records": 3080},
        "model_inventory": {"held_out_test_accuracy": 0.8224, "n_classes": 77},
        "gate4": {"shap_sample_size": 150},
    }


def test_build_smart_suggestions_flags_near_random_and_high_variance_when_present():
    suggestions = rh.build_smart_suggestions(_make_bundle_for_suggestions())
    titles = " ".join(s["title"] for s in suggestions)
    assert "hist_gradient_boosting" in titles
    assert "lightgbm" in titles


def test_build_smart_suggestions_omits_anomaly_items_when_absent():
    suggestions = rh.build_smart_suggestions(_make_bundle_for_suggestions(near_random=False, high_variance=False))
    titles = " ".join(s["title"] for s in suggestions)
    assert "hist_gradient_boosting" not in titles
    assert "lightgbm" not in titles
    assert len(suggestions) == 3  # SHAP overlap, per-intent monitoring, reason-code coverage - always present


def test_build_smart_suggestions_every_item_has_required_fields():
    suggestions = rh.build_smart_suggestions(_make_bundle_for_suggestions())
    for s in suggestions:
        assert set(s.keys()) == {"title", "specific", "measurable", "timebound", "owner_placeholder"}
        for v in s.values():
            assert isinstance(v, str) and len(v) > 0


# ---------------------------------------------------------------------------
# build_kpi_bundle
# ---------------------------------------------------------------------------

def _make_full_bundle():
    return {
        "model_inventory": {
            "model_name": "logistic_regression", "held_out_test_accuracy": 0.8224,
            "held_out_test_f1_macro": 0.8221, "cv_mean_f1_macro": 0.804,
            "n_classes": 77, "n_train_rows": 10003, "n_test_rows": 3080,
        },
        "gate4": {"roc_auc_ovr_macro": 0.9933},
        "gate5_summary": {"n_decision_records": 3080, "n_with_reason_codes": 150},
        "gate6_summary": {
            "pytest_all_passed": True, "pytest_counts": {"passed": 52, "failed": 0},
            "notebook_syntax_all_passed": True,
            "n_gate3_near_random_anomalies_detected": 1,
            "n_gate3_high_variance_anomalies_detected": 2,
        },
        "gate2_coverage_df": pd.DataFrame({
            "common_taxonomy_bucket": ["OUT_OF_SCOPE_NO_BANKING77_OVERLAP", "CARD_ISSUANCE_AND_LIFECYCLE"],
            "cfpb_fraction": [0.934, 0.031],
        }),
    }


def test_build_kpi_bundle_pulls_real_values_verbatim():
    bundle = _make_full_bundle()
    kpis = rh.build_kpi_bundle(bundle)
    assert kpis["champion_model"] == "logistic_regression"
    assert kpis["held_out_test_accuracy"] == 0.8224
    assert kpis["n_decision_records"] == 3080
    assert kpis["reason_code_coverage"] == pytest.approx(150 / 3080)
    assert kpis["cfpb_out_of_scope_fraction"] == pytest.approx(0.934)
    assert kpis["pytest_all_passed"] is True
    assert kpis["governance_gates_complete"] == 6


def test_build_kpi_bundle_surfaces_gate3_open_anomaly_counts():
    bundle = _make_full_bundle()
    kpis = rh.build_kpi_bundle(bundle)
    assert kpis["n_gate3_near_random_anomalies"] == 1
    assert kpis["n_gate3_high_variance_anomalies"] == 2


def test_build_kpi_bundle_has_no_financial_fields():
    bundle = _make_full_bundle()
    kpis = rh.build_kpi_bundle(bundle)
    assert not any("saving" in k.lower() or "financial" in k.lower() for k in kpis)


# ---------------------------------------------------------------------------
# build_gate1_summary
# ---------------------------------------------------------------------------

def _make_policy():
    return {
        "target_definition": {
            "primary_target": "category",
            "primary_target_description": "BANKING77's real 77-class fine-grained customer intent label.",
            "secondary_target": "common_taxonomy_bucket",
            "secondary_target_description": "The 9-bucket common taxonomy from Gate 2.",
            "feature_variable": "text",
            "train_test_split_source": "BANKING77's own provided train/test split.",
        },
        "leakage_rules": ["No CFPB row-level data is ever joined into BANKING77 data."],
        "assumptions": ["CFPB<->BANKING77 integration is a taxonomy crosswalk, not a row-level join."],
        "compliance_touchpoint": {
            "requirement": "Data-minimization & purpose-limitation statement (GLBA/GDPR-aligned)",
            "statement": "BP1 processes only the text and category fields of BANKING77.",
        },
        "live_checks": {
            "shared_columns_cfpb_banking77": [],
            "train_test_exact_text_overlap_rows": 0,
            "class_imbalance_77_class": {
                "min_class_count": 35, "max_class_count": 187, "imbalance_ratio_max_over_min": 5.34,
            },
            "class_imbalance_9_bucket": {
                "min_bucket_count": 460, "max_bucket_count": 1770, "imbalance_ratio_max_over_min": 3.85,
            },
        },
        "generated_at_utc": "2026-09-22T04:53:54.488546+00:00",
    }


def test_build_gate1_summary_reads_every_real_field():
    gate1 = rh.build_gate1_summary({"policy": _make_policy()})
    assert gate1["primary_target"] == "category"
    assert gate1["secondary_target"] == "common_taxonomy_bucket"
    assert gate1["feature_variable"] == "text"
    assert gate1["train_test_exact_text_overlap_rows"] == 0
    assert gate1["class_imbalance_77_class"]["imbalance_ratio_max_over_min"] == 5.34
    assert len(gate1["leakage_rules"]) == 1
    assert len(gate1["assumptions"]) == 1


def test_build_gate1_summary_shared_columns_is_the_real_list_not_just_a_count():
    gate1 = rh.build_gate1_summary({"policy": _make_policy()})
    assert gate1["shared_columns_cfpb_banking77"] == []


# ---------------------------------------------------------------------------
# build_gate6_governance_detail
# ---------------------------------------------------------------------------

def _make_gate6_bundle():
    return {
        "gate6_summary": {
            "pytest_summary_line": "52 passed, 0 failed, 0 skipped, 0 errors",
            "pytest_counts": {"passed": 52, "failed": 0, "skipped": 0, "errors": 0},
            "pytest_all_passed": True,
            "notebook_syntax_check_n_passed": 8,
            "notebook_syntax_check_n_failed": 0,
            "notebook_syntax_all_passed": True,
            "n_gate3_near_random_anomalies_detected": 1,
            "n_gate3_high_variance_anomalies_detected": 2,
            "model_card_path": "reports/bp1_customer_intent_classification/MODEL_CARD.md",
            "changelog_path": "reports/bp1_customer_intent_classification/CHANGELOG.md",
            "generated_at_utc": "2026-09-22T06:25:18.547134+00:00",
        },
        "model_inventory": {
            "compliance_touchpoint": "Model inventory entry opened (SR 11-7 first-line record)",
            "model_family": "TF-IDF + logistic_regression",
            "training_data": "PolyAI BANKING77 train split (real, provided split).",
        },
        "bp1_config": {
            "gate3_model_benchmark": {
                "candidates_evaluated": ["logistic_regression", "random_forest"],
                "candidates_failed": [],
            },
        },
    }


def test_build_gate6_governance_detail_reads_every_real_field():
    gate6 = rh.build_gate6_governance_detail(_make_gate6_bundle())
    assert gate6["n_gate3_near_random_anomalies_detected"] == 1
    assert gate6["n_gate3_high_variance_anomalies_detected"] == 2
    assert gate6["model_card_path"].endswith("MODEL_CARD.md")
    assert gate6["model_family"] == "TF-IDF + logistic_regression"
    assert gate6["candidates_evaluated"] == ["logistic_regression", "random_forest"]
    assert gate6["candidates_failed"] == []


def test_build_gate6_governance_detail_handles_missing_gate3_block_gracefully():
    bundle = _make_gate6_bundle()
    bundle["bp1_config"] = {}
    gate6 = rh.build_gate6_governance_detail(bundle)
    assert gate6["candidates_evaluated"] == []
    assert gate6["candidates_failed"] == []


# ---------------------------------------------------------------------------
# load_all_gate_artifacts
# ---------------------------------------------------------------------------

def test_load_all_gate_artifacts_missing_prerequisite_raises_named_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Gates 1-6 to be real-run confirmed"):
        rh.load_all_gate_artifacts(tmp_path)
