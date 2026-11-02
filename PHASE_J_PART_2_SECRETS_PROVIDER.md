# Phase J (Part 2): Secrets-Provider Abstraction — Implementation Report

## What this closes

`SECRETS_MANAGEMENT.md`'s own "What real production Vault needs" section named an
explicit, not-yet-started gap:

> An actual integration point in the 7 services - none of them currently fetch from
> Vault; they still read `os.environ["C360_API_KEY"]` (see
> `src/services/service_auth.py`). Wiring even one of them to fetch its key from
> Vault at startup instead of the environment is a real, scoped, not-yet-started
> next step.

This phase adds that integration point for all 7 services at once, since they all
share the single `require_api_key` dependency in `src/services/service_auth.py`.

## What was added / changed

- **`src/services/secrets_provider.py` (new)** — `EnvSecretsProvider` (default,
  byte-for-byte the same behavior every service already had) and
  `VaultSecretsProvider` (real HTTP integration against Vault's KV v2 API, using
  the identical endpoint shape `docs/secrets_management_demo/vault_dev_example.sh`
  already exercises against a genuine dev-mode Vault in CI). A `get_secrets_provider()`
  factory selects the backend via `C360_SECRETS_PROVIDER` (`env` default, or `vault`),
  and `validate_secret_configuration()` is a startup-validation hook a service can
  call to fail fast rather than waiting for the first request.
- **`src/services/service_auth.py` (modified)** — `require_api_key()` now resolves
  `C360_API_KEY` through `get_secrets_provider()` instead of a direct
  `os.environ.get(...)` call. Both new failure modes (`SecretsProviderUnavailableError`,
  `SecretNotFoundError`) are turned into the same fail-closed `503` the dependency
  already returned for a missing env var — never a `500`, never a silent pass-through.
  The module docstring's dependency claim was corrected to include the new sibling
  import.
- **`tests/services/test_secrets_provider.py` (new, 31 tests with `test_service_auth.py`)**
  — covers `EnvSecretsProvider`, the factory, Vault configuration failures (missing
  `VAULT_ADDR`/`VAULT_TOKEN`, a real connection-refused address), and a real HTTP
  round trip against a hand-built `http.server` stand-in for Vault (not a mocked
  `urlopen`) — secret retrieval, the `X-Vault-Token` header is actually sent,
  not-found on a missing mount path/key/empty value, and that no error message ever
  contains a token or secret value.
- **`tests/services/test_service_auth.py` (new)** — builds a minimal real FastAPI
  app with one protected route and drives it through a real `TestClient`: missing
  credentials → `503` (not `401`, not `200`), wrong/missing header → `401`, correct
  key → `200`, the `401`/`503` response bodies never echo the caller's guess or the
  real configured key, unprotected routes (`/health`) are unaffected, and a Vault
  backend that is unreachable surfaces through the exact same dependency as the
  same fail-closed `503` with no token leakage.

## Design decisions

- **No new runtime dependency.** The Vault HTTP call uses only `urllib.request`
  (stdlib), mirroring `vault_dev_example.sh`'s own plain-HTTP approach. Every one of
  the 7 services' Dockerfiles already does `COPY src/ ./src/` (grep-verified against
  `bp1_inference_service/Dockerfile`), so this new first-party module ships
  automatically with zero Dockerfile changes.
- **Backward compatible by default.** `EnvSecretsProvider` is the default; every
  existing deployment's behavior is unchanged unless an operator explicitly sets
  `C360_SECRETS_PROVIDER=vault`.
- **Fails closed, never fails open.** An unreachable or unparseable Vault is reported
  as `SecretsProviderUnavailableError`, never treated as "no secret required."
- **Never logs or returns a secret's value.** Only names/paths appear in error
  messages — verified directly by tests, including one that deliberately passes a
  real-looking token value and asserts it is absent from every raised error's text.

## A real bug this caught before it shipped

Running the new Vault round-trip tests (rather than trusting that the code "looked
right") surfaced a genuine logic error: `urllib.error.HTTPError` is a subclass of
`urllib.error.URLError`, so the original `except urllib.error.URLError` branch
silently swallowed Vault's real `404` response for a missing secret path and
misreported it as `SecretsProviderUnavailableError` ("Vault is unreachable") instead
of the correct `SecretNotFoundError` ("this secret genuinely isn't there"). Real
Vault's KV v2 API returns exactly this `404` shape for a missing path. Fixed by
catching `HTTPError` first and treating its `404` as not-found, any other status as
a real backend problem. A second, unrelated typo (`monkeypath` vs `monkeypatch`) in
one new test was also caught by actually running the suite rather than only
syntax-checking it.

## Verification performed

- `tests/services/test_secrets_provider.py` + `tests/services/test_service_auth.py`:
  **31 passed**.
- `tests/services` (all 7 BP services' existing test suites, unaffected by the
  rewiring): **181 passed, 3 skipped**.
- Full 3-batch regression suite: `tests/mlops` **89 passed**;
  `tests/monitoring tests/shared tests/identity_resolution tests/services tests/deployment`
  **475 passed, 3 skipped**; all eight `tests/bp*_...` directories **238 passed,
  6 skipped**. **Total: 802 passed, 9 skipped (811)** — up from the prior session
  baseline of 771 passed / 9 skipped (780) by exactly the 31 new tests added here,
  with zero regressions.
- `black --check`, `isort --check`, `flake8`, `mypy --config-file pyproject.toml`,
  and `bandit -c pyproject.toml` on all 4 new/modified files: **all clean**. One
  `bandit` finding (`B310`, the generic "audit url open for permitted schemes" rule)
  was suppressed with an inline `# nosec B310 - <reason>` comment, following this
  project's own existing convention (`src/deployment/*.py`, `src/mlops/tracking.py`
  use the same pattern) — the URL is built from operator-supplied deployment
  configuration (`VAULT_ADDR`), never attacker-controlled request-time input.

## What this does NOT claim

- This does **not** make Vault production-grade. `SECRETS_MANAGEMENT.md`'s own
  "What real production Vault needs" list — TLS, a durable storage backend,
  auto-unseal, short-lived per-service tokens instead of a long-lived token read
  from the environment — still applies in full and is unaddressed by this module.
  This phase closes the one specific gap that document named ("no integration
  point exists yet"), not the whole list.
- This does **not** change any of the 7 services' actual deployment configuration.
  No service has been switched to `C360_SECRETS_PROVIDER=vault` by this change;
  every deployment keeps reading from the environment exactly as before unless an
  operator explicitly opts in.
- This does **not** cover the remaining Phase I (security) items from the Master
  Engineering Directive — secret-scanning in CI, dependency vulnerability scanning,
  container security scanning, and SBOM generation are separate, not-yet-started
  work, tracked as a follow-up slice of this same phase.
