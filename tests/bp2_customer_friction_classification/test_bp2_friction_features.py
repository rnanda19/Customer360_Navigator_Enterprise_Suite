"""
tests/bp2_customer_friction_classification/test_bp2_friction_features.py — Customer360 Navigator

Full pytest coverage for src/features/bp2_friction_features.py (BP2 Gate 6 governance
requirement, mirroring BP1 Gate 6's test_bp1_intent_classifier.py pattern). Includes consistency
checks against the literal values BP2 Gates 3/4/5's own delivered notebook source uses inline,
since this module's entire purpose is to be a verified single source of truth for that duplicated
logic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from features import bp2_friction_features as bff

# ---------------------------------------------------------------------------
# Constants - must exactly match what Gates 3/4/5's delivered notebooks define inline.
# ---------------------------------------------------------------------------


def test_feature_cols_categorical_matches_gate3_4_5_definitions():
    assert bff.FEATURE_COLS_CATEGORICAL == [
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "State",
        "Submitted via",
        "common_taxonomy_bucket",
    ]


def test_company_col_and_catboost_cols_match_gate3_4_5_definitions():
    assert bff.COMPANY_COL == "Company"
    assert bff.CATBOOST_FEATURE_COLS == bff.FEATURE_COLS_CATEGORICAL + ["Company"]


def test_barred_columns_matches_gate3_4_5_definitions():
    assert bff.BARRED_COLUMNS == [
        "Company response to consumer",
        "Timely response?",
        "Date received",
        "Date sent to company",
        "Company public response",
        "Complaint ID",
        "ZIP code",
        "Tags",
    ]


def test_needs_dense_and_uses_raw_categorical_match_gate3_4_5_definitions():
    assert bff.NEEDS_DENSE == frozenset({"hist_gradient_boosting"})
    # CatBoost (the only candidate that ever used this path) was removed 2026-09-22 - see
    # Lesson #22 in LESSONS_LEARNED_APPLIED.md. No candidate uses the raw-categorical path now.
    assert bff.USES_RAW_CATEGORICAL == frozenset()


# ---------------------------------------------------------------------------
# make_candidates
# ---------------------------------------------------------------------------


def test_make_candidates_returns_all_five_models():
    # 5 models since 2026-09-22 - CatBoost removed (Lesson #22 in LESSONS_LEARNED_APPLIED.md).
    candidates = bff.make_candidates(random_state=42)
    assert set(candidates.keys()) == {
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
        "xgboost",
        "lightgbm",
    }


def test_make_candidates_uses_given_random_state_and_class_weight_balanced():
    candidates = bff.make_candidates(random_state=123)
    assert isinstance(candidates["logistic_regression"], LogisticRegression)
    assert candidates["logistic_regression"].random_state == 123
    assert candidates["logistic_regression"].class_weight == "balanced"
    assert candidates["random_forest"].random_state == 123
    assert candidates["random_forest"].class_weight == "balanced"
    assert candidates["random_forest"].n_jobs == 1  # no nested parallelism (WARP)


def test_make_candidates_hist_gradient_boosting_and_xgboost_never_pass_class_weight():
    # Documented library-capability asymmetry (Gates 3/4/5's own comment) - neither
    # HistGradientBoostingClassifier's nor XGBoost's sklearn API is passed class_weight='balanced'
    # here (unlike logistic_regression/random_forest/lightgbm above), since this environment's
    # installed versions don't support it for multiclass. sklearn's BaseEstimator always exposes a
    # `class_weight` attribute name once ANY estimator declares it as a constructor param
    # (hasattr is True either way) - the real signal is that it was left at its unset default,
    # never explicitly set to "balanced" the way the other three candidates are.
    candidates = bff.make_candidates(random_state=42)
    assert isinstance(candidates["hist_gradient_boosting"], HistGradientBoostingClassifier)
    assert (
        "class_weight" not in candidates["hist_gradient_boosting"].get_params(deep=False)
        or candidates["hist_gradient_boosting"].get_params(deep=False).get("class_weight") is None
    )
    from xgboost import XGBClassifier

    assert isinstance(candidates["xgboost"], XGBClassifier)
    assert candidates["xgboost"].get_params(deep=False).get("class_weight") is None


# ---------------------------------------------------------------------------
# build_shared_preprocessing
# ---------------------------------------------------------------------------


def _tiny_raw_frame(n=6):
    products = ["Checking or savings account", "Credit card"] * (n // 2)
    return pd.DataFrame(
        {
            "Product": products,
            "Sub-product": ["Checking account"] * n,
            "Issue": ["Some issue"] * n,
            "Sub-issue": ["Some sub-issue"] * n,
            "State": ["CA", "NY"] * (n // 2),
            "Submitted via": ["Web"] * n,
            "common_taxonomy_bucket": ["BUCKET_A", "BUCKET_B"] * (n // 2),
            "Company": [f"Company_{i % 3}" for i in range(n)],
        }
    )


def test_build_shared_preprocessing_shapes_and_feature_names():
    X_train_raw = _tiny_raw_frame(6)
    X_test_raw = _tiny_raw_frame(4)
    ohe, X_train_shared, X_test_shared, company_freq_map, feature_names = bff.build_shared_preprocessing(
        X_train_raw, X_test_raw
    )
    assert X_train_shared.shape[0] == 6
    assert X_test_shared.shape[0] == 4
    # +1 for the appended Company_freq column
    assert X_train_shared.shape[1] == len(feature_names)
    assert feature_names[-1] == "Company_freq"
    assert set(company_freq_map.keys()) == {"Company_0", "Company_1", "Company_2"}


def test_build_shared_preprocessing_unseen_test_company_gets_zero_frequency():
    X_train_raw = _tiny_raw_frame(6)
    X_test_raw = _tiny_raw_frame(2)
    X_test_raw.loc[0, "Company"] = "Never_Seen_In_Train"
    _, _, X_test_shared, company_freq_map, _ = bff.build_shared_preprocessing(X_train_raw, X_test_raw)
    assert "Never_Seen_In_Train" not in company_freq_map
    # Last column is Company_freq - unseen company's frequency must be exactly 0, never fabricated.
    assert X_test_shared.toarray()[0, -1] == 0.0


# ---------------------------------------------------------------------------
# to_dense
# ---------------------------------------------------------------------------


def test_to_dense_converts_sparse():
    from scipy import sparse as sp

    sparse_matrix = sp.csr_matrix(np.array([[1.0, 0.0], [0.0, 2.0]]))
    dense = bff.to_dense(sparse_matrix)
    assert isinstance(dense, np.ndarray)
    np.testing.assert_array_equal(dense, [[1.0, 0.0], [0.0, 2.0]])


def test_to_dense_passthrough_for_already_dense():
    arr = np.array([[1.0, 2.0]])
    assert bff.to_dense(arr) is arr


# ---------------------------------------------------------------------------
# is_linear_champion (the real bug Gate 4 fixed before delivery)
# ---------------------------------------------------------------------------


def test_is_linear_champion_true_for_logistic_regression():
    assert bff.is_linear_champion(LogisticRegression()) is True


def test_is_linear_champion_false_for_tree_based_models_not_in_needs_dense():
    # The whole point of the Gate 4 fix: xgboost is NOT in NEEDS_DENSE (that set only has
    # hist_gradient_boosting) but must still be treated as non-linear for SHAP densification.
    from xgboost import XGBClassifier

    assert bff.is_linear_champion(XGBClassifier()) is False
    assert bff.is_linear_champion(HistGradientBoostingClassifier()) is False
    assert "xgboost" not in bff.NEEDS_DENSE  # the exact gap the Gate 4 bug fix closed


# ---------------------------------------------------------------------------
# reorder_predict_proba
# ---------------------------------------------------------------------------


class _FakeRawCategoricalModel:
    """Stand-in for a fitted CatBoostClassifier whose classes_ order need not match
    label_encoder.classes_ - the exact scenario Gate 4/5's real fix addresses."""

    def __init__(self, classes_):
        self.classes_ = classes_


