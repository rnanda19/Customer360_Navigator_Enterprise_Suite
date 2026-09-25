"""
tests/services/test_bp6_resolution_service.py — Customer360 Navigator

Tests for src/services/bp6_resolution_service.py (BP6 Gate 6 — Master Plan paragraph 205's
mandatory BP6/BP7 FastAPI-service-with-live-self-test deliverable). Mirrors
test_bp4_decision_service.py's synthetic-fixture-drives-the-real-app structure (see that file's
docstring for the rationale), adapted for BP6's very different shape: there is no persisted
artifact to load, only real, small, schema-correct upstream Gate 7 manifests + a Gate 2
PII-screened CSV + a Gate 4 eligible-bucket trace, and every generation call is mocked at the
`google.genai.Client` boundary (never a real network call in this suite — a real Gemini call is
made only when the user runs Gate 6's own notebook cell or the service for real, per this
project's standing "Claude never executes real external-API calls" rule).

Two-layer structure:
  1. Synthetic-fixture tests (below) build tiny, real-schema upstream manifests/CSV/trace files
     under `tmp_path` and drive the real FastAPI app end-to-end, with `google.genai.Client` mocked
     at the exact boundary `call_grounded_generation()` itself imports it from.
  2. One real-artifact integration test, skipped (not failed) when this is not running inside the
     real project tree with BP6 Gates 2/4 already real-run — checks only that /health reports "ok"
     against the REAL on-device evidence bundle; it makes NO real network call (no BP6 gate/test in
     this project ever fires the real Gemini API automatically — only a human, running the gate
     notebook or the service itself, does that).
"""

from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

MODULE_PATH = "services.bp6_resolution_service"

UPSTREAM_BP_NAMES = {
    "bp1": "bp1_customer_intent_classification",
    "bp2": "bp2_customer_friction_classification",
    "bp3": "bp3_complaint_escalation_prediction",
    "bp4": "bp4_customer_journey_analytics",
    "bp5": "bp5_root_cause_driver_analytics",
}


