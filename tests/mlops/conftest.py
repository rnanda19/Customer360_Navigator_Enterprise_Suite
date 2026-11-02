"""
tests/mlops/conftest.py — Customer360 Navigator

Shared fixtures for the Phase D MLOps test suite. Every test that touches MLflow tracking or the
Model Registry gets its own fresh, isolated sqlite-backed store under pytest's tmp_path - never
the real repo-root mlruns/ directory this project's actual training runs use, and never shared
state between tests.
"""

from __future__ import annotations

import uuid

import mlflow
import pytest


@pytest.fixture
def mlflow_tracking_uri(tmp_path, monkeypatch):
    """Point MLflow (and src/mlops/registry.py, which reads MLFLOW_TRACKING_URI) at a fresh
    temp sqlite file for the duration of one test."""
    uri = f"sqlite:///{tmp_path / 'test_mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    yield uri


@pytest.fixture
def logged_run(mlflow_tracking_uri):
    """A real MLflow run with a real logged sklearn artifact (a tiny LogisticRegression fit on
    synthetic data) - returns (run_id, artifact_subpath) for registry tests to register against.
    Synthetic data here is appropriate: these tests exercise registry/promotion MECHANICS, not
    BP1's real accuracy (that is covered separately and for real by
    scripts/mlops/bp1_train_and_register.py against the real BANKING77 data)."""
    import joblib
    from sklearn.linear_model import LogisticRegression

    mlflow.set_experiment(f"test_experiment_{uuid.uuid4().hex[:8]}")
    with mlflow.start_run() as run:
        clf = LogisticRegression().fit([[0], [1], [2], [3]], [0, 0, 1, 1])
        local_path = run.info.run_id + "_model.joblib"
        joblib.dump(clf, local_path)
        mlflow.log_artifact(local_path, artifact_path="model")
        import os

        os.remove(local_path)
        run_id = run.info.run_id
    return run_id, "model/" + local_path
