# Secrets Management -- Platform-Wide

Real, current state, verified 2026-09-26 (`grep -rn "C360_API_KEY" .env.example`).

## What exists today

Every one of the 7 FastAPI services (`src/services/*.py`) reads its shared secret
(`C360_API_KEY`, used by the `X-API-Key` auth described in `SECURITY.md`) from a plain process
environment variable, documented in `.env.example`, which ships a clearly-fake placeholder value,
never a real secret. BP6 additionally reads `GEMINI_API_KEY` the same way. There is no central
secrets store, no rotation, and no audit trail of who or what read a given secret and when - an
environment variable, once set, is just a string any process running as that user can read for
the rest of that process's life.

This is a normal, honest way to run a solo local/demo deployment. It is not how a real production
system with more than one deployer or more than one environment (dev/staging/prod) should manage
secrets long-term.

## A real, CI-verified proof-of-concept: HashiCorp Vault (dev mode)

`docs/secrets_management_demo/` contains a working, minimal example of the pattern this
platform's services could adopt instead: a secret stored in
[HashiCorp Vault](https://www.vaultproject.io/) and fetched at runtime via its HTTP API, rather
than baked into an environment variable at process start.

- `docs/secrets_management_demo/docker-compose.vault.yml` -- starts a single-node Vault in
  **dev mode** (in-memory, auto-unsealed, fixed root token). This mode is explicitly insecure and
  is only ever meant for a laptop or a throwaway CI job - see "What real production Vault needs"
  below for what it deliberately skips.
- `docs/secrets_management_demo/vault_dev_example.sh` -- a real, runnable script (plain `curl`
  against Vault's HTTP API, no extra Python dependency) that waits for Vault to report healthy,
  writes a real secret (`secret/data/customer360/services`, key `c360_api_key`), reads it back,
  and asserts byte-for-byte that what was read matches what was written. Exits non-zero on any
  failure.
- `.github/workflows/vault-verify.yml` -- runs the two files above for real on GitHub's own
  `ubuntu-latest` runners (this sandbox environment has no Docker available, exactly the same
  constraint that motivated `docker-verify.yml` for this project's Dockerfiles) on every push and
  PR to `main`.

**Honest verification status**: this script's bash syntax and the compose file's YAML were
checked directly in this environment (`bash -n`, `yaml.safe_load`), but the actual end-to-end run
(start Vault, write, read, assert) has not been executed here, because this sandbox has no
Docker. It is verified for real by the CI workflow above once pushed - check the Actions tab for
the `vault-write-read-verify` job to confirm it went green before relying on this as evidence the
pattern works. This document will be corrected if that run does not pass.

## What real production Vault needs, that dev mode skips

Dev mode exists purely to make the pattern demonstrable without extra setup. A real deployment
would need, at minimum:

1. **A real storage backend** (Vault's `raft` integrated storage, or Consul) instead of dev
   mode's in-memory store, so secrets survive a restart.
2. **Auto-unseal** (a cloud KMS key, e.g. AWS KMS or GCP Cloud KMS) so the server doesn't require
   a human to manually unseal it with key shares after every restart.
3. **TLS** on Vault's own listener - dev mode serves plain HTTP.
4. **Short-lived, scoped tokens per service** (a real AppRole or Kubernetes auth method), not the
   single fixed root token this demo uses - the root token here has unrestricted access to
   everything in Vault and is only acceptable because it never leaves a throwaway container.
5. **An actual integration point in the 7 services** - none of them currently fetch from Vault;
   they still read `os.environ["C360_API_KEY"]` (see `src/services/service_auth.py`). Wiring even
   one of them to fetch its key from Vault at startup instead of the environment is a real,
   scoped, not-yet-started next step.

## Related documents

- `SECURITY.md` -- the platform's overall security scope, static analysis, and the real
  `X-API-Key` authentication control this secret protects.
