"""
tests/services/test_bp7_decision_engine_service.py — Customer360 Navigator

Tests for src/services/bp7_decision_engine_service.py (BP7 Gate 6 — Master Plan paragraph 205's
mandatory BP6/BP7 FastAPI-service-with-live-self-test deliverable). Mirrors
test_bp4_decision_service.py's synthetic-fixture-drives-the-real-app structure (see that file's
docstring for the rationale), adapted for BP7's shape: a real, persisted, full-population CSV
(never a Parquet index), no model bundle, and NO external network call anywhere (BP7 makes none -
contrast test_bp6_resolution_service.py, whose self-test mocks a real Gemini call boundary; BP7's
own self-test below makes no such mock because there is no external call to mock).

Two-layer structure:
  1. Synthetic-fixture tests (below) build a tiny, real-schema Gate 5 CSV + summary JSON under
     `tmp_path` (same 19 `FINAL_OUTPUT_COLUMNS` the real Hardening/Gate 5 notebook writes) and
     drive the real FastAPI app end-to-end.
  2. One real-artifact integration test, skipped (not failed) when this is not running inside the
     real project tree with BP7 Gate 5 already real-run.
"""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MODULE_PATH = "services.bp7_decision_engine_service"
TEST_API_KEY = "test-api-key-for-ci"

FINAL_OUTPUT_COLUMNS = [
    "Complaint ID",
    "priority_score",
    "intervention_flag",
    "recommended_action",
    "reason_codes",
    "contribution_bp2",
    "contribution_bp3",
    "contribution_bp4",
    "bp2_predicted_label",
    "bp2_confidence",
    "bp3_predicted_label",
    "bp3_probability_positive_class",
    "bp4_review_priority_tier",
    "bp4_review_priority_score",
    "bp4_join_status",
    "bp1_context_status",
    "bp5_outcome_1_context",
    "bp5_outcome_2_context",
    "tags_group",
]


def _row(
    complaint_id: int,
    priority_score,
    intervention_flag: bool,
    recommended_action: str,
    reason_codes: str,
    contribution_bp2="",
    contribution_bp3="",
    contribution_bp4="",
    bp4_review_priority_tier="MEDIUM",
    bp4_review_priority_score=2,
    bp4_join_status="BP4_JOINED",
) -> dict:
    return {
        "Complaint ID": complaint_id,
        "priority_score": "" if priority_score is None else priority_score,
        "intervention_flag": str(intervention_flag).lower(),
        "recommended_action": recommended_action,
        "reason_codes": reason_codes,
        "contribution_bp2": contribution_bp2,
        "contribution_bp3": contribution_bp3,
        "contribution_bp4": contribution_bp4,
        "bp2_predicted_label": "MEDIUM_HIGH_FRICTION",
        "bp2_confidence": 0.7,
        "bp3_predicted_label": "NO_ESCALATE",
        "bp3_probability_positive_class": 0.1,
        "bp4_review_priority_tier": bp4_review_priority_tier,
        "bp4_review_priority_score": bp4_review_priority_score,
        "bp4_join_status": bp4_join_status,
        "bp1_context_status": "BP1_NO_TAXONOMY_MAPPING",
        "bp5_outcome_1_context": "NOT_IN_TOP_K_ASSOCIATION_LIST",
        "bp5_outcome_2_context": "NOT_IN_TOP_K_ASSOCIATION_LIST",
        "tags_group": "NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED",
    }


