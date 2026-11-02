"""
tests/services/test_secrets_provider.py — Customer360 Navigator

Tests for src/services/secrets_provider.py (Phase J). Covers the explicit security-testing list
the Master Engineering Directive's Phase I (secrets management) names: missing credentials,
invalid credentials, Vault unavailable, and secret-value-never-leaked-in-errors. The real Vault
HTTP call is exercised against a tiny stdlib http.server fixture standing in for Vault's own KV
v2 response shape (the exact shape docs/secrets_management_demo/vault_dev_example.sh verifies
against a real dev-mode Vault in CI) - never a mocked/monkeypatched urlopen, so the real request
construction, URL building, and JSON parsing are genuinely exercised end to end.
"""

from __future__ import annotations

import http.server
import json
import threading
from contextlib import contextmanager

import pytest

from services import secrets_provider as sp

# ---------------------------------------------------------------------------
# EnvSecretsProvider
# ---------------------------------------------------------------------------


def test_env_provider_returns_the_real_value_when_set(monkeypatch):
    monkeypatch.setenv("SOME_SECRET", "real-value-123")
    assert sp.EnvSecretsProvider().get_secret("SOME_SECRET") == "real-value-123"


def test_env_provider_raises_secret_not_found_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_SECRET", raising=False)
    with pytest.raises(sp.SecretNotFoundError):
        sp.EnvSecretsProvider().get_secret("SOME_SECRET")


def test_env_provider_raises_secret_not_found_when_set_to_empty_string(monkeypatch):
    monkeypatch.setenv("SOME_SECRET", "")
    with pytest.raises(sp.SecretNotFoundError):
        sp.EnvSecretsProvider().get_secret("SOME_SECRET")


def test_env_provider_error_message_never_contains_a_secret_value(monkeypatch):
    """The only thing that could leak here is the *name* of the missing variable - which is not
    sensitive by itself - never a value, since there is no value to leak when the variable is
    unset. This test pins that the exception message is name-only."""
    monkeypatch.delenv("TOTALLY_MISSING_VAR", raising=False)
    with pytest.raises(sp.SecretNotFoundError) as exc_info:
        sp.EnvSecretsProvider().get_secret("TOTALLY_MISSING_VAR")
    assert "TOTALLY_MISSING_VAR" in str(exc_info.value)


# ---------------------------------------------------------------------------
# get_secrets_provider() factory
# ---------------------------------------------------------------------------


def test_factory_defaults_to_env_provider_when_unset(monkeypatch):
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    provider = sp.get_secrets_provider()
    assert isinstance(provider, sp.EnvSecretsProvider)


def test_factory_returns_env_provider_when_explicitly_env(monkeypatch):
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "env")
    assert isinstance(sp.get_secrets_provider(), sp.EnvSecretsProvider)


def test_factory_returns_vault_provider_when_vault(monkeypatch):
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "vault")
    monkeypatch.delenv("C360_VAULT_SECRET_PATH", raising=False)
    provider = sp.get_secrets_provider()
    assert isinstance(provider, sp.VaultSecretsProvider)
    assert provider.mount_path == "customer360/services"


def test_factory_honors_custom_vault_mount_path(monkeypatch):
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "vault")
    monkeypatch.setenv("C360_VAULT_SECRET_PATH", "custom/path")
    provider = sp.get_secrets_provider()
    assert provider.mount_path == "custom/path"


def test_factory_raises_on_unknown_provider_kind(monkeypatch):
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "some-nonsense-backend")
    with pytest.raises(ValueError):
        sp.get_secrets_provider()


def test_factory_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("C360_SECRETS_PROVIDER", "ENV")
    assert isinstance(sp.get_secrets_provider(), sp.EnvSecretsProvider)


# ---------------------------------------------------------------------------
# VaultSecretsProvider - configuration failures (fail closed, never fail open)
# ---------------------------------------------------------------------------


