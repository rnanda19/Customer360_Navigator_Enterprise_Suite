"""
tests/services/test_bp5_driver_service.py — Customer360 Navigator

Tests for src/services/bp5_driver_service.py (BP5 hardening pass). Mirrors
test_bp4_decision_service.py's / test_bp6_resolution_service.py's two-layer structure (see those
files' docstrings for the rationale): synthetic-fixture tests build tiny, real-schema Gate 5
report JSON + Gate 7 rollup manifest files and drive the real FastAPI app end-to-end; one
real-artifact integration test is skipped (not failed) when BP5's real committed Gate 5/Gate 7
artifacts are not present in this checkout.

BP5 fits no supervised classifier for a decision boundary and makes no GenAI call - there is no
"prediction" and no external API call here, only real read-only reporting behavior (per-outcome
Gate 5 report lookup, the Gate 7 rollup, and the zero-fabrication 503 path when an artifact is
missing).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MODULE_PATH = "services.bp5_driver_service"
TEST_API_KEY = "test-api-key-for-ci"

OUTCOME_1 = "outcome_1_intervention_required"
OUTCOME_2 = "outcome_2_timely_response_failure"


def _synthetic_report(outcome_field: str) -> dict:
    """Real-schema, synthetic-VALUE Gate 5 prioritized root-cause report - same top-level keys as
    BP5's own real gate5_prioritized_root_cause_report_outcome_*.json artifacts (live-verified
    against both real outcome files), synthetic numbers only."""
    return {
        "outcome_field": outcome_field,
        "association_not_causation_disclaimer": (
            "This is a statistical ASSOCIATION finding between a real candidate driver field and "
            "a real outcome field - never a causal claim."
        ),
        "field_level_ranking": [
            {
                "rank": 1,
                "driver_field": "Sub-issue",
                "cramers_v": 0.41,
                "association_strength": "moderate",
                "chi2_statistic": 1000.0,
                "degrees_of_freedom": 10,
                "p_value": 0.0,
                "n_rows_tested": 100,
                "n_distinct_levels": 5,
                "citation": {"source_bp": "bp5", "source_gate": "gate3"},
            }
        ],
        "category_level_findings_by_field": {
            "Sub-issue": [
                {
                    "rank": 1,
                    "driver_field": "Sub-issue",
                    "category": "Problem with fees",
                    "reference_category": "Other",
                    "n_rows": 10,
                    "n_outcome_positive": 4,
                    "n_outcome_negative": 6,
                    "odds_ratio_vs_reference": 2.0,
                    "log_odds_ratio": 0.69,
                    "ci_95_low": 1.0,
                    "ci_95_high": 4.0,
                    "p_value": 0.01,
                    "continuity_correction_applied": False,
                    "citation": {"source_bp": "bp5", "source_gate": "gate3"},
                }
            ]
        },
        "champion_shap_feature_importance": [
            {"feature": "Sub-issue_Problem with fees", "mean_abs_shap": 0.05}
        ],
        "company_process_field_finding": {
            "driver_field": "Company",
            "encoding": "frequency_zscored",
            "odds_ratio_per_1sd": 1.5,
            "ci_95_low_odds_ratio_per_1sd": 1.2,
            "ci_95_high_odds_ratio_per_1sd": 1.9,
            "p_value": 0.001,
            "converged": True,
            "citation": {"source_bp": "bp5", "source_gate": "gate3"},
        },
        "champion_validation_snapshot": {
            "held_out_roc_auc": 0.95,
            "held_out_pr_auc": 0.07,
            "bootstrap_roc_auc_ci_95": [0.94, 0.96],
            "bootstrap_pr_auc_ci_95": [0.05, 0.09],
            "brier_score": 0.1,
            "confusion_matrix_at_0_5": {
                "recall": 0.97,
                "precision": 0.02,
                "false_positive_rate": 0.15,
                "selection_rate": 0.16,
            },
            "interpretation_note": "synthetic fixture note",
            "citations": [],
        },
        "barred_field_governance_disclosures": {
            "timely_response_vs_outcome_1": {},
            "response_duration_days_vs_outcomes": {},
            "company_response_to_consumer_vs_outcome_2": {},
            "bar_relaxed_by_this_notebook": False,
            "disclosure": "synthetic fixture disclosure",
        },
        "narrative_text": {
            "field_level": "synthetic field-level narrative",
            "category_level": "synthetic category-level narrative",
            "shap_level": "synthetic shap-level narrative",
        },
        "min_n_per_category_threshold_used": 30,
        "top_k_fields": 5,
        "top_k_categories_per_field": 5,
        "top_k_shap_features": 10,
    }


def _synthetic_rollup() -> dict:
    """Real-schema, synthetic-VALUE Gate 7 executive rollup manifest - same top-level keys as
    BP5's own real executive_rollup_manifest.json (live-verified), synthetic numbers only."""
    return {
        "bp_id": "bp5",
        "gate": 7,
        "report_name": "BP5 Root-Cause & Driver Analytics - Executive Rollup",
        "outcomes": [OUTCOME_1, OUTCOME_2],
        "production_recommendation_tier": "Recommended for Decision-Support Use, With Monitoring",
        "production_recommendation_tier_code": 2,
        "ecoa_reg_b_disparate_impact_applicability": "NOT_APPLICABLE",
        "output_paths": {"dashboard_html": "reports/bp5_root_cause_driver_analytics/x.html"},
        "output_sizes_bytes": {"dashboard_html": 100},
        "contains_financial_impact_section": False,
        "contains_assumption_based_content": False,
        "n_negligible_strength_fields_detected": 2,
        "n_near_zero_precision_outcomes_detected": 1,
        "association_not_causation_disclaimer_carried_forward": True,
        "generated_at_utc": "2026-09-24T11:23:27.353785+00:00",
    }


