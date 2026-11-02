"""
src/services/secrets_provider.py — Customer360 Navigator

Phase J secrets-provider abstraction. SECRETS_MANAGEMENT.md's own "What real production Vault
needs" section named this exact gap as a real, not-yet-started next step: "none of [the 7
services] currently fetch from Vault; they still read os.environ['C360_API_KEY']... Wiring even
one of them to fetch its key from Vault at startup instead of the environment is a real, scoped,
not-yet-started next step." This module is that step.

Design, matching this project's existing conventions:
- stdlib + fastapi only (urllib.request for the Vault HTTP call, mirroring
  docs/secrets_management_demo/vault_dev_example.sh's own plain-HTTP-against-Vault's-API
  approach - that script needs no extra Python dependency either). No new runtime dependency is
  introduced, so none of the 7 services' minimal per-Dockerfile dependency lists need updating,
  and no Dockerfile change is needed at all: every one of them already does `COPY src/ ./src/`
  (grep-verified against bp1_inference_service/Dockerfile), so this new first-party module ships
  automatically.
- Backward compatible by default: EnvSecretsProvider is the default provider and preserves every
  existing deployment's exact current behavior (a plain os.environ[...] read) unchanged unless a
  service operator explicitly opts in to Vault via C360_SECRETS_PROVIDER=vault.
- Fails closed, never fails open: a Vault that cannot be reached, or that returns a response this
  module cannot parse, is reported as unavailable - it is never silently treated as "no secret
  required" or papered over with a default/placeholder value. The caller (service_auth.py) is
  responsible for turning that failure into the existing fail-closed 503 behavior.
- Never logs or returns a secret's value in an error message - only the secret's *name* (an env
  var name, or a Vault mount path/key name), which is not sensitive by itself.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Protocol


class SecretNotFoundError(RuntimeError):
    """Raised when the configured backend was reachable but genuinely does not have this
    secret (or it is set to an empty value) - never silently substituted with a default."""


class SecretsProviderUnavailableError(RuntimeError):
    """Raised when the configured backend itself could not be used at all (Vault unreachable,
    no VAULT_ADDR/VAULT_TOKEN configured, an unparseable response). Kept distinct from
    SecretNotFoundError so a caller or a test can tell "the backend is down" apart from "the
    backend is up but doesn't have this secret" - conflating the two would make Vault-unavailable
    silently look identical to "nobody configured this secret yet", which is exactly the kind of
    silent-failure ambiguity this project's conventions reject."""


class SecretsProvider(Protocol):
    def get_secret(self, name: str) -> str:
        """Return the real secret value for `name`, or raise SecretNotFoundError /
        SecretsProviderUnavailableError. Never returns an empty string, a placeholder, or None in
        place of raising."""
        ...


