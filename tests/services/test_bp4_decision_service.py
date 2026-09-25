"""
tests/services/test_bp4_decision_service.py — Customer360 Navigator

Tests for src/services/bp4_decision_service.py (Hardening Step 3). Mirrors
test_bp1_inference_service.py / test_bp2_inference_service.py's two-layer structure (see those
files' docstrings for the rationale): synthetic-fixture tests build a tiny real Parquet artifact
in the exact schema bp4_decision_artifact_persistence.ipynb (Hardening Step 2) produces and drive
the real FastAPI app end-to-end; one real-artifact integration test is skipped (not failed) when
the real BP4 persisted Parquet index from Hardening Step 2 is not present.

BP4 fits no model - there is no "prediction" here, only real read-only lookup/query behavior
(exact-key lookup, tier/company filters, pagination, and the zero-fabrication 503 path when the
artifact has not been persisted for real yet).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

MODULE_PATH = "services.bp4_decision_service"

CLUSTER_KEY = ["Company", "Product", "Sub-product", "Issue", "Sub-issue"]


def _build_synthetic_bp4_parquet(tmp_path: Path) -> Path:
    """Builds a tiny, real, schema-correct Parquet index (same 19 columns, same dtypes, same
    CLUSTER_KEY sort convention as the real Hardening Step 2 notebook produces) - synthetic ROWS,
    real SCHEMA, so the service under test exercises its real parsing/filtering/pagination logic
    end-to-end rather than a hand-mocked stand-in."""
    rows = [
        {
            "Company": "Acme Bank",
            "Product": "Checking or savings account",
            "Sub-product": "Checking account",
            "Issue": "Problem with a lender",
            "Sub-issue": "MISSING_SUB_ISSUE",
            "n_complaints_total": 12,
            "first_complaint_date": "2024-01-01",
            "last_complaint_date": "2024-06-01",
            "n_active_months": 3,
            "avg_response_lag_days": 6.5,
            "banking77_coverage_fraction": 0.2,
            "is_recurring_cluster": True,
            "recurring_flag": True,
            "elevated_lag_flag": True,
            "high_volume_flag": True,
            "review_priority_score": 3,
            "review_priority_tier": "HIGH",
            "reason_codes": "RECURRING|ELEVATED_LAG|HIGH_VOLUME",
            "reason_evidence": "synthetic fixture evidence",
        },
        {
            "Company": "AES/PHEAA",  # real-shaped: '/' in a real company name, live-verified
            "Product": "Student loan",
            "Sub-product": "Federal student loan servicing",
            "Issue": "Dealing with your lender or servicer",
            "Sub-issue": "MISSING_SUB_ISSUE",
            "n_complaints_total": 1,
            "first_complaint_date": "2024-02-01",
            "last_complaint_date": "2024-02-01",
            "n_active_months": 1,
            "avg_response_lag_days": 0.0,
            "banking77_coverage_fraction": 0.0,
            "is_recurring_cluster": False,
            "recurring_flag": False,
            "elevated_lag_flag": False,
            "high_volume_flag": False,
            "review_priority_score": 0,
            "review_priority_tier": "NONE",
            "reason_codes": "",
            "reason_evidence": "",
        },
        {
            "Company": "Beta Bank",
            "Product": "Mortgage",
            "Sub-product": "Conventional home mortgage",
            "Issue": "Struggling to pay",
            "Sub-issue": "MISSING_SUB_ISSUE",
            "n_complaints_total": 5,
            "first_complaint_date": "2024-03-01",
            "last_complaint_date": "2024-04-01",
            "n_active_months": 2,
            "avg_response_lag_days": 1.0,
            "banking77_coverage_fraction": 0.5,
            "is_recurring_cluster": True,
            "recurring_flag": True,
            "elevated_lag_flag": False,
            "high_volume_flag": False,
            "review_priority_score": 1,
            "review_priority_tier": "LOW",
            "reason_codes": "RECURRING",
            "reason_evidence": "synthetic fixture evidence",
        },
    ]
    frame = pl.DataFrame(rows).with_columns(
        [
            pl.col("first_complaint_date").str.strptime(pl.Date, "%Y-%m-%d"),
            pl.col("last_complaint_date").str.strptime(pl.Date, "%Y-%m-%d"),
        ]
    )
    frame = frame.sort(CLUSTER_KEY)
    parquet_path = tmp_path / "bp4_synthetic_index.parquet"
    frame.write_parquet(parquet_path)
    return parquet_path


@pytest.fixture()
def service_module():
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    return importlib.import_module(MODULE_PATH)


@pytest.fixture()
def loaded_client(tmp_path, monkeypatch, service_module):
    parquet_path = _build_synthetic_bp4_parquet(tmp_path)
    monkeypatch.setattr(service_module, "_default_parquet_path", lambda: parquet_path)
    monkeypatch.setattr(service_module, "_default_metadata_path", lambda: tmp_path / "does_not_exist.json")
    with TestClient(service_module.app) as client:
        yield client


@pytest.fixture()
def unloaded_client(tmp_path, monkeypatch, service_module):
    monkeypatch.setattr(service_module, "_default_parquet_path", lambda: tmp_path / "missing.parquet")
    monkeypatch.setattr(service_module, "_default_metadata_path", lambda: tmp_path / "missing_meta.json")
    with TestClient(service_module.app) as client:
        yield client


# ---------------------------------------------------------------------------
# Synthetic-fixture tests
# ---------------------------------------------------------------------------


def test_root_lists_cluster_key_and_tiers(loaded_client):
    response = loaded_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bp4_customer_journey_analytics_decision_records"
    assert body["cluster_key_columns"] == CLUSTER_KEY
    assert set(body["valid_tiers"]) == {"HIGH", "MEDIUM", "LOW", "NONE"}


def test_health_ok_when_artifact_loaded(loaded_client):
    response = loaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bp_id"] == "bp4"
    assert body["n_rows"] == 3


def test_lookup_exact_key_returns_record(loaded_client):
    response = loaded_client.get(
        "/cluster/lookup",
        params={
            "company": "Acme Bank",
            "product": "Checking or savings account",
            "sub_product": "Checking account",
            "issue": "Problem with a lender",
            "sub_issue": "MISSING_SUB_ISSUE",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["review_priority_tier"] == "HIGH"
    assert body["n_complaints_total"] == 12


def test_lookup_company_with_slash_character(loaded_client):
    """Real-shaped edge case: a real 'Company' value containing '/' (e.g. AES/PHEAA) must be
    look-up-able via query parameters without any path-routing ambiguity."""
    response = loaded_client.get(
        "/cluster/lookup",
        params={
            "company": "AES/PHEAA",
            "product": "Student loan",
            "sub_product": "Federal student loan servicing",
            "issue": "Dealing with your lender or servicer",
            "sub_issue": "MISSING_SUB_ISSUE",
        },
    )
    assert response.status_code == 200
    assert response.json()["company"] == "AES/PHEAA"


def test_lookup_unknown_key_returns_404(loaded_client):
    response = loaded_client.get(
        "/cluster/lookup",
        params={
            "company": "Nonexistent Co",
            "product": "x",
            "sub_product": "x",
            "issue": "x",
            "sub_issue": "x",
        },
    )
    assert response.status_code == 404


def test_lookup_rejects_missing_query_param(loaded_client):
    response = loaded_client.get("/cluster/lookup", params={"company": "Acme Bank"})
    assert response.status_code == 422


def test_list_clusters_no_filter_returns_all(loaded_client):
    response = loaded_client.get("/clusters")
    assert response.status_code == 200
    body = response.json()
    assert body["total_matching"] == 3
    assert len(body["items"]) == 3


def test_list_clusters_filters_by_tier(loaded_client):
    response = loaded_client.get("/clusters", params={"tier": "HIGH"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_matching"] == 1
    assert body["items"][0]["review_priority_tier"] == "HIGH"


def test_list_clusters_rejects_invalid_tier(loaded_client):
    response = loaded_client.get("/clusters", params={"tier": "NOT_A_REAL_TIER"})
    assert response.status_code == 422


def test_list_clusters_filters_by_company(loaded_client):
    response = loaded_client.get("/clusters", params={"company": "Beta Bank"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_matching"] == 1
    assert body["items"][0]["company"] == "Beta Bank"


def test_list_clusters_recurring_only_filter(loaded_client):
    response = loaded_client.get("/clusters", params={"recurring_only": True})
    assert response.status_code == 200
    body = response.json()
    assert body["total_matching"] == 2
    assert all(item["is_recurring_cluster"] for item in body["items"])


def test_list_clusters_pagination(loaded_client):
    page1 = loaded_client.get("/clusters", params={"limit": 2, "offset": 0}).json()
    page2 = loaded_client.get("/clusters", params={"limit": 2, "offset": 2}).json()
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 1
    assert page1["total_matching"] == page2["total_matching"] == 3


def test_list_clusters_by_tier_path_endpoint(loaded_client):
    response = loaded_client.get("/clusters/tiers/LOW")
    assert response.status_code == 200
    body = response.json()
    assert body["total_matching"] == 1
    assert body["items"][0]["review_priority_tier"] == "LOW"


def test_list_clusters_rejects_limit_over_max(loaded_client):
    response = loaded_client.get("/clusters", params={"limit": 5000})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Degraded-startup (zero-fabrication) tests
# ---------------------------------------------------------------------------


def test_health_reports_artifact_not_loaded_when_parquet_missing(unloaded_client):
    response = unloaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "artifact_not_loaded"
    assert body["bp_id"] == "bp4"
    assert body["error"] is not None
    assert "decision_artifact_persistence.ipynb" in body["error"]


def test_lookup_returns_503_when_parquet_missing(unloaded_client):
    response = unloaded_client.get(
        "/cluster/lookup",
        params={"company": "x", "product": "x", "sub_product": "x", "issue": "x", "sub_issue": "x"},
    )
    assert response.status_code == 503
    assert "not loaded" in response.json()["detail"]


def test_list_returns_503_when_parquet_missing(unloaded_client):
    response = unloaded_client.get("/clusters")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Real-artifact integration test (skipped, not failed, if Step 2 hasn't been run for real yet)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_project_root():
    from services.bp4_decision_service import resolve_project_root

    try:
        return resolve_project_root()
    except RuntimeError:
        pytest.skip("Not running inside the Customer360 Navigator project tree - set C360_PROJECT_ROOT.")


def test_real_bp4_decision_artifact_serves_queries(real_project_root):
    parquet_path = (
        real_project_root
        / "models"
        / "bp4_customer_journey_analytics"
        / "bp4_decision_artifact_index.parquet"
    )
    if not parquet_path.exists():
        pytest.skip(
            "Real BP4 decision-artifact Parquet index not found - run "
            "bp4_customer_journey_analytics_decision_artifact_persistence.ipynb for real first."
        )
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    module = importlib.import_module(MODULE_PATH)
    with TestClient(module.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["n_rows"] > 0

        listing = client.get("/clusters", params={"limit": 1})
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert len(items) == 1
        real_row = items[0]

        lookup = client.get(
            "/cluster/lookup",
            params={
                "company": real_row["company"],
                "product": real_row["product"],
                "sub_product": real_row["sub_product"],
                "issue": real_row["issue"],
                "sub_issue": real_row["sub_issue"],
            },
        )
        assert lookup.status_code == 200
        assert lookup.json()["review_priority_tier"] == real_row["review_priority_tier"]