def _build_synthetic_artifacts_dir(tmp_path: Path) -> Path:
    artifacts_dir = tmp_path / "notebooks" / "bp5_root_cause_driver_analytics" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    filenames = {
        OUTCOME_1: "gate5_prioritized_root_cause_report_outcome_1_intervention_required.json",
        OUTCOME_2: "gate5_prioritized_root_cause_report_outcome_2_timely_response_failure.json",
    }
    for outcome, filename in filenames.items():
        with open(artifacts_dir / filename, "w", encoding="utf-8") as f:
            json.dump(_synthetic_report(outcome), f)
    with open(artifacts_dir / "executive_rollup_manifest.json", "w", encoding="utf-8") as f:
        json.dump(_synthetic_rollup(), f)
    return artifacts_dir


@pytest.fixture()
def service_module():
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    return importlib.import_module(MODULE_PATH)


@pytest.fixture()
def loaded_client(tmp_path, monkeypatch, service_module):
    artifacts_dir = _build_synthetic_artifacts_dir(tmp_path)
    monkeypatch.setattr(service_module, "_default_artifacts_dir", lambda: artifacts_dir)
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        yield client


@pytest.fixture()
def unloaded_client(tmp_path, monkeypatch, service_module):
    monkeypatch.setattr(service_module, "_default_artifacts_dir", lambda: tmp_path / "missing")
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        yield client


# ---------------------------------------------------------------------------
# Synthetic-fixture tests
# ---------------------------------------------------------------------------


def test_root_lists_endpoints_and_valid_outcomes(loaded_client):
    response = loaded_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bp5_root_cause_driver_analytics_reporting"
    assert set(body["valid_outcomes"]) == {OUTCOME_1, OUTCOME_2}


def test_health_ok_when_both_outcomes_loaded(loaded_client):
    response = loaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["bp_id"] == "bp5"
    assert body["outcomes_loaded"] == {OUTCOME_1: True, OUTCOME_2: True}
    assert body["rollup_loaded"] is True
    assert body["n_outcomes_loaded"] == 2
    assert body["generated_at_utc"] == "2026-09-24T11:23:27.353785+00:00"


def test_outcomes_endpoint(loaded_client):
    response = loaded_client.get("/outcomes")
    assert response.status_code == 200
    body = response.json()
    assert set(body["valid_outcomes"]) == {OUTCOME_1, OUTCOME_2}
    assert body["outcomes_loaded"][OUTCOME_1] is True