def _build_synthetic_prerequisites(tmp_path: Path) -> None:
    """Real-schema, synthetic-value fixtures: one executive_rollup_manifest.json per upstream BP
    (2 real scalar fields each -> 10 total citations, matching how
    retrieve_headline_evidence_bundle() counts them), a 2-row PII-screened CSV (one row per
    eligible bucket), and a 2-bucket Gate 4 trace."""
    for bp_id, bp_name in UPSTREAM_BP_NAMES.items():
        artifacts_dir = tmp_path / "notebooks" / bp_name / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "bp_id": bp_id,
            "gate": 7,
            "generated_at_utc": "2026-09-24T00:00:00+00:00",
            "headline_metric_a": 0.95,
            "headline_metric_b": f"fixture-value-{bp_id}",
        }
        with open(artifacts_dir / "executive_rollup_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

    bp6_artifacts_dir = tmp_path / "notebooks" / "bp6_genai_resolution_assistant" / "artifacts"
    bp6_artifacts_dir.mkdir(parents=True, exist_ok=True)

    with open(bp6_artifacts_dir / "gate4_explainability_trace.json", "w", encoding="utf-8") as f:
        json.dump([{"bucket": "bucket_a"}, {"bucket": "bucket_b"}], f)

    csv_path = bp6_artifacts_dir / "gate2_pii_screened_narrative_text.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["masked_text", "category", "common_taxonomy_bucket", "pii_detected", "split"])
        w.writerow(
            [
                "My card was charged twice for the same purchase.",
                "card_payment_wrong_exchange_rate",
                "bucket_a",
                "False",
                "train",
            ]
        )
        w.writerow(
            [
                "I never received my refund after cancelling.",
                "refund_not_showing_up",
                "bucket_b",
                "False",
                "test",
            ]
        )

    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").touch()


class _FakeCandidate:
    def __init__(self, finish_reason: str):
        self.finish_reason = finish_reason


class _FakeUsage:
    prompt_token_count = 500
    candidates_token_count = 40


class _FakeResponse:
    def __init__(self, text: str, finish_reason: str = "STOP"):
        self.text = text
        self.usage_metadata = _FakeUsage()
        self.response_id = "fake-response-id"
        self.candidates = [_FakeCandidate(finish_reason)]


def _fake_genai_client(text: str, finish_reason: str = "STOP") -> mock.MagicMock:
    instance = mock.MagicMock()
    instance.models.generate_content.return_value = _FakeResponse(text, finish_reason)
    return mock.MagicMock(return_value=instance)


@pytest.fixture()
def service_module():
    import services.bp6_resolution_service as svc

    importlib.reload(svc)
    return svc


@pytest.fixture()
def configured_client(tmp_path, monkeypatch, service_module):
    _build_synthetic_prerequisites(tmp_path)
    monkeypatch.setattr(service_module, "resolve_project_root", lambda: tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "sandbox-fake-key-not-real")
    with TestClient(service_module.app) as client:
        yield client


@pytest.fixture()
def unconfigured_client(tmp_path, monkeypatch, service_module):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").touch()
    monkeypatch.setattr(service_module, "resolve_project_root", lambda: tmp_path)
    with TestClient(service_module.app) as client:
        yield client


NARRATIVE_A = {
    "masked_text": "My card was charged twice.",
    "category": "card_payment_wrong_exchange_rate",
    "common_taxonomy_bucket": "bucket_a",
}


def test_root_lists_endpoints(configured_client):
    r = configured_client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["resolve"] == "/resolve"
    assert body["self_test"] == "/resolve/self-test"


def test_health_ok_when_configured(configured_client):
    r = configured_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["n_evidence_citations_available"] == 10  # 2 fields x 5 upstream BPs
    assert body["n_eligible_retrieval_buckets"] == 2
    assert body["gemini_api_key_present"] is True


def test_health_not_configured_when_prerequisites_missing(unconfigured_client):
    r = unconfigured_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_configured"
    assert "gate2_pii_screened_narrative_text.csv" in body["error"]


def test_resolve_returns_503_when_not_configured(unconfigured_client):
    r = unconfigured_client.post("/resolve", json={"narrative_sample": NARRATIVE_A})
    assert r.status_code == 503


def test_resolve_success_with_explicit_narrative(configured_client):
    good_text = (
        "Based on the evidence, a monetary-relief resolution is appropriate for this case "
        "[EV-BP1-1]. Review timelines should follow the documented process [EV-BP2-1]."
    )
    fake_cls = _fake_genai_client(good_text, finish_reason="STOP")
    with mock.patch("google.genai.Client", fake_cls):
        r = configured_client.post("/resolve", json={"narrative_sample": NARRATIVE_A})
    assert r.status_code == 200, r.text
    artifact = r.json()["recommendation_artifact"]
    assert artifact["approval_status"] == "PENDING_HUMAN_REVIEW"
    assert artifact["auto_applied"] is False
    assert artifact["citation_check"]["passed"] is True
    assert artifact["udaap_check"]["passed"] is True
    assert artifact["generated_recommendation_text"] == good_text
    # thinking is disabled per the real, documented truncation bug fixed in Gate 5
    call_kwargs = fake_cls.return_value.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].thinking_config.thinking_budget == 0


def test_resolve_reproducible_sample_mode_selects_deterministically(configured_client):
    """Omitting narrative_sample reuses Gate 5's own reproducible-selection code path."""
    fake_cls = _fake_genai_client("Escalation is warranted here [EV-BP3-1].", finish_reason="STOP")
    with mock.patch("google.genai.Client", fake_cls):
        r1 = configured_client.post("/resolve", json={"random_state": 42})
        r2 = configured_client.post("/resolve", json={"random_state": 42})
    assert r1.status_code == 200 and r2.status_code == 200
    ctx1 = r1.json()["recommendation_artifact"]["customer_message_context"]
    ctx2 = r2.json()["recommendation_artifact"]["customer_message_context"]
    assert ctx1 == ctx2  # same seed -> same real row selected, both times


