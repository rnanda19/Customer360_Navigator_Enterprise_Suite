"""
tests/bp1_customer_intent_classification/test_bp1_intent_classifier.py — Customer360 Navigator

Full pytest coverage for src/models/bp1_intent_classifier.py (BP1 Gate 6 governance requirement).
Includes a consistency check against the literal values BP1 Gates 3/4/5's own delivered notebook
source uses inline, since this module's entire purpose is to be a verified single source of truth
for that duplicated logic.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

from models import bp1_intent_classifier as bic


# ---------------------------------------------------------------------------
# Constants - must exactly match what Gates 3/4/5's delivered notebooks define inline.
# ---------------------------------------------------------------------------

def test_tfidf_kwargs_matches_gate3_4_5_definitions():
    assert bic.TFIDF_KWARGS == dict(
        max_features=5000, ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words="english"
    )


def test_needs_dense_matches_gate3_4_5_definitions():
    assert bic.NEEDS_DENSE == frozenset({"hist_gradient_boosting"})


# ---------------------------------------------------------------------------
# make_candidates
# ---------------------------------------------------------------------------

def test_make_candidates_returns_all_six_models():
    candidates = bic.make_candidates(random_state=42)
    assert set(candidates.keys()) == {
        "logistic_regression", "random_forest", "hist_gradient_boosting",
        "xgboost", "lightgbm", "catboost",
    }


def test_make_candidates_uses_given_random_state():
    candidates = bic.make_candidates(random_state=123)
    assert isinstance(candidates["logistic_regression"], LogisticRegression)
    assert candidates["logistic_regression"].random_state == 123
    assert candidates["random_forest"].random_state == 123
    assert candidates["random_forest"].n_jobs == 1  # no nested parallelism (WARP)


def test_make_candidates_hist_gradient_boosting_is_correct_type():
    candidates = bic.make_candidates(random_state=42)
    assert isinstance(candidates["hist_gradient_boosting"], HistGradientBoostingClassifier)


# ---------------------------------------------------------------------------
# to_dense
# ---------------------------------------------------------------------------

def test_to_dense_converts_sparse():
    sparse_matrix = sp.csr_matrix(np.array([[1.0, 0.0], [0.0, 2.0]]))
    dense = bic.to_dense(sparse_matrix)
    assert isinstance(dense, np.ndarray)
    np.testing.assert_array_equal(dense, [[1.0, 0.0], [0.0, 2.0]])


def test_to_dense_passthrough_for_already_dense():
    arr = np.array([[1.0, 2.0]])
    result = bic.to_dense(arr)
    assert result is arr


# ---------------------------------------------------------------------------
# make_pipeline
# ---------------------------------------------------------------------------

def test_make_pipeline_no_densify_for_logistic_regression():
    candidates = bic.make_candidates(random_state=42)
    pipe = bic.make_pipeline("logistic_regression", candidates)
    assert isinstance(pipe, Pipeline)
    step_names = [name for name, _ in pipe.steps]
    assert step_names == ["tfidf", "clf"]


def test_make_pipeline_includes_densify_for_hist_gradient_boosting():
    candidates = bic.make_candidates(random_state=42)
    pipe = bic.make_pipeline("hist_gradient_boosting", candidates)
    step_names = [name for name, _ in pipe.steps]
    assert step_names == ["tfidf", "densify", "clf"]
    densify_step = dict(pipe.steps)["densify"]
    assert isinstance(densify_step, FunctionTransformer)


def test_make_pipeline_unknown_candidate_raises_keyerror():
    candidates = bic.make_candidates(random_state=42)
    with pytest.raises(KeyError, match="Unknown candidate"):
        bic.make_pipeline("not_a_real_model", candidates)


def test_make_pipeline_end_to_end_fit_predict():
    # Small real fit/predict smoke of the actual pipeline shape (not a substitute for the
    # notebooks' own full real-data runs - just proves this extracted definition is usable).
    candidates = bic.make_candidates(random_state=42)
    pipe = bic.make_pipeline("logistic_regression", candidates)
    X = ["card is lost", "transfer failed", "card is lost again", "transfer pending review"]
    y = [0, 1, 0, 1]
    pipe.fit(X, y)
    preds = pipe.predict(X)
    assert len(preds) == 4


# ---------------------------------------------------------------------------
# reason_codes_for_row (BP1 Gate 5's grounding rule)
# ---------------------------------------------------------------------------

def test_reason_codes_for_row_only_returns_nonzero_weight_terms():
    feature_names = np.array(["card", "lost", "transfer", "unrelated"])
    shap_values = np.array([0.9, 0.5, 0.1, 5.0])  # 'unrelated' has the HIGHEST |shap| ...
    tfidf_weights = np.array([0.3, 0.2, 0.0, 0.0])  # ... but zero weight in this row - must be excluded
    codes = bic.reason_codes_for_row(shap_values, tfidf_weights, feature_names, n_reason_codes=5)
    assert "unrelated" not in codes
    assert set(codes) == {"card", "lost"}


def test_reason_codes_for_row_respects_top_k():
    feature_names = np.array(["a", "b", "c", "d"])
    shap_values = np.array([0.1, 0.4, 0.3, 0.2])
    tfidf_weights = np.array([1.0, 1.0, 1.0, 1.0])  # all present
    codes = bic.reason_codes_for_row(shap_values, tfidf_weights, feature_names, n_reason_codes=2)
    assert codes == ["b", "c"]  # ranked by |shap| descending, top 2


def test_reason_codes_for_row_empty_when_no_nonzero_weights():
    feature_names = np.array(["a", "b"])
    shap_values = np.array([0.5, 0.5])
    tfidf_weights = np.array([0.0, 0.0])
    assert bic.reason_codes_for_row(shap_values, tfidf_weights, feature_names) == []


def test_reason_codes_for_row_shape_mismatch_raises():
    with pytest.raises(ValueError, match="Shape mismatch"):
        bic.reason_codes_for_row(
            np.array([0.1, 0.2]), np.array([0.1, 0.2, 0.3]), np.array(["a", "b", "c"])
        )
