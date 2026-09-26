"""
tests/services/test_bp_activation_service.py — Customer360 Navigator

Real pytest coverage for the Activation Layer service (src/services/bp_activation_service.py).
Every test exercises the real FastAPI app via TestClient — no mocked adapter, since the adapters
are themselves already simulations (see that module's own docstring); these tests verify the
simulation behaves exactly as documented: real state persisted, real policy applied, real auth
enforced, and a real 422 (never a silent fallback) for a recommended_action outside BP7's own
disclosed vocabulary.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.bp_activation_service import ACTIVATION_POLICY, KNOWN_RECOMMENDED_ACTIONS, app

# Matches tests/services/conftest.py's autouse _c360_api_key_env fixture, which sets
# C360_API_KEY to exactly this value for every test collected under tests/services/.
TEST_API_KEY = "test-api-key-for-ci"
AUTH = {"X-API-Key": TEST_API_KEY}


def _client() -> TestClient:
    return TestClient(app)


def test_root_discloses_simulation_and_policy():
    with _client() as c:
        r = c.get("/")
    assert r.status_code == 200
    body = r.json()
    assert "SIMULATED" not in body["service"]  # service name itself is plain
    assert "No adapter" in body["disclosure"]
    assert set(body["known_recommended_actions"]) == set(KNOWN_RECOMMENDED_ACTIONS)


def test_health_open_no_auth_needed():
    with _client() as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_protected_routes_require_api_key():
    with _client() as c:
        r = c.post("/activation/case", json={"complaint_id": "X", "recommended_action": "STANDARD_QUEUE"})
    assert r.status_code == 401


def test_protected_routes_reject_wrong_key():
    with _client() as c:
        r = c.get("/activation/log", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_create_case_is_simulated_and_logged():
    with _client() as c:
        r = c.post(
            "/activation/case",
            json={
                "complaint_id": "C-100",
                "recommended_action": "PRIORITY_QUEUE_REVIEW",
                "priority_score": 3.0,
                "reason_codes": ["BP2_HIGH_FRICTION"],
            },
            headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["system"] == "SIMULATED_CASE_MANAGEMENT"
        assert body["status"] == "created"
        assert body["case_id"].startswith("CASE-")

        log = c.get("/activation/log", headers=AUTH).json()
    assert log["count"] >= 1
    assert any(e["event_type"] == "case" and e["complaint_id"] == "C-100" for e in log["events"])


def test_crm_and_notification_adapters_simulated():
    with _client() as c:
        r_crm = c.post(
            "/activation/crm", json={"complaint_id": "C-200", "note": "unit test note"}, headers=AUTH
        )
        r_note = c.post(
            "/activation/notification",
            json={"complaint_id": "C-200", "recipient_hint": "customer on file", "template": "t"},
            headers=AUTH,
        )
    assert r_crm.status_code == 200 and r_crm.json()["system"] == "SIMULATED_CRM"
    assert r_note.status_code == 200 and r_note.json()["system"] == "SIMULATED_NOTIFICATION_GATEWAY"


def test_route_applies_disclosed_policy_for_every_known_action():
    with _client() as c:
        for action, expected_channels in ACTIVATION_POLICY.items():
            r = c.post(
                "/activation/route",
                json={"complaint_id": f"C-{action}", "recommended_action": action},
                headers=AUTH,
            )
            assert r.status_code == 200, action
            body = r.json()
            assert set(body["channels_activated"]) == set(expected_channels), action
            assert (body["case"] is not None) == ("case" in expected_channels)
            assert (body["crm"] is not None) == ("crm" in expected_channels)
            assert (body["notification"] is not None) == ("notification" in expected_channels)


def test_route_rejects_unknown_recommended_action_never_guesses():
    with _client() as c:
        r = c.post(
            "/activation/route",
            json={"complaint_id": "C-BAD", "recommended_action": "NOT_A_REAL_ACTION"},
            headers=AUTH,
        )
    assert r.status_code == 422


def test_policy_table_covers_exactly_bp7s_real_vocabulary():
    # Guards against ACTIVATION_POLICY silently drifting from BP7's own disclosed action set.
    assert set(ACTIVATION_POLICY.keys()) == set(KNOWN_RECOMMENDED_ACTIONS)
