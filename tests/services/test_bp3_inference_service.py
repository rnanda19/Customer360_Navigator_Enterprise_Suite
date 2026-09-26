"""
tests/services/test_bp3_inference_service.py — Customer360 Navigator

Tests for src/services/bp3_inference_service.py (Hardening Step 3). Mirrors
test_bp2_inference_service.py's two-layer structure (see that file's docstring for the rationale):
synthetic-fixture tests build a tiny real, fitted BP3-shaped dict bundle (OneHotEncoder
ColumnTransformer + a company-frequency map + a binary classifier, NO label_encoder - BP3's real
target is already 0/1) in-process, persist it with the real save_model_bundle(), and drive the real
FastAPI app end-to-end; one real-artifact integration test is skipped (not failed) when the real
BP3 champion bundle from Hardening Step 2 is not present.

BP3's request schema is built dynamically from FEATURE_COLS_CATEGORICAL + COMPANY_COL (real column
names with spaces/hyphens, e.g. "Sub-product") - same pattern as BP2's tests, exercised directly
rather than hand-typing a second, possibly-stale copy of the field list. BP3's response shape is
binary (predicted_label 0/1 + probability_positive_class + confidence), not BP1's/BP2's ranked
top-3 label list - these tests assert against that real, different shape.
"""

from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder

from features.bp3_escalation_features import COMPANY_COL, FEATURE_COLS_CATEGORICAL
from models.model_persistence import save_model_bundle
from services.service_common import resolve_project_root

MODULE_PATH = "services.bp3_inference_service"
TEST_API_KEY = "test-api-key-for-ci"

_REAL_COLS = list(FEATURE_COLS_CATEGORICAL) + [COMPANY_COL]


def _build_synthetic_bp3_bundle_file(tmp_path):
    """Fits a tiny real binary BP3-shaped dict bundle on synthetic structured rows, using the
    project's REAL feature-column constants so the request schema built by the service (from those
    same constants) lines up with what the fitted preprocessor expects - persisted via the real
    save_model_bundle(). No label_encoder key - BP3's real target is already binary 0/1, never a
    LabelEncoder output (see model_persistence.py's module docstring)."""
    n_rows = 8
    rng = np.random.default_rng(0)
    data = {col: rng.choice(["value_a", "value_b"], size=n_rows) for col in FEATURE_COLS_CATEGORICAL}
    data[COMPANY_COL] = ["Acme Bank", "Beta Bank"] * (n_rows // 2)
    X_raw = pd.DataFrame(data)
    y = np.array([0, 1] * (n_rows // 2))

    company_freq_map = X_raw[COMPANY_COL].value_counts(normalize=True).to_dict()
    X_company_freq = X_raw[[COMPANY_COL]].assign(
        **{f"{COMPANY_COL}_freq": X_raw[COMPANY_COL].map(company_freq_map)}
    )[[f"{COMPANY_COL}_freq"]]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore"),
                list(FEATURE_COLS_CATEGORICAL),
            )
        ],
        remainder="drop",
    )
    X_ohe = preprocessor.fit_transform(X_raw[list(FEATURE_COLS_CATEGORICAL)])
    X_ohe_dense = X_ohe.toarray() if hasattr(X_ohe, "toarray") else np.asarray(X_ohe)
    X_full = np.hstack([X_ohe_dense, X_company_freq.to_numpy()])

    classifier = LogisticRegression(max_iter=1000).fit(X_full, y)

    bundle = {
        "bp_id": "bp3",
        "champion_name": "logistic_regression_synthetic",
        "preprocessor": preprocessor,
        "company_freq_map": company_freq_map,
        "feature_cols_categorical": list(FEATURE_COLS_CATEGORICAL),
        "company_col": COMPANY_COL,
        "classifier": classifier,
        "class_names": ["0", "1"],
        "needs_dense": True,
        "metadata": {"synthetic_fixture": True},
    }
    joblib_path = tmp_path / "bp3_synthetic.joblib"
    save_model_bundle(bundle, joblib_path)
    return joblib_path


def _sample_item_payload(company: str = "Acme Bank") -> dict:
    payload = {col: "value_a" for col in FEATURE_COLS_CATEGORICAL}
    payload[COMPANY_COL] = company
    return payload


@pytest.fixture()
def service_module():
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    return importlib.import_module(MODULE_PATH)


@pytest.fixture()
def loaded_client(tmp_path, monkeypatch, service_module):
    joblib_path = _build_synthetic_bp3_bundle_file(tmp_path)
    monkeypatch.setattr(service_module, "_default_joblib_path", lambda: joblib_path)
    monkeypatch.setattr(
        service_module,
        "_default_metadata_path",
        lambda: tmp_path / "does_not_exist.json",
    )
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        yield client


@pytest.fixture()
def unloaded_client(tmp_path, monkeypatch, service_module):
    monkeypatch.setattr(service_module, "_default_joblib_path", lambda: tmp_path / "missing.joblib")
    monkeypatch.setattr(service_module, "_default_metadata_path", lambda: tmp_path / "missing_meta.json")
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        yield client