def test_get_report_returns_real_shaped_report(loaded_client):
    response = loaded_client.get(f"/report/{OUTCOME_1}")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome_field"] == OUTCOME_1
    assert "never a causal claim" in body["association_not_causation_disclaimer"]
    assert body["field_level_ranking"][0]["driver_field"] == "Sub-issue"
    assert "Sub-issue" in body["category_level_findings_by_field"]
    assert body["champion_validation_snapshot"]["held_out_roc_auc"] == 0.95


def test_get_report_rejects_invalid_outcome(loaded_client):
    response = loaded_client.get("/report/not_a_real_outcome")
    assert response.status_code == 422


def test_get_top_drivers_subset(loaded_client):
    response = loaded_client.get(f"/report/{OUTCOME_2}/top-drivers")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome_field"] == OUTCOME_2
    assert set(body.keys()) == {
        "outcome_field",
        "association_not_causation_disclaimer",
        "field_level_ranking",
    }


def test_get_rollup_returns_real_shaped_manifest(loaded_client):
    response = loaded_client.get("/rollup")
    assert response.status_code == 200
    body = response.json()
    assert body["bp_id"] == "bp5"
    assert body["gate"] == 7
    assert set(body["outcomes"]) == {OUTCOME_1, OUTCOME_2}
    assert body["association_not_causation_disclaimer_carried_forward"] is True


# ---------------------------------------------------------------------------
# Degraded-startup (zero-fabrication) tests
# ---------------------------------------------------------------------------


def test_health_reports_artifact_not_loaded_when_all_missing(unloaded_client):
    response = unloaded_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "artifact_not_loaded"
    assert body["n_outcomes_loaded"] == 0
    assert body["rollup_loaded"] is False
    assert OUTCOME_1 in body["errors"]
    assert "rollup" in body["errors"]


def test_get_report_returns_503_when_missing(unloaded_client):
    response = unloaded_client.get(f"/report/{OUTCOME_1}")
    assert response.status_code == 503
    assert "not loaded" in response.json()["detail"]


def test_get_rollup_returns_503_when_missing(unloaded_client):
    response = unloaded_client.get("/rollup")
    assert response.status_code == 503


def test_health_partially_loaded_when_only_one_outcome_present(tmp_path, monkeypatch, service_module):
    artifacts_dir = tmp_path / "notebooks" / "bp5_root_cause_driver_analytics" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    with open(
        artifacts_dir / "gate5_prioritized_root_cause_report_outcome_1_intervention_required.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(_synthetic_report(OUTCOME_1), f)
    monkeypatch.setattr(service_module, "_default_artifacts_dir", lambda: artifacts_dir)
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partially_loaded"
    assert body["n_outcomes_loaded"] == 1
    assert body["outcomes_loaded"] == {OUTCOME_1: True, OUTCOME_2: False}


# ---------------------------------------------------------------------------
# Real-artifact integration test (skipped, not failed, if BP5's real Gate 5/Gate 7 artifacts are
# not present in this checkout)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_project_root():
    from services.bp5_driver_service import resolve_project_root

    try:
        return resolve_project_root()
    except RuntimeError:
        pytest.skip("Not running inside the Customer360 Navigator project tree - set C360_PROJECT_ROOT.")


def test_real_bp5_reports_serve_queries(real_project_root):
    artifacts_dir = real_project_root / "notebooks" / "bp5_root_cause_driver_analytics" / "artifacts"
    report_path = artifacts_dir / "gate5_prioritized_root_cause_report_outcome_1_intervention_required.json"
    rollup_path = artifacts_dir / "executive_rollup_manifest.json"
    if not report_path.exists() or not rollup_path.exists():
        pytest.skip(
            "Real BP5 Gate 5/Gate 7 artifacts not found - run BP5's Gate 5 and Gate 7 notebooks "
            "for real first."
        )
    if MODULE_PATH in importlib.sys.modules:
        del importlib.sys.modules[MODULE_PATH]
    module = importlib.import_module(MODULE_PATH)
    with TestClient(module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["n_outcomes_loaded"] == 2

        report = client.get(f"/report/{OUTCOME_1}")
        assert report.status_code == 200
        assert report.json()["outcome_field"] == OUTCOME_1
        assert len(report.json()["field_level_ranking"]) > 0

        rollup = client.get("/rollup")
        assert rollup.status_code == 200
        assert rollup.json()["bp_id"] == "bp5"
