# Monitoring

## Deployment-readiness verdicts (per BP)
`src/deployment/{bp4,bp5,bp6,bp7,bp8}_readiness_verdict.py` (plus the shared `readiness_verdict.py` for
BP1-3) are pure, read-only audits — they inspect what's actually on disk and re-derive a verdict, they
never trust a config file's own status claim. Each one: recomputes the persisted model's SHA-256 hash and
compares it to the recorded value (tamper/drift detection); reloads the bundle and re-predicts to confirm
near-zero drift; confirms the FastAPI service module imports cleanly with `/`, `/health`, and the BP's own
endpoint present; and can optionally re-run that BP's own pytest suite as a subprocess and capture the
real summary. Output: `reports/<bp>/deployment_readiness_verdict.{json,md}`.

## Service health
Every BP1-7 FastAPI service exposes `GET /health`. A missing or corrupt model bundle is recorded as a
structured `.error` on the handle rather than crashing service startup — the service still starts and
`/health` still reports the real problem, it never serves a silent mock prediction.

## CI (`.github/workflows/ci.yml`)
Generic across all 8 BPs — lint (flake8/black/isort), security (bandit), the full pytest suite,
notebook-syntax audit (`scripts/check_notebook_syntax.py`), and a docker-validate job that runs
`docker compose config` plus a build-mechanics smoke test (placeholder artifacts, not real inference)
for every BP's own Docker Compose file.

## What's not yet monitored
No live deployment exists yet (see `ROADMAP.md`), so there is no real uptime, latency, or drift-over-time
data to report here — that section is intentionally absent rather than filled with a hypothetical number.