# ---------------------------------------------------------------------------
# Synthetic-fixture tests
# ---------------------------------------------------------------------------


def test_root_lists_required_fields(loaded_client):
    response = loaded_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bp3_complaint_escalation_prediction"
    assert set(body["required_fields"]) == set(_REAL_COLS)


def test_health_ok_when_model_loaded(loaded_client):
    response = loaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bp_id"] == "bp3"
    assert body["champion_model"] == "logistic_regression_synthetic"


def test_predict_known_company_returns_sensible_response(loaded_client):
    response = loaded_client.post("/predict", json={"items": [_sample_item_payload("Acme Bank")]})
    assert response.status_code == 200
    body = response.json()
    assert body["decision_threshold"] == 0.5
    assert len(body["predictions"]) == 1
    prediction = body["predictions"][0]
    assert prediction["predicted_label"] in (0, 1)
    assert 0.0 <= prediction["probability_positive_class"] <= 1.0
    assert 0.0 <= prediction["confidence"] <= 1.0
    # confidence must be max(p, 1-p), never simply the positive-class probability
    p = prediction["probability_positive_class"]
    assert abs(prediction["confidence"] - max(p, 1 - p)) < 1e-6


def test_predict_unseen_company_uses_zero_frequency_fallback(loaded_client):
    """Real behavior established in Step 2/Step 3 smoke testing: a company never seen during
    training must not error - predict_bp3's fallback maps it to frequency 0, never a fabricated
    or guessed frequency."""
    response = loaded_client.post(
        "/predict",
        json={"items": [_sample_item_payload("Totally Fictional Company XYZ")]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["predictions"]) == 1
    assert body["predictions"][0]["predicted_label"] in (0, 1)


def test_predict_batch_of_multiple_items(loaded_client):
    response = loaded_client.post(
        "/predict",
        json={
            "items": [
                _sample_item_payload("Acme Bank"),
                _sample_item_payload("Beta Bank"),
            ]
        },
    )
    assert response.status_code == 200
    assert len(response.json()["predictions"]) == 2


def test_predict_rejects_empty_batch(loaded_client):
    response = loaded_client.post("/predict", json={"items": []})
    assert response.status_code == 422


def test_predict_rejects_missing_required_field(loaded_client):
    incomplete = _sample_item_payload("Acme Bank")
    first_field = _REAL_COLS[0]
    del incomplete[first_field]
    response = loaded_client.post("/predict", json={"items": [incomplete]})
    assert response.status_code == 422


def test_predict_rejects_blank_required_field(loaded_client):
    payload = _sample_item_payload("Acme Bank")
    payload[_REAL_COLS[0]] = ""
    response = loaded_client.post("/predict", json={"items": [payload]})
    assert response.status_code == 422


def test_predict_rejects_batch_over_max_size(loaded_client):
    response = loaded_client.post("/predict", json={"items": [_sample_item_payload("Acme Bank")] * 101})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Degraded-startup (zero-fabrication) tests
# ---------------------------------------------------------------------------


def test_health_reports_model_not_loaded_when_bundle_missing(unloaded_client):
    response = unloaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "model_not_loaded"
    assert body["bp_id"] == "bp3"
    assert body["error"] is not None
    assert "model_persistence.ipynb" in body["error"]


def test_predict_returns_503_when_bundle_missing(unloaded_client):
    response = unloaded_client.post("/predict", json={"items": [_sample_item_payload("Acme Bank")]})
    assert response.status_code == 503
    assert "not loaded" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Real-artifact integration test (skipped, not failed, if Step 2 hasn't been run for real yet)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_project_root():
    try:
        return resolve_project_root()
    except RuntimeError:
        pytest.skip("Not running inside the Customer360 Navigator project tree - set C360_PROJECT_ROOT.")


def test_real_bp3_champion_bundle_serves_predictions(real_project_root):
    joblib_path = (
        real_project_root / "models" / "bp3_complaint_escalation_prediction" / "bp3_champion_bundle.joblib"
    )
    if not joblib_path.exists():
        pytest.skip(
            "Real BP3 champion bundle not found - run "
            "bp3_complaint_escalation_prediction_model_persistence.ipynb for real first."
        )
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    module = importlib.import_module(MODULE_PATH)
    with TestClient(module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        health = client.get("/health")
        assert health.status_code == 200
        health_body = health.json()
        assert health_body["status"] == "ok"
        assert health_body["fresh_refit_test_pr_auc"] is not None
        assert health_body["fresh_refit_test_accuracy"] is None  # BP3 never reports accuracy

        response = client.get("/")
        real_fields = response.json()["required_fields"]
        payload = {col: "some_real_looking_value" for col in real_fields}

        result = client.post("/predict", json={"items": [payload]})
        assert result.status_code == 200
        body = result.json()
        assert len(body["predictions"]) == 1
        prediction = body["predictions"][0]
        assert prediction["predicted_label"] in (0, 1)
        assert 0.0 <= prediction["probability_positive_class"] <= 1.0
