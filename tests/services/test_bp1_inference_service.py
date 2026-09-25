"""
tests/services/test_bp1_inference_service.py — Customer360 Navigator

Tests for src/services/bp1_inference_service.py (Hardening Step 3). Two layers, mirroring this
project's established test style (see tests/shared/test_model_persistence.py for the synthetic-
fixture pattern and tests/bp1_customer_intent_classification/test_gate_artifacts.py for the real-
artifact skip-if-missing pattern):

1. Synthetic-fixture tests (the majority) - build a tiny real, fitted sklearn Pipeline in-process,
   persist it with the real save_model_bundle(), point the service at that temp file via
   monkeypatch, and drive the real FastAPI app end-to-end through its real lifespan startup and
   TestClient. No mocking of predict_bp1, load_model_bundle, or any service logic - only the
   *location* of the model file is swapped, so these tests exercise the actual code path a real
   deployment runs. CI-safe: needs no real project artifacts.

2. One real-artifact integration test, skipped (not failed) when the real BP1 champion bundle
   from Hardening Step 2 is not present on disk - the same skip-if-missing discipline
   test_gate_artifacts.py already established for this project, applied to the service layer.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from models.model_persistence import save_model_bundle
from services.service_common import resolve_project_root

MODULE_PATH = "services.bp1_inference_service"


def _build_synthetic_bp1_bundle_file(tmp_path):
    """Fits a tiny real 2-class Pipeline on synthetic text and persists it via the real
    save_model_bundle() - this is a genuinely loadable bundle, not a stub or a mock."""
    texts = [
        "my card was lost please block it",
        "card was stolen yesterday",
        "i want to transfer money to another account",
        "please process my pending transfer",
    ]
    labels = [
        "lost_or_stolen_card",
        "lost_or_stolen_card",
        "transfer_issue",
        "transfer_issue",
    ]
    label_encoder = LabelEncoder().fit(labels)
    y = label_encoder.transform(labels)
    pipeline = Pipeline([("tfidf", TfidfVectorizer()), ("clf", LogisticRegression(max_iter=1000))])
    pipeline.fit(texts, y)
    bundle = {
        "bp_id": "bp1",
        "champion_name": "logistic_regression",
        "pipeline": pipeline,
        "label_encoder": label_encoder,
        "class_names": list(label_encoder.classes_),
        "metadata": {"synthetic_fixture": True},
    }
    joblib_path = tmp_path / "bp1_synthetic.joblib"
    save_model_bundle(bundle, joblib_path)
    return joblib_path


@pytest.fixture()
def service_module():
    """A fresh import of the service module per test, so monkeypatching its module-level
    _default_joblib_path/_default_metadata_path (below) never leaks between tests via a cached
    module object with a stale _handle."""
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    return importlib.import_module(MODULE_PATH)


@pytest.fixture()
def loaded_client(tmp_path, monkeypatch, service_module):
    """A TestClient whose lifespan startup loads a real, synthetic, fitted bundle - exercises the
    actual ModelBundleHandle -> load_model_bundle -> predict_bp1 path end-to-end."""
    joblib_path = _build_synthetic_bp1_bundle_file(tmp_path)
    monkeypatch.setattr(service_module, "_default_joblib_path", lambda: joblib_path)
    monkeypatch.setattr(
        service_module,
        "_default_metadata_path",
        lambda: tmp_path / "does_not_exist.json",
    )
    with TestClient(service_module.app) as client:
        yield client


@pytest.fixture()
def unloaded_client(tmp_path, monkeypatch, service_module):
    """A TestClient whose lifespan startup points at a joblib path that does not exist - exercises
    the zero-fabrication degraded-startup path (service starts, /health reports the problem,
    /predict returns 503) rather than mocking a missing-model condition."""
    monkeypatch.setattr(service_module, "_default_joblib_path", lambda: tmp_path / "missing.joblib")
    monkeypatch.setattr(service_module, "_default_metadata_path", lambda: tmp_path / "missing_meta.json")
    with TestClient(service_module.app) as client:
        yield client


# ---------------------------------------------------------------------------
# Synthetic-fixture tests
# ---------------------------------------------------------------------------


def test_root_lists_endpoints(loaded_client):
    response = loaded_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bp1_customer_intent_classification"
    assert body["predict"] == "/predict"


def test_health_ok_when_model_loaded(loaded_client):
    response = loaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bp_id"] == "bp1"
    assert body["champion_model"] == "logistic_regression"


def test_predict_returns_sensible_top3(loaded_client):
    response = loaded_client.post("/predict", json={"texts": ["my card was lost please block it"]})
    assert response.status_code == 200
    body = response.json()
    assert body["champion_model"] == "logistic_regression"
    assert body["n_classes"] == 2
    assert len(body["predictions"]) == 1
    prediction = body["predictions"][0]
    assert prediction["predicted_label"] == "lost_or_stolen_card"
    assert 0.0 <= prediction["confidence"] <= 1.0
    # Top-3 padding: with only 2 real classes, rank2/rank3 must still be populated (padded, not
    # missing) per top3_from_proba's documented behavior.
    assert prediction["rank2_label"] in {"lost_or_stolen_card", "transfer_issue"}
    assert prediction["rank3_label"] in {"lost_or_stolen_card", "transfer_issue"}


def test_predict_batch_of_multiple_texts(loaded_client):
    response = loaded_client.post(
        "/predict",
        json={"texts": ["card was stolen yesterday", "please process my pending transfer"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["predictions"]) == 2
    assert body["predictions"][0]["text"] == "card was stolen yesterday"
    assert body["predictions"][1]["text"] == "please process my pending transfer"


def test_predict_rejects_empty_batch(loaded_client):
    response = loaded_client.post("/predict", json={"texts": []})
    assert response.status_code == 422


def test_predict_rejects_blank_text(loaded_client):
    response = loaded_client.post("/predict", json={"texts": ["   "]})
    assert response.status_code == 422


def test_predict_rejects_batch_over_max_size(loaded_client):
    response = loaded_client.post("/predict", json={"texts": ["hello"] * 101})
    assert response.status_code == 422


def test_predict_rejects_missing_texts_field(loaded_client):
    response = loaded_client.post("/predict", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Degraded-startup (zero-fabrication) tests
# ---------------------------------------------------------------------------


def test_health_reports_model_not_loaded_when_bundle_missing(unloaded_client):
    response = unloaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "model_not_loaded"
    assert body["bp_id"] == "bp1"
    assert body["error"] is not None
    assert "model_persistence.ipynb" in body["error"]


def test_predict_returns_503_when_bundle_missing(unloaded_client):
    response = unloaded_client.post("/predict", json={"texts": ["my card was lost"]})
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


def test_real_bp1_champion_bundle_serves_predictions(real_project_root):
    joblib_path = (
        real_project_root / "models" / "bp1_customer_intent_classification" / "bp1_champion_pipeline.joblib"
    )
    if not joblib_path.exists():
        pytest.skip(
            "Real BP1 champion bundle not found - run "
            "bp1_customer_intent_classification_model_persistence.ipynb for real first."
        )
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    module = importlib.import_module(MODULE_PATH)
    with TestClient(module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        response = client.post("/predict", json={"texts": ["my card was lost, please block it"]})
        assert response.status_code == 200
        body = response.json()
        assert body["n_classes"] > 0
        assert len(body["predictions"]) == 1
        prediction = body["predictions"][0]
        # The specific label is real-model-dependent (the actual trained BANKING77 champion), so
        # this checks the response is well-formed and non-empty rather than asserting a specific
        # class - that would be re-testing the already-verified Step 2 notebook, not this service.
        assert prediction["predicted_label"]
        assert 0.0 <= prediction["confidence"] <= 1.0