@dataclass(frozen=True)
class EnvSecretsProvider:
    """Default provider - reads a plain process environment variable, identical to every
    existing service's behavior today (src/services/service_auth.py's prior direct
    os.environ.get(...) call, before this module existed). Exists so that behavior is an
    explicit, named choice (and can be swapped for VaultSecretsProvider) rather than the only
    option baked into every call site."""

    def get_secret(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise SecretNotFoundError(f"Environment variable {name!r} is not set or is empty.")
        return value


@dataclass(frozen=True)
class VaultSecretsProvider:
    """Real HTTP integration against HashiCorp Vault's KV v2 API, using the identical endpoint
    shape docs/secrets_management_demo/vault_dev_example.sh already exercises against a real
    dev-mode Vault in CI (`GET {addr}/v1/secret/data/{mount_path}`, response shape
    `{"data": {"data": {<key>: <value>, ...}}}`). Reads VAULT_ADDR/VAULT_TOKEN from the process
    environment when not given explicitly, matching that script's own convention, so a service
    can be pointed at a real Vault with no code change - only environment configuration.

    Does NOT itself claim this is production-grade: a real deployment still needs everything
    SECRETS_MANAGEMENT.md's "What real production Vault needs" section lists (TLS, a durable
    storage backend, auto-unseal, short-lived per-service tokens instead of a long-lived token
    read from the environment here). This class is the real integration *mechanism*; it does not
    change what Vault instance it is pointed at."""

    mount_path: str
    vault_addr: Optional[str] = None
    vault_token: Optional[str] = None
    timeout_seconds: float = 5.0

    def _resolved_addr(self) -> str:
        addr = self.vault_addr or os.environ.get("VAULT_ADDR")
        if not addr:
            raise SecretsProviderUnavailableError(
                "VAULT_ADDR is not set and no explicit vault_addr was given - cannot reach Vault."
            )
        return addr

    def _resolved_token(self) -> str:
        token = self.vault_token or os.environ.get("VAULT_TOKEN")
        if not token:
            raise SecretsProviderUnavailableError(
                "VAULT_TOKEN is not set and no explicit vault_token was given - refusing to call "
                "Vault with no token rather than sending an unauthenticated request."
            )
        return token

    def get_secret(self, name: str) -> str:
        addr = self._resolved_addr()
        token = self._resolved_token()
        url = f"{addr.rstrip('/')}/v1/secret/data/{self.mount_path}"
        request = urllib.request.Request(url, headers={"X-Vault-Token": token})
        try:
            with urllib.request.urlopen(  # nosec B310 - VAULT_ADDR is operator-supplied
                # deployment configuration (env var or explicit constructor arg), never
                # request-time/attacker-controlled input, so the url-scheme concern this
                # bandit rule flags (file:// or another unexpected scheme) does not apply here -
                # matching this project's existing "# nosec <code> - <reason>" convention
                # (see src/deployment/*.py, src/mlops/tracking.py for the same pattern).
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # HTTPError is a URLError subclass, so it must be handled before the generic
            # URLError branch below. Vault's real KV v2 API returns HTTP 404 for a path that
            # simply does not exist - that is "this secret is genuinely absent", the same
            # SecretNotFoundError case as a missing key, never "Vault is unreachable". Any
            # other non-2xx status (403 permission denied, 500 internal error, etc.) is a real
            # backend problem and is reported as unavailable, fail closed.
            if exc.code == 404:
                raise SecretNotFoundError(
                    f"Vault path {self.mount_path!r} does not contain a key named {name!r} "
                    "(Vault returned 404)."
                ) from exc
            raise SecretsProviderUnavailableError(
                f"Vault at {addr!r} returned HTTP {exc.code} for path {self.mount_path!r}: " f"{exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            # Fail closed: Vault being unreachable (connection refused, timeout, DNS failure,
            # TLS error) is reported as *unavailable*, never silently treated as "this secret
            # doesn't exist" and never papered over with a cached/default value.
            raise SecretsProviderUnavailableError(
                f"Could not reach Vault at {addr!r} within {self.timeout_seconds}s: {exc}"
            ) from exc

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise SecretsProviderUnavailableError(
                f"Vault at {addr!r} returned a response that could not be parsed as JSON: {exc}"
            ) from exc

        try:
            secret_value = body["data"]["data"][name]
        except (KeyError, TypeError) as exc:
            raise SecretNotFoundError(
                f"Vault path {self.mount_path!r} does not contain a key named {name!r}."
            ) from exc
        if not secret_value:
            raise SecretNotFoundError(f"Vault path {self.mount_path!r} key {name!r} is present but empty.")
        return str(secret_value)


def get_secrets_provider() -> SecretsProvider:
    """Factory - the one function services should call; never instantiate
    EnvSecretsProvider/VaultSecretsProvider directly in a service module, so the choice of
    backend stays centralized here and swappable without touching call sites.

    Selects the provider via C360_SECRETS_PROVIDER (env|vault), defaulting to "env" - so every
    existing deployment's behavior is completely unchanged unless a service operator explicitly
    opts in to Vault. This default is what keeps this change backward compatible."""
    kind = os.environ.get("C360_SECRETS_PROVIDER", "env").strip().lower()
    if kind == "env":
        return EnvSecretsProvider()
    if kind == "vault":
        mount_path = os.environ.get("C360_VAULT_SECRET_PATH", "customer360/services")
        return VaultSecretsProvider(mount_path=mount_path)
    raise ValueError(f"Unknown C360_SECRETS_PROVIDER={kind!r} - expected 'env' or 'vault'.")


def validate_secret_configuration(name: str, provider: Optional[SecretsProvider] = None) -> None:
    """Startup-validation hook: a service calls this once at import/startup time to fail fast and
    loud if its required secret cannot be resolved at all, rather than waiting for the first real
    request to discover a misconfiguration. Deliberately discards the resolved value - this
    function's return is None either way; its only job is to raise or not raise."""
    resolved_provider = provider if provider is not None else get_secrets_provider()
    resolved_provider.get_secret(name)  # Raises on failure. Return value is intentionally unused.
