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

## BP7 live observability: Prometheus + Grafana (Priority 3, added 2026-09-26)

This is a real, runnable Prometheus + Grafana stack scraping `src/services/bp7_decision_engine_service.py`'s
new `GET /metrics/prometheus` endpoint - not a mockup, not a static screenshot. Everything below
reflects the actual code, config, and dashboard JSON already in this repo (`monitoring/`); nothing
here is aspirational. Scope: BP7 only, matching the deployment-hardening pass this builds on (see
`RENDER_DEPLOYMENT.md`) - BP1-6 do not yet have this endpoint, so the "What's not yet monitored"
section below still applies to them.

### The honesty disclosure this section exists to make explicit

BP7 is a **read-only lookup service over a static, pre-scored artifact** (Gate 5's own
full-population decision-records CSV) - it performs **no live model inference** on any request
(see the service module's own docstring for the full architectural rationale). That has a direct
consequence for what "observability" can honestly mean here, and this dashboard is built to never
blur that line:

| Category | Series | What it really is |
|---|---|---|
| **Live, per-request** | `bp7_http_requests_total`, `bp7_http_request_duration_seconds`, `bp7_lookup_volume_total`, `bp7_recommended_action_served_total` | Real counters/histograms incremented on every real request this process serves. |
| **Live, process-level** | `process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_start_time_seconds`, `bp7_service_uptime_seconds` | `prometheus_client`'s own standard `ProcessCollector`/`PlatformCollector`, not custom code. |
| **Live, the one real governance signal** | `bp7_self_test_last_result`, `bp7_self_test_last_run_timestamp_seconds` | The **exact same real internal-consistency check** `GET /decide/self-test` always performed (see that endpoint's own docstring) - reused, not reinvented, via a shared `_compute_self_test()` helper. Updated whenever a real client calls that endpoint, and optionally by a periodic background `asyncio` task (`C360_SELF_TEST_METRICS_INTERVAL_SECONDS`, default 300s, `0` disables it). |
| **Real, but STATIC (refreshed once per service restart)** | every `bp7_population_*` gauge, `bp7_service_info`, `bp7_gate5_artifact_loaded` | The real, already-computed Gate 5 population-level governance numbers (`gate5_decision_layer_summary.json`'s own `disparate_impact_audit`, `contribution_decomposition_summary`, `weight_rederivation_cross_check`, `champion_stats`) - Gate 5 ran this analysis once, for real, over the full 1,048,575-row population. This is exposed as a queryable time series so it survives in Grafana's history and alongside the live panels, but it is **never** live per-request feature/prediction drift detection, because BP7 makes no live inference to compute one from. |

If you are looking for classic "feature drift" / "prediction drift" the way BP1-3/BP6 would define
it (today's live inference distribution vs. a training baseline): that does not literally apply to
a static lookup service, and this dashboard does not pretend otherwise. The honest analogue this
service CAN expose is the two rows above the "Static Gate 5" section: a real, live, repeatedly
re-run internal-consistency proof, plus the real population-level fairness/reconciliation audit
Gate 5 already computed.

### What's in `monitoring/`

```
monitoring/
  docker-compose.monitoring.yml          # Prometheus + Grafana, provisioned and wired together
  prometheus/prometheus.yml.example      # scrape config TEMPLATE - copy to prometheus.yml, fill in your real key
  grafana/provisioning/datasources/prometheus.yml   # auto-registers the Prometheus datasource
  grafana/provisioning/dashboards/dashboard.yml     # auto-loads the dashboard below
  grafana/dashboards/customer360_bp7_production_monitor.json   # the actual dashboard (24 panels)
```

### Running it

1. Start a real BP7 instance first (either locally or your real Render deployment - see
   `RENDER_DEPLOYMENT.md`). Locally:
   ```
   docker compose -f src/services/docker/bp7_decision_engine_service/docker-compose.yml up --build
   ```
2. Create your real, untracked Prometheus config from the committed template (same `.env.example`
   -> `.env` convention this project already uses for secrets - see `SECURITY.md`):
   ```
   cp monitoring/prometheus/prometheus.yml.example monitoring/prometheus/prometheus.yml
   ```
   Edit `monitoring/prometheus/prometheus.yml`: replace `REPLACE_WITH_YOUR_REAL_C360_API_KEY` with
   your real `C360_API_KEY` value. `GET /metrics/prometheus` requires the same `X-API-Key` header
   as every other BP7 governance endpoint (see `SECURITY.md`) - it is never left unauthenticated.
   Prometheus's native `authorization:` scrape-config block only supports `Authorization: Bearer`
   tokens, so this uses Prometheus's `http_headers` field (2.47+) to send an arbitrary header name
   instead.
3. Start the observability stack (run from the project root):
   ```
   docker compose -f monitoring/docker-compose.monitoring.yml up
   ```
4. Open Grafana at `http://localhost:3000` (default login `admin` / `admin`, or your real
   `GRAFANA_ADMIN_PASSWORD` if you set one - change the password on first login either way) and
   open the **Customer360 Navigator** folder - the **Customer360 Navigator - BP7 Production
   Monitor** dashboard is already provisioned, no manual import needed. Prometheus itself is at
   `http://localhost:9090` if you want to run raw PromQL queries directly.

To point Prometheus at your **real, deployed Render instance** instead of (or alongside) a local
one, uncomment the `bp7-render-production` job in `monitoring/prometheus/prometheus.yml` and fill
in your real Render service name - Prometheus scrapes it directly over HTTPS, no VPN/tunnel
needed, since Render assigns your service a real public HTTPS URL.

### Reaching a local BP7 instance from inside the Prometheus container

`docker-compose.monitoring.yml` is a standalone compose file - it does not join BP7's own Docker
network, and does not require any change to
`src/services/docker/bp7_decision_engine_service/docker-compose.yml`. Instead it adds an
`extra_hosts: host.docker.internal:host-gateway` entry to the Prometheus container, so
`host.docker.internal:8007` resolves to the BP7 container's port published on your host machine.
This works out of the box on Docker Desktop (Mac/Windows) and on Linux with Docker Engine 20.10+.

### What each dashboard section is, honestly

- **Service Health & Availability** (live): API availability (Prometheus's own real `up` gauge,
  averaged over 24h), p95 latency, requests and errors in the last hour.
- **Live Governance Signal**: the real self-test's last result and how stale it is (minutes since
  it last actually ran), plus the real, live recommended-action distribution this process has
  actually served since it started.
- **Static Gate 5 Population Governance** (refreshed once per restart, explicitly labeled as such
  in the dashboard itself): the real disparate-impact audit, contribution-reconstruction
  exactness, weight-rederivation consistency, and population intervention-flag rate Gate 5 already
  computed over the full persisted population, plus whether this instance's Gate 5 artifacts
  loaded at all, plus a real build/version info table (`GET /version`'s own honest "no semantic
  version, champion+timestamp is the real proxy" disclosure applies here too).
- **Resource Usage & Process**: real CPU/memory/uptime from `prometheus_client`'s own standard
  collectors - not custom instrumentation.
- **Request Rate & Latency Over Time**: real request-rate-by-status and p50/p95/p99 latency time
  series.

### What this does NOT give you

- **Not a claim of BP1-6 observability.** Only BP7 was in scope for this pass - the other 6
  services do not yet expose `/metrics/prometheus`; see "What's not yet monitored" below.
- **Not literal feature/prediction drift detection.** See the disclosure table above - BP7 has no
  live inference to drift-detect against a training baseline. The "Static Gate 5 Population
  Governance" panels are the real, honest thing a static lookup service can expose instead.
- **Not a managed/hosted Prometheus or Grafana.** This is a local (or self-hosted)
  `docker compose` stack you run yourself, same "no external account creation on your behalf"
  boundary already established for Render (see `RENDER_DEPLOYMENT.md`).
- **The in-memory rate limiter and self-test background refresh remain per-process** (see
  `SECURITY.md`) - if you ever run more than one BP7 instance, each has its own independent
  self-test cadence and rate-limit counters; Prometheus's own `job`/`instance` labels (or the
  `environment` label this config adds) are what let you tell multiple scraped instances apart in
  the dashboard.

## What's not yet monitored
BP7 now has the real, live Prometheus + Grafana stack described above (added 2026-09-26) once it is
actually deployed and a Prometheus instance is actually scraping it - this repo ships the real
config and dashboard, but nothing here claims a stack is running unattended right now unless you
have started one yourself. BP1-6 have no equivalent yet - only BP7 was in scope for this pass. For
every other service, there is still no real uptime, latency, or drift-over-time data to report
here beyond what's described above - that section is intentionally scoped rather than filled with
a hypothetical number for services this pass didn't touch.