def test_resolve_refuses_on_max_tokens_truncation(configured_client):
    fake_cls = _fake_genai_client(" and is recommended [EV-BP1-1].", finish_reason="MAX_TOKENS")
    with mock.patch("google.genai.Client", fake_cls):
        r = configured_client.post("/resolve", json={"narrative_sample": NARRATIVE_A})
    assert r.status_code == 422
    assert "MAX_TOKENS" in r.json()["detail"]


def test_resolve_refuses_on_uncited_claim(configured_client):
    fake_cls = _fake_genai_client("You are guaranteed a full refund immediately.", finish_reason="STOP")
    with mock.patch("google.genai.Client", fake_cls):
        r = configured_client.post("/resolve", json={"narrative_sample": NARRATIVE_A})
    assert r.status_code == 422


def test_self_test_endpoint_proves_one_real_call_and_identical_artifacts(configured_client):
    """Master Plan paragraph 205's own required proof: exactly one real (here: mocked-boundary)
    Gemini call, and the endpoint-composed vs. directly-computed artifacts are field-for-field
    identical."""
    good_text = "This case merits escalation per the documented process [EV-BP3-1]."
    fake_cls = _fake_genai_client(good_text, finish_reason="STOP")
    with mock.patch("google.genai.Client", fake_cls):
        r = configured_client.post("/resolve/self-test", json={"narrative_sample": NARRATIVE_A})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["identical"] is True
    assert body["endpoint_composed_artifact"] == body["directly_computed_artifact"]
    assert fake_cls.return_value.models.generate_content.call_count == 1


def test_self_test_reports_false_would_be_caught_if_paths_ever_drifted(configured_client, monkeypatch):
    """Negative control: if the two computation paths ever produced different artifacts, the
    endpoint must report identical=False rather than silently reporting True. Simulated by
    monkeypatching build_recommendation_artifact to append a nonce on its second (direct-path)
    call only, which would otherwise be indistinguishable from a real regression."""
    import genai.bp6_grounded_generation as ggen

    real_build = ggen.build_recommendation_artifact
    call_count = {"n": 0}

    def _drifting_build(*args, **kwargs):
        result = real_build(*args, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 2:
            result = dict(result)
            result["generated_recommendation_text"] += " [DRIFTED]"
        return result

    monkeypatch.setattr(ggen, "build_recommendation_artifact", _drifting_build)
    fake_cls = _fake_genai_client("Escalation is warranted [EV-BP1-1].", finish_reason="STOP")
    with mock.patch("google.genai.Client", fake_cls):
        r = configured_client.post("/resolve/self-test", json={"narrative_sample": NARRATIVE_A})
    assert r.status_code == 200
    assert r.json()["identical"] is False


# ------------------------------------------------------------------------------------------------
# Real-artifact integration test (skipped, not failed, unless running inside the real project tree
# with BP6 Gates 2/4 already real-run). Makes NO real network call - health-only.
# ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_project_root():
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return candidate
    pytest.skip("Not running inside the Customer360 Navigator project tree.")


def test_real_bp6_health_reports_ok_when_gates_2_and_4_have_run(
    real_project_root, monkeypatch, service_module
):
    artifacts_dir = real_project_root / "notebooks" / "bp6_genai_resolution_assistant" / "artifacts"
    if not (artifacts_dir / "gate2_pii_screened_narrative_text.csv").exists():
        pytest.skip("BP6 Gate 2 has not been run for real yet.")
    if not (artifacts_dir / "gate4_explainability_trace.json").exists():
        pytest.skip("BP6 Gate 4 has not been run for real yet.")
    monkeypatch.setattr(service_module, "resolve_project_root", lambda: real_project_root)
    with TestClient(service_module.app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["n_evidence_citations_available"] > 0