def test_reorder_predict_proba_realigns_to_label_encoder_order():
    label_encoder = LabelEncoder().fit(["HIGH_FRICTION", "LOW_FRICTION", "MEDIUM_FRICTION"])
    # Model's own discovered class order differs from label_encoder's sorted order.
    model = _FakeRawCategoricalModel(classes_=["MEDIUM_FRICTION", "HIGH_FRICTION", "LOW_FRICTION"])
    # One row: probability mass concentrated on MEDIUM_FRICTION (model's column 0).
    y_proba_raw = np.array([[0.7, 0.2, 0.1]])
    reordered = bff.reorder_predict_proba(model, y_proba_raw, label_encoder)
    # label_encoder.classes_ is alphabetically sorted: HIGH, LOW, MEDIUM
    assert list(label_encoder.classes_) == ["HIGH_FRICTION", "LOW_FRICTION", "MEDIUM_FRICTION"]
    # So column order after reorder must be [HIGH(0.2), LOW(0.1), MEDIUM(0.7)]
    np.testing.assert_array_almost_equal(reordered[0], [0.2, 0.1, 0.7])


def test_reorder_predict_proba_identity_when_orders_already_match():
    label_encoder = LabelEncoder().fit(["A", "B"])
    model = _FakeRawCategoricalModel(classes_=["A", "B"])
    y_proba_raw = np.array([[0.4, 0.6]])
    reordered = bff.reorder_predict_proba(model, y_proba_raw, label_encoder)
    np.testing.assert_array_almost_equal(reordered[0], [0.4, 0.6])