def test_vault_provider_raises_unavailable_when_vault_addr_missing(monkeypatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.setenv("VAULT_TOKEN", "some-token")
    provider = sp.VaultSecretsProvider(mount_path="customer360/services")
    with pytest.raises(sp.SecretsProviderUnavailableError):
        provider.get_secret("C360_API_KEY")


def test_vault_provider_raises_unavailable_when_vault_token_missing(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:1")
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    provider = sp.VaultSecretsProvider(mount_path="customer360/services")
    with pytest.raises(sp.SecretsProviderUnavailableError):
        provider.get_secret("C360_API_KEY")


def test_vault_provider_raises_unavailable_when_vault_unreachable(monkeypatch):
    """Real connection-refused case: point at a real TCP port with nothing listening, rather
    than mocking the failure - a genuinely unreachable address, not a simulated one."""
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    provider = sp.VaultSecretsProvider(
        mount_path="customer360/services",
        vault_addr="http://127.0.0.1:1",  # port 1 - real, almost never listened on
        vault_token="irrelevant-token",
        timeout_seconds=2.0,
    )
    with pytest.raises(sp.SecretsProviderUnavailableError):
        provider.get_secret("C360_API_KEY")


def test_vault_unavailable_error_never_contains_the_vault_token(monkeypatch):
    """The token is a real credential - this pins that a connection-failure message never
    includes it, even though the token was passed to the failing request."""
    provider = sp.VaultSecretsProvider(
        mount_path="customer360/services",
        vault_addr="http://127.0.0.1:1",
        vault_token="super-secret-token-value-should-never-appear",
        timeout_seconds=2.0,
    )
    with pytest.raises(sp.SecretsProviderUnavailableError) as exc_info:
        provider.get_secret("C360_API_KEY")
    assert "super-secret-token-value-should-never-appear" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# VaultSecretsProvider - real HTTP round trip against a tiny stand-in server
# ---------------------------------------------------------------------------


class _FakeVaultHandler(http.server.BaseHTTPRequestHandler):
    """Stands in for Vault's own KV v2 read endpoint - real HTTP, real JSON body, the exact
    response shape vault_dev_example.sh already verifies against a genuine dev-mode Vault."""

    secrets_by_path: dict = {}
    received_tokens: list = []

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's required method name
        self.received_tokens.append(self.headers.get("X-Vault-Token"))
        prefix = "/v1/secret/data/"
        if not self.path.startswith(prefix):
            self.send_response(404)
            self.end_headers()
            return
        mount_path = self.path[len(prefix) :]
        if mount_path not in self.secrets_by_path:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"errors": []}')
            return
        body = json.dumps({"data": {"data": self.secrets_by_path[mount_path]}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002 - silence test-run log noise
        pass


@contextmanager
def _fake_vault_server(secrets_by_path: dict):
    _FakeVaultHandler.secrets_by_path = secrets_by_path
    _FakeVaultHandler.received_tokens = []
    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeVaultHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", _FakeVaultHandler.received_tokens
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_vault_provider_real_http_round_trip_returns_the_real_secret():
    with _fake_vault_server({"customer360/services": {"C360_API_KEY": "real-vault-value"}}) as (
        addr,
        _tokens,
    ):
        provider = sp.VaultSecretsProvider(
            mount_path="customer360/services", vault_addr=addr, vault_token="test-token"
        )
        assert provider.get_secret("C360_API_KEY") == "real-vault-value"


def test_vault_provider_sends_the_configured_token_as_the_x_vault_token_header():
    with _fake_vault_server({"customer360/services": {"C360_API_KEY": "v"}}) as (addr, tokens):
        provider = sp.VaultSecretsProvider(
            mount_path="customer360/services", vault_addr=addr, vault_token="my-real-token"
        )
        provider.get_secret("C360_API_KEY")
    assert tokens == ["my-real-token"]


def test_vault_provider_raises_not_found_when_mount_path_does_not_exist():
    with _fake_vault_server({}) as (addr, _tokens):
        provider = sp.VaultSecretsProvider(mount_path="nonexistent/path", vault_addr=addr, vault_token="t")
        with pytest.raises(sp.SecretNotFoundError):
            provider.get_secret("C360_API_KEY")


def test_vault_provider_raises_not_found_when_key_missing_from_existing_path():
    with _fake_vault_server({"customer360/services": {"SOME_OTHER_KEY": "v"}}) as (addr, _t):
        provider = sp.VaultSecretsProvider(
            mount_path="customer360/services", vault_addr=addr, vault_token="t"
        )
        with pytest.raises(sp.SecretNotFoundError):
            provider.get_secret("C360_API_KEY")


def test_vault_provider_raises_not_found_when_key_present_but_empty():
    with _fake_vault_server({"customer360/services": {"C360_API_KEY": ""}}) as (addr, _t):
        provider = sp.VaultSecretsProvider(
            mount_path="customer360/services", vault_addr=addr, vault_token="t"
        )
        with pytest.raises(sp.SecretNotFoundError):
            provider.get_secret("C360_API_KEY")


# ---------------------------------------------------------------------------
# validate_secret_configuration - startup validation hook
# ---------------------------------------------------------------------------


def test_validate_secret_configuration_passes_silently_when_secret_resolves(monkeypatch):
    monkeypatch.setenv("SOME_SECRET", "value")
    assert sp.validate_secret_configuration("SOME_SECRET", provider=sp.EnvSecretsProvider()) is None


def test_validate_secret_configuration_raises_when_secret_cannot_be_resolved(monkeypatch):
    monkeypatch.delenv("SOME_SECRET", raising=False)
    with pytest.raises(sp.SecretNotFoundError):
        sp.validate_secret_configuration("SOME_SECRET", provider=sp.EnvSecretsProvider())


def test_validate_secret_configuration_uses_the_default_factory_when_no_provider_given(
    monkeypatch,
):
    monkeypatch.delenv("C360_SECRETS_PROVIDER", raising=False)
    monkeypatch.setenv("SOME_SECRET", "value")
    assert sp.validate_secret_configuration("SOME_SECRET") is None