def _build_synthetic_prerequisites(tmp_path: Path) -> None:
    """Real-schema, synthetic-value fixtures: a tiny Gate 5 records CSV (same 19
    FINAL_OUTPUT_COLUMNS, same column order, as the real Gate 5 notebook writes) covering a
    flagged/recurring row, a non-flagged row, and a real, structurally-honest unscored row (null
    priority_score - BP7's own real UNSCORED_MISSING_UPSTREAM_INPUT sentinel path), plus a real-
    schema summary JSON."""
    artifacts_dir = tmp_path / "notebooks" / "bp7_customer_navigator_decision_engine" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        _row(
            1001,
            0.62,
            True,
            "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
            "BP2_TIER=HIGH_FRICTION|BP4_TIER=HIGH|BP4_RECURRING",
            contribution_bp2=0.2,
            contribution_bp3=0.1,
            contribution_bp4=0.32,
            bp4_review_priority_tier="HIGH",
            bp4_review_priority_score=3,
        ),
        _row(
            1002,
            0.21,
            False,
            "STANDARD_QUEUE",
            "BP2_TIER=LOW_FRICTION|BP4_TIER=LOW",
            contribution_bp2=0.05,
            contribution_bp3=0.02,
            contribution_bp4=0.14,
            bp4_review_priority_tier="LOW",
            bp4_review_priority_score=0,
        ),
        _row(
            1003,
            None,
            False,
            "UNSCORED_MISSING_UPSTREAM_INPUT",
            "BP4_TIER=UNSCORED|BP1_CONTEXT=BP1_NO_TAXONOMY_MAPPING",
            bp4_review_priority_tier="",
            bp4_review_priority_score="",
            bp4_join_status="UNSCORED_MISSING_UPSTREAM_INPUT",
        ),
    ]
    csv_path = artifacts_dir / "gate5_full_population_decision_records.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FINAL_OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    summary = {
        "bp_id": "bp7",
        "gate": 5,
        "generated_at_utc": "2026-09-25T00:00:00+00:00",
        "live_row_count": 3,
        "champion_rule_scheme": "correlation_aware_plus_lr_diagnostic",
        "champion_weights_normalized": {"bp2": 0.222714, "bp3": 0.170774, "bp4": 0.606512},
        "intervention_threshold": 0.5,
    }
    with open(artifacts_dir / "gate5_decision_layer_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f)

    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").touch()


@pytest.fixture()
def service_module():
    import services.bp7_decision_engine_service as svc

    importlib.reload(svc)
    return svc


@pytest.fixture()
def configured_client(tmp_path, monkeypatch, service_module):
    _build_synthetic_prerequisites(tmp_path)
    monkeypatch.setattr(service_module, "resolve_project_root", lambda: tmp_path)
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        yield client


@pytest.fixture()
def unconfigured_client(tmp_path, monkeypatch, service_module):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").touch()
    monkeypatch.setattr(service_module, "resolve_project_root", lambda: tmp_path)
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        yield client


# ---------------------------------------------------------------------------
# Synthetic-fixture tests
# ---------------------------------------------------------------------------


def test_root_lists_endpoints(configured_client):
    r = configured_client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["decide"] == "/decide/{complaint_id}"
    assert body["self_test"] == "/decide/self-test"
    assert "unlike BP6" in body["note"]


def test_health_ok_when_configured(configured_client):
    r = configured_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["bp_id"] == "bp7"
    assert body["live_row_count"] == 3
    assert body["champion_rule_scheme"] == "correlation_aware_plus_lr_diagnostic"
    assert body["intervention_threshold"] == 0.5
    assert "Complaint ID" in body["records_csv_columns"]


def test_health_not_configured_when_prerequisites_missing(unconfigured_client):
    r = unconfigured_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_configured"
    assert "Gate 5" in body["error"]


def test_decide_returns_flagged_recurring_record(configured_client):
    r = configured_client.get("/decide/1001")
    assert r.status_code == 200
    body = r.json()
    assert body["complaint_id"] == 1001
    assert body["intervention_flag"] is True
    assert body["recommended_action"] == "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER"
    assert body["priority_score"] == pytest.approx(0.62)


def test_decide_returns_standard_queue_record(configured_client):
    r = configured_client.get("/decide/1002")
    assert r.status_code == 200
    body = r.json()
    assert body["intervention_flag"] is False
    assert body["recommended_action"] == "STANDARD_QUEUE"


def test_decide_returns_unscored_record_with_null_priority_score(configured_client):
    """Real, structurally-honest zero-fabrication path: an unjoinable complaint carries a null
    priority_score and UNSCORED_MISSING_UPSTREAM_INPUT, never a fabricated substitute score."""
    r = configured_client.get("/decide/1003")
    assert r.status_code == 200
    body = r.json()
    assert body["priority_score"] is None
    assert body["recommended_action"] == "UNSCORED_MISSING_UPSTREAM_INPUT"


def test_decide_unknown_complaint_id_returns_404(configured_client):
    r = configured_client.get("/decide/999999999")
    assert r.status_code == 404


def test_decide_rejects_non_integer_complaint_id(configured_client):
    r = configured_client.get("/decide/not-an-int")
    assert r.status_code == 422


def test_decide_returns_503_when_not_configured(unconfigured_client):
    r = unconfigured_client.get("/decide/1001")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Self-test endpoint (no external API call anywhere - BP7's own honest analogue of BP6's
# real-Gemini-call self-test; see the service module's own docstring for the full rationale).
# ---------------------------------------------------------------------------


def test_self_test_route_is_not_shadowed_by_decide_path_param(configured_client):
    """Real regression guard: /decide/self-test must resolve to the self-test endpoint, never be
    swallowed by /decide/{complaint_id} attempting to int-parse 'self-test' (a real bug hit and
    fixed during this service's own sandbox verification - route registration order matters)."""
    r = configured_client.get("/decide/self-test")
    assert r.status_code == 200
    assert "row_checks" in r.json()


def test_self_test_all_checks_pass_on_real_schema_fixture(configured_client):
    r = configured_client.get("/decide/self-test", params={"sample_size": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_rows_checked"] == 3
    assert body["real_external_api_call_made"] is False
    assert body["all_checks_passed"] is True
    for row_check in body["row_checks"]:
        assert row_check["contribution_reconstruction_exact"] is True
        assert row_check["intervention_flag_matches_threshold_rule"] is True
        assert row_check["recommended_action_structurally_consistent"] is True
        assert row_check["dual_read_identical"] is True


def test_self_test_unscored_row_is_vacuously_contribution_consistent(configured_client):
    """Complaint 1003 (unscored, null priority_score) must never be reported as a reconstruction
    failure - there is nothing to reconstruct for a row with no real contribution values."""
    r = configured_client.get("/decide/self-test", params={"sample_size": 3})
    body = r.json()
    row_1003 = next(rc for rc in body["row_checks"] if rc["complaint_id"] == 1003)
    assert row_1003["contribution_reconstruction_exact"] is True
    assert row_1003["recommended_action_structurally_consistent"] is True


def test_self_test_detects_broken_reconstruction(configured_client, tmp_path, monkeypatch):
    """Negative control: if a real row's stored contributions no longer sum to its stored
    priority_score, the self-test must report all_checks_passed=False, never silently pass."""
    artifacts_dir = tmp_path / "notebooks" / "bp7_customer_navigator_decision_engine" / "artifacts"
    csv_path = artifacts_dir / "gate5_full_population_decision_records.csv"
    text = csv_path.read_text(encoding="utf-8")
    # Corrupt row 1001's priority_score so it no longer equals the sum of its own contributions.
    text = text.replace("1001,0.62,true", "1001,0.99,true")
    csv_path.write_text(text, encoding="utf-8")

    r = configured_client.get("/decide/self-test", params={"sample_size": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["all_checks_passed"] is False
    row_1001 = next(rc for rc in body["row_checks"] if rc["complaint_id"] == 1001)
    assert row_1001["contribution_reconstruction_exact"] is False


def test_self_test_returns_503_when_not_configured(unconfigured_client):
    r = unconfigured_client.get("/decide/self-test")
    assert r.status_code == 503


def test_self_test_rejects_sample_size_over_max(configured_client):
    r = configured_client.get("/decide/self-test", params={"sample_size": 10_000})
    assert r.status_code == 422


def test_self_test_rejects_sample_size_below_one(configured_client):
    r = configured_client.get("/decide/self-test", params={"sample_size": 0})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Production-hardening endpoints (2026-09-26 addition - see the service module's own docstring):
# /version, /model-info, /metrics, POST /score, POST /decision, the /v1 mirror, request-ID +
# latency headers, the consistent JSON error envelope, and the in-memory rate limiter.
# ---------------------------------------------------------------------------


def test_version_is_public_and_has_no_semver_claim(unconfigured_client):
    """GET /version must work with NO API key (matching /health's own precedent), and must never
    claim a semantic version this project doesn't really have."""
    r = unconfigured_client.get("/version", headers={"X-API-Key": ""})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["app_version"] == "0.1.0"
    assert body["api_versions_supported"] == ["v1"]
    assert "no semantic version tags" in body["note"]
    assert body["dataset_and_model_version_proxy"]["gate5_artifacts_loaded"] is False


def test_version_reports_real_dataset_proxy_when_configured(configured_client):
    r = configured_client.get("/version")
    assert r.status_code == 200
    proxy = r.json()["dataset_and_model_version_proxy"]
    assert proxy["gate5_artifacts_loaded"] is True
    assert proxy["champion_rule_scheme"] == "correlation_aware_plus_lr_diagnostic"
    assert proxy["live_row_count"] == 3


def test_model_info_requires_auth(configured_client):
    r = configured_client.get("/model-info", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_model_info_returns_real_governance_fields_when_configured(configured_client):
    r = configured_client.get("/model-info")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["decision_type"] == "deterministic_weighted_rule_lookup"
    assert body["champion_rule_scheme"] == "correlation_aware_plus_lr_diagnostic"
    assert body["champion_weights_normalized"]["bp4"] == pytest.approx(0.606512)
    assert body["upstream_inputs"] == ["bp2", "bp3", "bp4"]
    assert "no live model inference" in body["disclosure"]


def test_model_info_not_configured(unconfigured_client):
    r = unconfigured_client.get("/model-info")
    assert r.status_code == 200
    assert r.json()["status"] == "not_configured"


def test_metrics_requires_auth(configured_client):
    r = configured_client.get("/metrics", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_metrics_counts_real_requests(configured_client):
    configured_client.get("/health")
    configured_client.get("/decide/1001")
    r = configured_client.get("/metrics")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_requests"] >= 2
    assert body["requests_by_route"]["/health"] >= 1
    assert body["requests_by_route"]["/decide/{complaint_id}"] >= 1
    assert body["responses_by_status_class"]["2xx"] >= 2
    assert body["rate_limit_per_minute"] == 120
    assert "per-process" in body["disclosure"] or "single process" in body["disclosure"]


def test_score_batch_returns_real_rows_and_flags_missing_ids(configured_client):
    r = configured_client.post("/score", json={"complaint_ids": [1001, 1002, 999999999]})
    assert r.status_code == 200, r.text
    results = {item["complaint_id"]: item for item in r.json()["results"]}
    assert results[1001]["found"] is True
    assert results[1001]["priority_score"] == pytest.approx(0.62)
    assert results[1001]["contribution_bp2"] == pytest.approx(0.2)
    assert results[1002]["found"] is True
    assert results[1002]["priority_score"] == pytest.approx(0.21)
    assert results[999999999]["found"] is False
    assert results[999999999]["priority_score"] is None


def test_score_batch_rejects_over_max_batch_size(configured_client):
    r = configured_client.post("/score", json={"complaint_ids": list(range(200))})
    assert r.status_code == 422


def test_score_batch_rejects_empty_list(configured_client):
    r = configured_client.post("/score", json={"complaint_ids": []})
    assert r.status_code == 422


def test_score_returns_503_when_not_configured(unconfigured_client):
    r = unconfigured_client.post("/score", json={"complaint_ids": [1001]})
    assert r.status_code == 503


def test_decision_batch_returns_real_rows_and_flags_missing_ids(configured_client):
    r = configured_client.post("/decision", json={"complaint_ids": [1001, 1002, 999999999]})
    assert r.status_code == 200, r.text
    results = {item["complaint_id"]: item for item in r.json()["results"]}
    assert results[1001]["found"] is True
    assert results[1001]["intervention_flag"] is True
    assert results[1001]["recommended_action"] == "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER"
    assert results[1002]["found"] is True
    assert results[1002]["intervention_flag"] is False
    assert results[999999999]["found"] is False
    assert results[999999999]["recommended_action"] is None


def test_decision_returns_503_when_not_configured(unconfigured_client):
    r = unconfigured_client.post("/decision", json={"complaint_ids": [1001]})
    assert r.status_code == 503


def test_v1_prefix_mirrors_bare_routes(configured_client):
    """Explicit API versioning (2026-09-26 addition): every bare route must also resolve under
    /v1, serving identical real data - never a second, drifted implementation."""
    bare = configured_client.get("/decide/1001")
    versioned = configured_client.get("/v1/decide/1001")
    assert bare.status_code == versioned.status_code == 200
    assert bare.json() == versioned.json()

    bare_health = configured_client.get("/health")
    versioned_health = configured_client.get("/v1/health")
    assert bare_health.json() == versioned_health.json()


def test_request_id_header_present_and_caller_supplied_value_is_echoed(configured_client):
    r = configured_client.get("/health")
    assert "x-request-id" in {k.lower() for k in r.headers.keys()}

    supplied = "caller-supplied-request-id-12345"
    r2 = configured_client.get("/health", headers={"X-Request-ID": supplied})
    assert r2.headers["x-request-id"] == supplied


def test_response_time_header_present(configured_client):
    r = configured_client.get("/health")
    assert "x-response-time-ms" in {k.lower() for k in r.headers.keys()}
    assert float(r.headers["X-Response-Time-Ms"]) >= 0.0


def test_error_envelope_on_404_has_request_id_and_error_code(configured_client):
    r = configured_client.get("/decide/999999999")
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "NOT_FOUND"
    assert body["status_code"] == 404
    assert "request_id" in body and body["request_id"]
    assert "detail" in body


def test_error_envelope_on_401(configured_client):
    r = configured_client.get("/decide/1001", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401
    body = r.json()
    assert body["error_code"] == "UNAUTHORIZED"
    assert "request_id" in body and body["request_id"]


def test_error_envelope_on_422_validation(configured_client):
    r = configured_client.get("/decide/self-test", params={"sample_size": 0})
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert "request_id" in body and body["request_id"]


def test_rate_limit_triggers_and_reports_retry_after(configured_client, monkeypatch):
    monkeypatch.setenv("C360_RATE_LIMIT_PER_MINUTE", "1")
    r1 = configured_client.get("/decide/1001")
    assert r1.status_code == 200
    r2 = configured_client.get("/decide/1002")
    assert r2.status_code == 429
    body = r2.json()
    assert body["error_code"] == "RATE_LIMITED"
    assert "Retry-After" in r2.headers


def test_rate_limit_disabled_when_set_to_zero(configured_client, monkeypatch):
    monkeypatch.setenv("C360_RATE_LIMIT_PER_MINUTE", "0")
    for _ in range(5):
        r = configured_client.get("/decide/1001")
        assert r.status_code == 200


def test_rate_limit_exempts_health_and_root(configured_client, monkeypatch):
    """/ and /health are real, un-authenticated orchestrator probes and must never be rate
    limited, even under a very tight limit."""
    monkeypatch.setenv("C360_RATE_LIMIT_PER_MINUTE", "1")
    for _ in range(5):
        assert configured_client.get("/").status_code == 200
        assert configured_client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Real-artifact integration test (skipped, not failed, unless running inside the real project
# tree with BP7 Gate 5 already real-run). Makes NO fabricated call of any kind.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_project_root():
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return candidate
    pytest.skip("Not running inside the Customer360 Navigator project tree.")


def test_real_bp7_health_and_decide_when_gate5_has_run(real_project_root, monkeypatch, service_module):
    artifacts_dir = real_project_root / "notebooks" / "bp7_customer_navigator_decision_engine" / "artifacts"
    records_csv = artifacts_dir / "gate5_full_population_decision_records.csv"
    summary_json = artifacts_dir / "gate5_decision_layer_summary.json"
    if not records_csv.exists() or not summary_json.exists():
        pytest.skip("BP7 Gate 5 has not been run for real yet.")

    monkeypatch.setattr(service_module, "resolve_project_root", lambda: real_project_root)
    with TestClient(service_module.app, headers={"X-API-Key": TEST_API_KEY}) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert health.json()["live_row_count"] > 0

        self_test = client.get("/decide/self-test", params={"sample_size": 10})
        assert self_test.status_code == 200
        assert self_test.json()["real_external_api_call_made"] is False
