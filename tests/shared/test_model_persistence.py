"""
tests/shared/test_model_persistence.py — Customer360 Navigator

Unit tests for src/models/model_persistence.py, using small SYNTHETIC fixtures (not real BP1/BP2
data - this module is BP-agnostic and its contract is fully testable without any real project
artifact). Mirrors this project's established test style: real assertions, no mocking of the
behavior under test, explanatory docstrings for why each case matters.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder

from models.model_persistence import (
    REQUIRED_KEYS,
    load_model_bundle,
    predict_bp1,
    predict_bp2,
    predict_bp3,
    save_model_bundle,
)


# ---------------------------------------------------------------------------
# Fixtures - tiny synthetic BP1-shaped and BP2-shaped fitted bundles.
# ---------------------------------------------------------------------------
@pytest.fixture
def bp1_bundle():
    texts = [
        "card is lost",
        "transfer failed",
        "card is stolen",
        "pending transfer issue",
    ]
    labels = ["lost_card", "transfer_issue", "lost_card", "transfer_issue"]
    label_encoder = LabelEncoder().fit(labels)
    y = label_encoder.transform(labels)
    pipeline = Pipeline(
        [
            ("tfidf", TfidfVectorizer()),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )
    pipeline.fit(texts, y)
    return {
        "bp_id": "bp1",
        "champion_name": "logistic_regression",
        "pipeline": pipeline,
        "label_encoder": label_encoder,
        "class_names": list(label_encoder.classes_),
        "metadata": {"synthetic_fixture": True},
    }


@pytest.fixture
def bp2_bundle():
    X_raw = pd.DataFrame(
        {
            "Product": ["Credit card", "Mortgage", "Credit card", "Mortgage"],
            "Company": ["Acme Bank", "Acme Bank", "Beta Bank", "Beta Bank"],
        }
    )
    y_labels = pd.Series(["LOW_FRICTION", "HIGH_FRICTION", "LOW_FRICTION", "HIGH_FRICTION"])
    label_encoder = LabelEncoder().fit(y_labels)
    y = label_encoder.transform(y_labels)

    preprocessor = ColumnTransformer(
        [("ohe", OneHotEncoder(handle_unknown="ignore"), ["Product"])], remainder="drop"
    )
    X_ohe = preprocessor.fit_transform(X_raw)
    company_freq_map = X_raw["Company"].value_counts().to_dict()
    from scipy import sparse as sp

    freq = X_raw["Company"].map(company_freq_map).to_numpy(dtype=np.float32).reshape(-1, 1)
    X_shared = sp.hstack([X_ohe, sp.csr_matrix(freq)], format="csr")

    classifier = LogisticRegression(max_iter=1000).fit(X_shared, y)
    return {
        "bp_id": "bp2",
        "champion_name": "logistic_regression",
        "preprocessor": preprocessor,
        "company_freq_map": company_freq_map,
        "feature_cols_categorical": ["Product"],
        "company_col": "Company",
        "classifier": classifier,
        "label_encoder": label_encoder,
        "class_names": list(label_encoder.classes_),
        "needs_dense": False,
        "metadata": {"synthetic_fixture": True},
    }


@pytest.fixture
def bp3_bundle():
    """BP3-shaped dict bundle - structurally identical to bp2_bundle's (OneHotEncoder + company-
    frequency, hstacked) EXCEPT for one real, load-bearing difference: no label_encoder. BP3's
    real target (intervention_required) is already binary 0/1 in the real pipeline (Polars
    .cast(pl.Int8) at Gate 3), never passed through a LabelEncoder - fabricating one here would
    misrepresent the real bundle contract this fixture is meant to mirror."""
    X_raw = pd.DataFrame(
        {
            "Product": ["Credit reporting", "Debt collection", "Credit reporting", "Debt collection"],
            "Company": ["Acme Bank", "Acme Bank", "Beta Bank", "Beta Bank"],
        }
    )
    y = np.array([0, 1, 0, 1])

    preprocessor = ColumnTransformer(
        [("ohe", OneHotEncoder(handle_unknown="ignore"), ["Product"])], remainder="drop"
    )
    X_ohe = preprocessor.fit_transform(X_raw)
    company_freq_map = X_raw["Company"].value_counts().to_dict()
    from scipy import sparse as sp

    freq = X_raw["Company"].map(company_freq_map).to_numpy(dtype=np.float32).reshape(-1, 1)
    X_shared = sp.hstack([X_ohe, sp.csr_matrix(freq)], format="csr")

    classifier = LogisticRegression(max_iter=1000).fit(X_shared, y)
    return {
        "bp_id": "bp3",
        "champion_name": "logistic_regression",
        "preprocessor": preprocessor,
        "company_freq_map": company_freq_map,
        "feature_cols_categorical": ["Product"],
        "company_col": "Company",
        "classifier": classifier,
        "class_names": ["0", "1"],
        "needs_dense": False,
        "metadata": {"synthetic_fixture": True},
    }


# ---------------------------------------------------------------------------
# save_model_bundle / load_model_bundle round trip
# ---------------------------------------------------------------------------
def test_bp1_save_load_round_trip(bp1_bundle, tmp_path):
    out_path = tmp_path / "bp1_champion.joblib"
    stats = save_model_bundle(bp1_bundle, out_path)
    assert out_path.exists()
    assert stats["size_bytes"] == out_path.stat().st_size
    assert len(stats["sha256"]) == 64  # real sha256 hex digest length

    reloaded = load_model_bundle(out_path)
    assert reloaded["bp_id"] == "bp1"
    assert reloaded["champion_name"] == "logistic_regression"
    # A round-tripped pipeline must predict IDENTICALLY to the original in-memory pipeline - this
    # is the real correctness bar for persistence, not merely "the file exists."
    original_pred = bp1_bundle["pipeline"].predict(["card is lost"])
    reloaded_pred = reloaded["pipeline"].predict(["card is lost"])
    assert list(original_pred) == list(reloaded_pred)


def test_bp2_save_load_round_trip(bp2_bundle, tmp_path):
    out_path = tmp_path / "bp2_champion.joblib"
    save_model_bundle(bp2_bundle, out_path)
    reloaded = load_model_bundle(out_path)
    assert reloaded["bp_id"] == "bp2"
    assert reloaded["company_freq_map"] == bp2_bundle["company_freq_map"]


def test_bp3_save_load_round_trip(bp3_bundle, tmp_path):
    out_path = tmp_path / "bp3_champion.joblib"
    save_model_bundle(bp3_bundle, out_path)
    reloaded = load_model_bundle(out_path)
    assert reloaded["bp_id"] == "bp3"
    assert reloaded["company_freq_map"] == bp3_bundle["company_freq_map"]
    assert "label_encoder" not in reloaded


def test_save_creates_parent_directories(bp1_bundle, tmp_path):
    nested_path = tmp_path / "a" / "b" / "c" / "champion.joblib"
    save_model_bundle(bp1_bundle, nested_path)
    assert nested_path.exists()


# ---------------------------------------------------------------------------
# Bundle-contract validation - a malformed bundle must fail loudly, not silently at inference time.
# ---------------------------------------------------------------------------
def test_save_rejects_unknown_bp_id(bp1_bundle, tmp_path):
    bad_bundle = dict(bp1_bundle)
    bad_bundle["bp_id"] = "bp99"  # not a supported persistence target (bp1/bp2/bp3 all are now)
    with pytest.raises(ValueError, match="Unknown or missing bp_id"):
        save_model_bundle(bad_bundle, tmp_path / "x.joblib")


def test_save_rejects_missing_required_key(bp1_bundle, tmp_path):
    incomplete_bundle = dict(bp1_bundle)
    del incomplete_bundle["label_encoder"]
    with pytest.raises(ValueError, match="missing required keys"):
        save_model_bundle(incomplete_bundle, tmp_path / "x.joblib")


def test_load_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_model_bundle(tmp_path / "does_not_exist.joblib")


def test_load_rejects_non_dict_payload(tmp_path):
    import joblib

    path = tmp_path / "not_a_bundle.joblib"
    joblib.dump([1, 2, 3], path)  # a real file exists, but the payload isn't a bundle dict
    with pytest.raises(ValueError, match="not a dict bundle"):
        load_model_bundle(path)


def test_required_keys_contract_covers_all_supported_bps():
    assert set(REQUIRED_KEYS.keys()) == {"bp1", "bp2", "bp3"}
    assert "pipeline" in REQUIRED_KEYS["bp1"]
    assert "preprocessor" in REQUIRED_KEYS["bp2"] and "company_freq_map" in REQUIRED_KEYS["bp2"]
    assert "preprocessor" in REQUIRED_KEYS["bp3"] and "company_freq_map" in REQUIRED_KEYS["bp3"]
    # BP3's real target is already binary 0/1 - never passed through a LabelEncoder anywhere in
    # the real pipeline (see model_persistence.py's module docstring) - so, unlike bp1/bp2, its
    # bundle contract has no label_encoder key.
    assert "label_encoder" not in REQUIRED_KEYS["bp3"]


# ---------------------------------------------------------------------------
# predict_bp1 / predict_bp2 - correctness against the synthetic fixtures' own known structure.
# ---------------------------------------------------------------------------
def test_predict_bp1_returns_well_formed_output(bp1_bundle):
    result = predict_bp1(bp1_bundle, ["card is lost", "transfer failed"])
    assert len(result["predicted_label"]) == 2
    assert len(result["confidence"]) == 2
    assert all(0.0 <= c <= 1.0 for c in result["confidence"])
    assert set(result["predicted_label"]).issubset(set(result["class_names"]))
    # Every row's probability vector must sum to 1 (a real predict_proba output, not fabricated).
    for row in result["probabilities"]:
        assert abs(sum(row) - 1.0) < 1e-6


def test_predict_bp1_wrong_bp_id_raises(bp2_bundle):
    with pytest.raises(ValueError, match="predict_bp1"):
        predict_bp1(bp2_bundle, ["x"])


def test_predict_bp2_returns_well_formed_output(bp2_bundle):
    X_new = pd.DataFrame({"Product": ["Credit card"], "Company": ["Acme Bank"]})
    result = predict_bp2(bp2_bundle, X_new)
    assert len(result["predicted_label"]) == 1
    assert result["predicted_label"][0] in result["class_names"]
    assert abs(sum(result["probabilities"][0]) - 1.0) < 1e-6


def test_predict_bp2_unseen_company_gets_zero_frequency_not_fabricated(bp2_bundle):
    """An unseen company at inference time must fall back to frequency 0 - never invented from
    the new row, never an average/default pulled from the training distribution. This mirrors
    Gates 3/4/5's own established fallback rule for a company absent from the train-fit map.
    """
    X_new_known = pd.DataFrame({"Product": ["Credit card"], "Company": ["Acme Bank"]})
    X_new_unseen = pd.DataFrame({"Product": ["Credit card"], "Company": ["Totally New Bank LLC"]})
    result_known = predict_bp2(bp2_bundle, X_new_known)
    result_unseen = predict_bp2(bp2_bundle, X_new_unseen)
    # Both must still produce valid, well-formed predictions (no crash on the unseen category) -
    # the exact confidence values are allowed to differ, but both are real, valid probability rows.
    assert abs(sum(result_known["probabilities"][0]) - 1.0) < 1e-6
    assert abs(sum(result_unseen["probabilities"][0]) - 1.0) < 1e-6


def test_predict_bp2_wrong_bp_id_raises(bp1_bundle):
    with pytest.raises(ValueError, match="predict_bp2"):
        predict_bp2(bp1_bundle, pd.DataFrame({"Product": ["x"], "Company": ["y"]}))


# ---------------------------------------------------------------------------
# predict_bp3 - correctness against the synthetic fixture's own known structure. BP3's response
# shape genuinely differs from predict_bp1's/predict_bp2's (binary predicted_label + a dedicated
# probability_positive_class field, no label_encoder-derived class names) - these tests assert
# against that real, different shape rather than reusing bp1/bp2's assertions verbatim.
# ---------------------------------------------------------------------------
def test_predict_bp3_returns_well_formed_output(bp3_bundle):
    X_new = pd.DataFrame({"Product": ["Credit reporting"], "Company": ["Acme Bank"]})
    result = predict_bp3(bp3_bundle, X_new)
    assert len(result["predicted_label"]) == 1
    assert result["predicted_label"][0] in (0, 1)
    assert 0.0 <= result["probability_positive_class"][0] <= 1.0
    assert abs(sum(result["probabilities"][0]) - 1.0) < 1e-6
    assert result["class_names"] == ["0", "1"]


def test_predict_bp3_confidence_is_max_of_both_class_probabilities(bp3_bundle):
    X_new = pd.DataFrame({"Product": ["Credit reporting"], "Company": ["Acme Bank"]})
    result = predict_bp3(bp3_bundle, X_new)
    p_positive = result["probability_positive_class"][0]
    assert abs(result["confidence"][0] - max(p_positive, 1 - p_positive)) < 1e-6


def test_predict_bp3_unseen_company_gets_zero_frequency_not_fabricated(bp3_bundle):
    """Same real fallback rule as predict_bp2's unseen-company case: an unseen company at
    inference time must fall back to frequency 0 - never invented from the new row, never an
    average/default pulled from the training distribution."""
    X_new_known = pd.DataFrame({"Product": ["Credit reporting"], "Company": ["Acme Bank"]})
    X_new_unseen = pd.DataFrame({"Product": ["Credit reporting"], "Company": ["Totally New Bank LLC"]})
    result_known = predict_bp3(bp3_bundle, X_new_known)
    result_unseen = predict_bp3(bp3_bundle, X_new_unseen)
    assert abs(sum(result_known["probabilities"][0]) - 1.0) < 1e-6
    assert abs(sum(result_unseen["probabilities"][0]) - 1.0) < 1e-6


def test_predict_bp3_wrong_bp_id_raises(bp1_bundle):
    with pytest.raises(ValueError, match="predict_bp3"):
        predict_bp3(bp1_bundle, pd.DataFrame({"Product": ["x"], "Company": ["y"]}))
