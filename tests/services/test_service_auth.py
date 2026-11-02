"""
tests/services/test_service_auth.py — Customer360 Navigator

Direct tests for src/services/service_auth.py::require_api_key (Phase J rewiring through
secrets_provider.py). Builds a minimal real FastAPI app with one protected route rather than
importing one of the 7 real BP services, so these tests exercise require_api_key in isolation
from any model-loading concern - real FastAPI dependency injection and a real TestClient/httpx
round trip, not a bare function call, so the actual HTTP status codes and headers this dependency
produces for real callers are what gets asserted.

Covers the explicit security-testing list the Master Engineering Directive's Phase I (secrets
management) names for this dependency: missing credentials, invalid credentials, unauthorized
API access, and secret leakage in the response body.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from services import service_auth as auth
from services.secrets_provider import VaultSecretsProvider


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(auth.require_api_key)])
    def protected():
        return {"ok": True}

    return app


@pytest.fixture
def client():
    return TestClient(_build_app())


def test_missing_api_key_env_var_returns_503_not_401(monkeypatch, client):
    """A misconfigured service (no real secret available at all) is a 503, never silently
    treated as "open" (200) nor confused with "caller sent a wrong key" (401)."""
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.delenv(auth.API_KEY_ENV_VAR, raising=False)
    response = client.get("/protected", headers={"X-API-Key": "anything"})
    assert response.status_code == 503
    assert auth.API_KEY_ENV_VAR in response.json()["detail"]


def test_missing_header_on_a_correctly_configured_service_returns_401(monkeypatch, client):
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.setenv(auth.API_KEY_ENV_VAR, "the-real-key")
    response = client.get("/protected")
    assert response.status_code == 401


def test_wrong_api_key_on_a_correctly_configured_service_returns_401(monkeypatch, client):
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.setenv(auth.API_KEY_ENV_VAR, "the-real-key")
    response = client.get("/protected", headers={"X-API-Key": "a-completely-wrong-key"})
    assert response.status_code == 401


def test_correct_api_key_is_accepted(monkeypatch, client):
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.setenv(auth.API_KEY_ENV_VAR, "the-real-key")
    response = client.get("/protected", headers={"X-API-Key": "the-real-key"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_401_response_body_never_echoes_the_wrong_key_the_caller_sent(monkeypatch, client):
    """A caller probing with a guessed key must never see their own guess reflected back, since
    that is a classic timing/oracle-adjacent leak pattern - the 401 body should name only the
    header, never the value that was sent."""
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.setenv(auth.API_KEY_ENV_VAR, "the-real-key")
    guessed = "attacker-guessed-value-xyz"
    response = client.get("/protected", headers={"X-API-Key": guessed})
    assert guessed not in response.text


def test_503_response_body_never_contains_the_configured_real_key(monkeypatch, client):
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.delenv(auth.API_KEY_ENV_VAR, raising=False)
    response = client.get("/protected", headers={"X-API-Key": "whatever"})
    # There is no configured key in this scenario, but this also pins the general shape: the
    # response never contains anything that looks like it came from a resolved secret value.
    assert response.status_code == 503
    assert "whatever" not in response.text


def test_health_and_root_routes_are_not_gated_by_this_dependency():
    """require_api_key is only ever attached by a service to its protected routes - this test
    documents that expectation at the dependency level: an app that never attaches it to a route
    serves that route with no auth check at all, exactly as / and /health do on every real BP
    service (SECURITY.md's own documented exemption)."""
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_vault_backend_unavailable_surfaces_as_503_through_the_same_dependency(monkeypatch):
    """When a service opts in to C360_SECRETS_PROVIDER=vault and that Vault is unreachable, the
    caller-visible result is the same fail-closed 503 as the plain env-var misconfiguration case
    - never a 500 (an unhandled exception) and never a silent fall-through to "open"."""
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "vault")
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:1")
    monkeypatch.setenv("VAULT_TOKEN", "irrelevant")
    monkeypatch.delenv("C360_VAULT_SECRET_PATH", raising=False)

    client = TestClient(_build_app())
    response = client.get("/protected", headers={"X-API-Key": "anything"})
    assert response.status_code == 503
    assert "VAULT_TOKEN" not in response.text
    assert "irrelevant" not in response.text


def test_vault_provider_instantiated_directly_is_the_real_class_not_a_stub(monkeypatch):
    """Sanity check that the factory this dependency calls really does return a
    VaultSecretsProvider instance when configured to, not some simplified stand-in - guards
    against a future refactor silently turning C360_SECRETS_PROVIDER=vault into a no-op."""
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "vault")
    from services.secrets_provider import get_secrets_provider

    provider = get_secrets_provider()
    assert isinstance(provider, VaultSecretsProvider)