# ---------------------------------------------------------------------------
# reason_codes_for_row_shared (reused verbatim from bp1_intent_classifier - HYPER)
# ---------------------------------------------------------------------------


def test_reason_codes_for_row_shared_only_returns_nonzero_valued_features():
    feature_names = np.array(["Product_Checking", "State_CA", "Company_freq", "State_NY"])
    shap_values = np.array([0.9, 0.5, 0.1, 5.0])  # State_NY has the HIGHEST |shap| ...
    row_values = np.array([0.3, 0.2, 12.0, 0.0])  # ... but is absent (0.0) in this row - excluded
    codes = bff.reason_codes_for_row_shared(shap_values, row_values, feature_names, n_reason_codes=5)
    assert "State_NY" not in codes
    assert set(codes) == {"Product_Checking", "State_CA", "Company_freq"}


def test_reason_codes_for_row_shared_is_the_bp1_module_function():
    # Explicit HYPER reuse assertion - this is not a re-implementation, it is the same object.
    from models.bp1_intent_classifier import reason_codes_for_row

    assert bff.reason_codes_for_row_shared is reason_codes_for_row


# ---------------------------------------------------------------------------
# reason_codes_for_row_raw_categorical (genuinely new for BP2's CatBoost path)
# ---------------------------------------------------------------------------


def test_reason_codes_for_row_raw_categorical_formats_column_equals_value():
    feature_names = np.array(["Product", "State", "Company"])
    shap_values = np.array([0.2, 0.9, 0.1])
    row_values = pd.Series({"Product": "Checking or savings account", "State": "CA", "Company": "Bank A"})
    codes = bff.reason_codes_for_row_raw_categorical(shap_values, feature_names, row_values, n_reason_codes=2)
    assert codes == ["State=CA", "Product=Checking or savings account"]  # ranked by |shap| descending


def test_reason_codes_for_row_raw_categorical_includes_missing_as_a_real_value():
    # CatBoost's raw-categorical path has no "absent" concept - MISSING is itself a valid,
    # reportable category, never excluded the way a zero one-hot value would be.
    feature_names = np.array(["Product", "State"])
    shap_values = np.array([0.5, 0.1])
    row_values = pd.Series({"Product": "MISSING", "State": "CA"})
    codes = bff.reason_codes_for_row_raw_categorical(shap_values, feature_names, row_values, n_reason_codes=2)
    assert "Product=MISSING" in codes


def test_reason_codes_for_row_raw_categorical_shape_mismatch_raises():
    with pytest.raises(ValueError, match="Shape mismatch"):
        bff.reason_codes_for_row_raw_categorical(
            np.array([0.1, 0.2]), np.array(["a", "b", "c"]), pd.Series({"a": 1, "b": 2, "c": 3})
        )
