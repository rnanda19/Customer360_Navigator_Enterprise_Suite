# Security

## Static analysis
`bandit` runs in CI on every push across `src/` and `tests/`. Current real result: **0 findings**
(two narrow, documented conventions are explicitly skipped: `B101` assert-statements in test files, and
`B404`/`B603` subprocess usage in the deployment-readiness verdict modules, which is its whole job —
each suppression is an inline `# nosec` on the exact flagged line, never a blanket ignore).

## Secrets
No API key, token, or credential is ever committed. Real secrets this project uses (a Google Gemini
API key for BP6, and the shared API key described below) are read from environment variables at
runtime only. `.gitignore` excludes `.env`, `*.pem`, and `*.key` project-wide.

## Authentication (added 2026-09-26)
All 7 FastAPI services (`src/services/*.py`) require an `X-API-Key` header matching the
`C360_API_KEY` environment variable, enforced by a shared dependency
(`src/services/service_auth.py::require_api_key`) on every route except `GET /` and `GET /health`
(left open for container orchestrators, load balancers, and uptime monitors to probe with no
secret). Design, fail-closed on both sides:

- A service with `C360_API_KEY` unset in its environment refuses every protected request with
  `503` naming exactly what to set - it never silently falls back to accepting unauthenticated
  requests, matching this project's zero-fabrication/no-silent-failure convention.
- A request with a missing or wrong key gets `401`. Comparison uses `hmac.compare_digest`, not
  `==`, so a wrong key is rejected in constant time.
- One shared secret across all 7 services (not one per service) - this project ships one
  deployment unit (`docker-compose.yml` aggregates all 7), matching the precedent BP6's own
  single shared `GEMINI_API_KEY` already set.

Set `C360_API_KEY` in `.env` (see `.env.example`) or your shell before starting any service -
`docker-compose.yml` and each per-service `docker-compose.yml` under `src/services/docker/`
require it (`${C360_API_KEY:?...}`) and refuse to start a container without it.

## Dependencies
`requirements.txt` and `pyproject.toml` pin minimum versions for every real direct import found in `src/`
(derived by grepping actual imports, not copied wholesale from an unrelated template).

## Reporting a vulnerability
This is an independent portfolio project, not a maintained production service. If you find a real issue,
open a GitHub issue on this repository describing it — there is no dedicated security contact or bug
bounty program.
