"""
src/services/bp7_decision_engine_service.py — Customer360 Navigator

BP7 (Customer Navigator Decision Engine) real-time decision-record lookup FastAPI service — Gate 6
(Productization, Monitoring & Governance) deliverable. Self-contained and independently deployable
(run with `uvicorn services.bp7_decision_engine_service:app`), matching BP1-6's own
one-service-file-per-problem pattern.

Per Master Plan paragraph 205 ("Per-BP governance set, required before Gate 6 sign-off:
MODEL_CARD.md, CHANGELOG.md, and — for BP6/BP7 — a runnable FastAPI service with a live self-test
proving API output matches direct computation."), this file is itself part of BP7's Gate 6
deliverable, not an optional Hardening extra (Section 18.1's "Optional FastAPI + Docker + MLflow"
does not apply to BP6/BP7 — theirs is mandatory).

BP7 is architecturally different from BP6: BP6 fits no persisted artifact and makes a real, live
external API call (Gemini) on every `/resolve`; BP7 makes NO external call at all — it is a
deterministic weighted-rule engine (`features.bp7_decision_engine_features.score_priority_rule`)
that Gate 5 already applied once, for real, to the full real population and persisted at
`notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_full_population_decision_records.csv`
(one row per real `Complaint ID`: `priority_score`/`intervention_flag`/`recommended_action`/
`reason_codes` plus every real upstream field that fed it — `FINAL_OUTPUT_COLUMNS`, unchanged).
This service is therefore architecturally closer to `services.bp4_decision_service` (read-only
lookup over a real, persisted decision artifact, never a live model/API call) than to
`services.bp6_resolution_service` — see BP4's own module docstring for the shared "reads a real
persisted artifact, never predicts or generates" rationale, reused here for the identical reason.

Deliberately standalone: does NOT import `src/services/service_common.py` (its ModelBundleHandle/
HealthResponse are model-bundle-shaped, BP1/BP2/BP3-specific) — reimplements project-root
resolution locally, identically, matching BP4's and BP6's own established precedent for a service
with no model bundle.

Point-lookup strategy — never an eager full-file load: the real Gate 5 CSV is large (~540MB,
1,048,575 rows). `GET /decide/{complaint_id}` runs a real, per-request `polars.scan_csv(...)
.filter(...)` LAZY scan against it (never loaded whole into memory at startup). At STARTUP, this
service only checks the file's real existence and its real schema (column names, via a zero-row
`.limit(0).collect()` — never a full read), plus loads Gate 5's own already-computed summary JSON
(`gate5_decision_layer_summary.json`) for the `/health` response's population-level real statistics
(row count, champion rule scheme, weights, threshold) — REUSED, never recomputed: re-deriving those
at every service startup would mean re-scoring the full 1,048,575-row population on every restart,
which Gate 5's own notebook already did once, for real, and persisted.

Zero-fabrication rule applies here exactly as everywhere else in this project: if the real Gate 5
CSV (or its summary JSON) is not present on disk, this service still starts (so it can be
health-checked) but serves 503 on `/decide` and `/decide/self-test` — never a mock/fabricated
decision record.

On the self-test's own honesty (BP7 has no external API call to test, unlike BP6's real Gemini
call — see that module's own docstring for the contrast this service deliberately does NOT copy):
`GET /decide/self-test` performs a REAL internal-consistency check on `sample_size` real,
already-scored rows read from the real Gate 5 CSV (deterministic — the first `sample_size` rows in
the file's own on-disk order, never random/unseeded; re-running against the same unchanged artifact
always samples the identical rows). It reuses
`features.bp7_decision_engine_features.summarize_contribution_decomposition` (Gate 4/5's own real
reconciliation function, imported and called UNMODIFIED, never reimplemented) to independently
verify `contribution_bp2 + contribution_bp3 + contribution_bp4` reconstructs `priority_score`
exactly for every sampled row — plus two further real, structural checks this endpoint performs
directly on the fetched rows: (a) `intervention_flag == (priority_score >=
DEFAULT_INTERVENTION_THRESHOLD)` for every row (the real, imported threshold constant, never a
hardcoded literal), and (b) every row's own `recommended_action` is one of the known real vocabulary
and structurally consistent with its own `intervention_flag` (`STANDARD_QUEUE` iff not flagged, one
of the three escalation/priority actions iff flagged, `UNSCORED_MISSING_UPSTREAM_INPUT` iff
`priority_score` is null). It also fetches the SAME sampled `Complaint ID`s via two
independently-constructed lazy-scan calls and asserts the two reads are field-for-field identical,
proving this service's own read path introduces no drift versus the real artifact on disk.

This is disclosed here, and again in the endpoint's own docstring and response, so it is never
mistaken for a claim that `score_priority_rule` itself was re-run end-to-end from upstream inputs:
the real Gate 5 CSV does not carry `bp4_recurring_flag`/`bp4_high_volume_flag` per row (only the
already-computed `reason_codes` string that encodes them), so a full, from-scratch re-derivation of
`reason_codes`/`recommended_action` via `score_priority_rule` is not reproducible from this artifact
alone — never attempted here with a fabricated stand-in for those two missing columns. The checks
above are the honest, real thing this service CAN verify from what it actually serves.

PRODUCTION-HARDENING ADDITION (2026-09-26 — Priority 2, "deploy BP7 as a real public API"):
everything below this point is additive to the Gate 6 deliverable above, never a change to the
lookup semantics already described. Added: explicit `/v1` API versioning (every route below is
served both bare, for backward compatibility with the existing test suite and any existing
caller, and again under `/v1` - every route decorated twice directly on `app`; see the note
near the end of this docstring on why an `APIRouter` was tried first and reverted); `GET
/version` (real app/API version, a best-effort real git commit — never fabricated, see
`_resolve_git_commit()` — and the same
honest "no semantic version, champion+timestamp is the real proxy" disclosure already used on
`index.html`'s Dataset & Model Provenance panel); `GET /model-info` (the real Gate 5 decision-layer
metadata — champion rule scheme, weights, threshold, disparate-impact audit — explicitly labeled
as a lookup service's metadata, never a model bundle, since BP7 fits no model); `GET /metrics`
(real, in-process request/latency counters — explicitly disclosed as per-process, non-distributed,
no Prometheus wired up, never dressed up as more than it is); `POST /score` and `POST /decision`
(batch form of the existing `GET /decide/{complaint_id}` lookup, accepting a JSON body of
`complaint_ids` instead of one path parameter each — `/score` returns the real
`priority_score`/`contribution_bp2/3/4` fields, `/decision` returns the real
`intervention_flag`/`recommended_action`/`reason_codes` fields, both reading the SAME real Gate 5
row per id via one batched `Complaint ID`-`is_in(...)` lazy-scan filter rather than N separate
scans — no new inference of any kind, purely a different real-field projection and a batched read
path over the identical real lookup `GET /decide/{complaint_id}` already performs); a
request-ID (`X-Request-ID`) and latency (`X-Response-Time-Ms`) middleware; a consistent JSON error
envelope (`detail` kept for backward compatibility, plus `error_code`/`status_code`/`request_id`)
on every 4xx/5xx, including validation errors and any truly unhandled exception; and an in-memory,
per-process, per-API-key-or-IP rate limiter (`C360_RATE_LIMIT_PER_MINUTE`, default 120/minute,
0 disables it) — explicitly disclosed as non-distributed (see `/metrics`' own disclosure and
`RENDER_DEPLOYMENT.md`), which is an honest fit for the single-instance Render free-tier deployment
this hardening pass targets, never a claim of a production-grade distributed limiter. No new
runtime dependency was added for any of this — every addition below uses only the Python standard
library (`uuid`, `time`, `threading`, `subprocess`, `datetime`) plus `fastapi`/`pydantic`, already
installed by this service's own Dockerfile.

ON THE /v1 MECHANISM (real bug found and fixed during this hardening pass's own sandbox
testing, 2026-09-26): an initial version of this file used a single `fastapi.APIRouter`,
decorated every route once, and mounted it twice via `app.include_router(router)` /
`app.include_router(router, prefix="/v1")`. That is idiomatic FastAPI, but this project's
pinned FastAPI/Starlette version (grep/import-verified: fastapi 0.141.1, starlette 1.7.0)
represents an included sub-router as one `fastapi.routing._IncludedRouter` wrapper object in
`app.routes`, rather than flattening its child routes into that list the way older versions
did - HTTP requests still routed correctly either way (verified directly against a real
TestClient), but `src/deployment/bp7_readiness_verdict.py`'s own real
`service_required_routes_present` check (and any other tool that plain-walks `app.routes`
expecting flat `Route` objects) could no longer see the wrapped routes and would report a
false FAIL. Rather than patch that unrelated governance script around this one file's
internal implementation choice, every route below is instead decorated TWICE directly on
`app` (once at its bare path, once again at the same path under `/v1`, with
`include_in_schema=False` on the `/v1` copy so `/docs` shows one canonical operation per
route) - no `APIRouter` anywhere in this file, matching every other BP service in this
project (none of which use one either).

PRIORITY 3 ADDITION (2026-09-26 — "add real observability: Prometheus + Grafana"): adds
`GET /metrics/prometheus` (bare + `/v1`, auth-protected via the same `require_api_key`
dependency as `/metrics`, subject to the same rate limiter — a deliberate consistency choice,
not an oversight; see `MONITORING.md`), serving real Prometheus exposition-format text via a
dedicated `prometheus_client.CollectorRegistry` (never the library's global default registry —
this module is `importlib.reload()`'d before every test in
`tests/services/test_bp7_decision_engine_service.py`, and a dedicated per-reload registry is
what avoids "Duplicated timeseries in CollectorRegistry" across tests, exactly like the
pre-existing `_METRICS_STATE`/`_RATE_LIMIT_STATE` module-level dicts already reset safely per
reload for the identical reason). This is the first genuinely NEW runtime dependency added to
this service since the Gate 6 deliverable above (`prometheus-client` — see `requirements.txt`/
`pyproject.toml`/this service's own Dockerfile); every earlier addition in this file used only
the standard library plus `fastapi`/`pydantic`, already installed.

What is exposed, and — critically — what is honestly disclosed about what each series really
measures (this distinction is repeated in `MONITORING.md`, never left implicit):
  - Real, live, per-request series: `bp7_http_requests_total` / `bp7_http_request_duration_
    seconds` (every request this instance serves, by method/route/status), `bp7_lookup_volume_
    total` (real `/decide`, `/score`, `/decision` lookups, by whether the id was found), and
    `bp7_recommended_action_served_total` (the real decision distribution actually served).
  - Real process-level series for free from `prometheus_client`'s own standard collectors
    (`ProcessCollector`/`PlatformCollector`, registered onto this module's dedicated registry
    below - not custom code): `process_cpu_seconds_total`, `process_resident_memory_bytes`, and
    `process_start_time_seconds` (the user's explicit "CPU, memory, service uptime" ask).
  - Real, but STATIC, per-process-restart series: `bp7_population_*` gauges and `bp7_service_
    info` — these are the real, already-computed Gate 5 population-level governance numbers
    (`gate5_decision_layer_summary.json`'s own `disparate_impact_audit`, `contribution_
    decomposition_summary`, `weight_rederivation_cross_check`, `champion_stats`), refreshed
    once at service (re)start, NEVER recomputed live per request. BP7 makes no live inference
    (see this docstring's own opening sections) — there is no live per-request feature/
    prediction distribution to compare against a training baseline the way there would be for
    BP1-3/BP6, so these are deliberately NOT presented as live drift/fairness detection. They
    are the honest, real thing a static lookup service CAN expose: the population-level
    governance audit Gate 5 already ran once, made queryable as a time series.
  - The one genuinely LIVE governance signal this service can honestly expose:
    `bp7_self_test_last_result` / `bp7_self_test_last_run_timestamp_seconds`, reusing the exact
    same real internal-consistency computation `GET /decide/self-test` already performed (see
    `_compute_self_test()`, factored out of that route so both it and the new optional
    background refresh below call the identical real logic). Updated (a) whenever a real
    client calls that endpoint, and (b) optionally on a periodic background `asyncio` task
    (`C360_SELF_TEST_METRICS_INTERVAL_SECONDS`, default 300s, `0` disables it) started in
    `lifespan` — so a Grafana panel wired to this series reflects a real, live, repeatedly-
    re-run check, not a value frozen at startup, while never fabricating a drift statistic this
    service has no live inference to compute.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import polars as pl
from fastapi import Depends, FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi import Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from pydantic import BaseModel, Field

from services.service_auth import require_api_key

BP_ID = "bp7"
DEFAULT_SELF_TEST_SAMPLE_SIZE = 25
MAX_SELF_TEST_SAMPLE_SIZE = 500

# Production-hardening constants (2026-09-26 addition — see module docstring).
MAX_BATCH_LOOKUP_SIZE = 100
API_VERSIONS_SUPPORTED = ["v1"]
RATE_LIMIT_PER_MINUTE_ENV_VAR = "C360_RATE_LIMIT_PER_MINUTE"
DEFAULT_RATE_LIMIT_PER_MINUTE = 120
GIT_COMMIT_ENV_VAR = "C360_GIT_COMMIT"

# Priority 3 observability constants (2026-09-26 addition — see module docstring). Controls the
# optional periodic background refresh of the live self-test gauges; a value <= 0 disables it
# entirely (the gauges are then only updated by real client calls to GET /decide/self-test).
SELF_TEST_METRICS_INTERVAL_ENV_VAR = "C360_SELF_TEST_METRICS_INTERVAL_SECONDS"
DEFAULT_SELF_TEST_METRICS_INTERVAL_SECONDS = 300.0
# Paths exempt from rate limiting - orchestrator/uptime-monitor probes and interactive docs, same
# spirit as service_auth's own "/ and /health stay open" convention (never for the auth-protected
# query/governance endpoints below).
_RATE_LIMIT_EXEMPT_PATHS = frozenset(
    {
        "/",
        "/health",
        "/version",
        "/v1",
        "/v1/",
        "/v1/health",
        "/v1/version",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# The real, full recommended_action vocabulary `features.bp7_decision_engine_features
# ._recommended_action_expr()` can produce (verified live against that real function's own source,
# never guessed) - used below only for the self-test's structural-consistency check, never to gate
# `/decide` itself (which returns whatever real value the persisted artifact actually holds, even
# if this vocabulary were ever to drift).
KNOWN_RECOMMENDED_ACTIONS = frozenset(
    {
        "UNSCORED_MISSING_UPSTREAM_INPUT",
        "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
        "ESCALATE_SENIOR_REVIEWER",
        "PRIORITY_QUEUE_REVIEW",
        "STANDARD_QUEUE",
    }
)


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every service/notebook in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) — reimplemented here (not imported from
    service_common.py), matching BP4's and BP6's own precedent for a service with no model
    bundle."""
    env_override = os.environ.get("C360_PROJECT_ROOT")
    if env_override:
        candidate = Path(env_override)
        if (candidate / marker_filename).exists():
            return candidate
        raise RuntimeError(
            f"C360_PROJECT_ROOT is set to {candidate} but {marker_filename} was not found there. "
            "Fix the environment variable rather than removing this check."
        )
    start = Path.cwd()
    current = start
    for _ in range(8):
        if (current / marker_filename).exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(
        f"Could not resolve PROJECT_ROOT: no {marker_filename} found by walking up from {start}. "
        "Set the C360_PROJECT_ROOT environment variable to the "
        "Customer360_Navigator_Enterprise_Suite folder before starting this service."
    )


def _default_records_csv_path(project_root: Path) -> Path:
    return (
        project_root
        / "notebooks"
        / "bp7_customer_navigator_decision_engine"
        / "artifacts"
        / "gate5_full_population_decision_records.csv"
    )


def _default_summary_json_path(project_root: Path) -> Path:
    return (
        project_root
        / "notebooks"
        / "bp7_customer_navigator_decision_engine"
        / "artifacts"
        / "gate5_decision_layer_summary.json"
    )


class DecisionEngineHandle:
    """Loads (or fails to load) BP7's real, static Gate 5 prerequisites at service startup — the
    real, persisted full-population decision-records CSV path (schema-checked, never fully read)
    and Gate 5's own real summary JSON (fully read — it is small). Never raises past __init__ — any
    missing/invalid prerequisite is recorded as `self.error`, not thrown, so the service can still
    start, serve an honest /health response, and return 503 on every query endpoint — same pattern
    as every other BP's own service handle in this project (`ModelBundleHandle`,
    `DecisionArtifactHandle`, `ResolutionAssistantHandle`)."""

    def __init__(self, records_csv_path: Path, summary_json_path: Path):
        self.records_csv_path = records_csv_path
        self.summary_json_path = summary_json_path
        self.schema_columns: Optional[list[str]] = None
        self.summary: Optional[dict[str, Any]] = None
        self.error: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if not self.records_csv_path.exists():
            self.error = (
                f"{self.records_csv_path} does not exist. Run BP7 Gate 5 for real first "
                "(bp7_customer_navigator_decision_engine_g5_decision_layer_reporting.ipynb)."
            )
            return
        if not self.summary_json_path.exists():
            self.error = f"{self.summary_json_path} does not exist. Run BP7 Gate 5 for real first."
            return

        try:
            schema_probe = pl.scan_csv(self.records_csv_path).limit(0).collect()
        except Exception as e:  # noqa: BLE001 - any parse failure means "not loaded", never a crash
            self.error = f"Gate 5 records CSV at {self.records_csv_path} failed schema probe: {e}"
            return
        if "Complaint ID" not in schema_probe.columns:
            self.error = f"{self.records_csv_path} is missing the required 'Complaint ID' column."
            return

        import json

        try:
            with open(self.summary_json_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except (OSError, ValueError) as e:
            self.error = f"Gate 5 summary JSON at {self.summary_json_path} failed to load: {e}"
            return

        self.schema_columns = list(schema_probe.columns)
        self.summary = summary

    @property
    def is_loaded(self) -> bool:
        return self.schema_columns is not None and self.summary is not None


_handle: Optional[DecisionEngineHandle] = None


def _get_handle() -> DecisionEngineHandle:
    if _handle is None:
        raise HTTPException(status_code=503, detail="BP7 decision-engine handle not initialized.")
    return _handle


# ---------------------------------------------------------------------------
# Prometheus metrics (2026-09-26 Priority 3 addition — "add real observability: Prometheus +
# Grafana"; see the module docstring for the full disclosure on live-per-request vs. static-
# per-restart series). A DEDICATED CollectorRegistry - never prometheus_client's global default
# `REGISTRY` - so this module can be safely `importlib.reload()`'d (the test suite's own
# `service_module` fixture reloads this module before every test; reusing the global default
# registry across reloads would raise "Duplicated timeseries in CollectorRegistry" on the second
# test). This mirrors the pre-existing `_METRICS_STATE`/`_RATE_LIMIT_STATE` module-level dicts
# above, which already reset safely per reload for the identical reason.
# ---------------------------------------------------------------------------

PROM_REGISTRY = CollectorRegistry()

# Real CPU/memory/process-uptime metrics (the user's explicit "CPU, memory" ask) - prometheus_
# client's own standard-library collectors, NOT custom code. These attach to the global default
# registry automatically at import time, but a DEDICATED registry (see above) gets nothing for
# free, so they are registered onto PROM_REGISTRY explicitly here: process_cpu_seconds_total,
# process_resident_memory_bytes, process_virtual_memory_bytes, process_start_time_seconds,
# process_open_fds/process_max_fds, and python_info.
ProcessCollector(registry=PROM_REGISTRY)
PlatformCollector(registry=PROM_REGISTRY)

HTTP_REQUESTS_TOTAL = Counter(
    "bp7_http_requests_total",
    "Total HTTP requests served by this BP7 instance, by method, route template, and status code.",
    ["method", "route", "status_code"],
    registry=PROM_REGISTRY,
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "bp7_http_request_duration_seconds",
    "HTTP request latency in seconds, by method and route template.",
    ["method", "route"],
    registry=PROM_REGISTRY,
)
SERVICE_UPTIME_SECONDS = Gauge(
    "bp7_service_uptime_seconds",
    "Seconds since this BP7 process started (module import time).",
    registry=PROM_REGISTRY,
)
SERVICE_INFO = Gauge(
    "bp7_service_info",
    "Always 1 - static build/version identity exposed as labels (the Prometheus 'info pattern', "
    "matching how kube_pod_info/up etc. work) - never a numeric measurement in its own right.",
    ["app_version", "git_commit", "champion_rule_scheme", "gate5_generated_at_utc"],
    registry=PROM_REGISTRY,
)
LOOKUP_VOLUME_TOTAL = Counter(
    "bp7_lookup_volume_total",
    "Real Complaint ID lookups served across /decide, /score, /decision, by endpoint and whether "
    "the id was found in the real Gate 5 CSV.",
    ["endpoint", "found"],
    registry=PROM_REGISTRY,
)
RECOMMENDED_ACTION_SERVED_TOTAL = Counter(
    "bp7_recommended_action_served_total",
    "Real recommended_action values actually served to callers, by value - the real, live decision "
    "distribution (contrast bp7_population_intervention_flag_rate, the static Gate 5 population rate).",
    ["recommended_action"],
    registry=PROM_REGISTRY,
)

# Population-level governance gauges - REAL, already-computed Gate 5 numbers (see
# gate5_decision_layer_summary.json), refreshed once per service (re)start by
# _update_static_gauges() below. Deliberately NOT live per-request feature/prediction drift: BP7
# makes no live inference (see module docstring), so there is no live per-request distribution to
# compare against a training baseline the way there would be for BP1-3/BP6. These are the honest,
# real, population-level fairness/reconciliation numbers Gate 5 already computed once over the
# full persisted population, exposed as a queryable time series - see MONITORING.md for the same
# disclosure repeated alongside the dashboard that renders them.
POPULATION_ADVERSE_IMPACT_RATIO = Gauge(
    "bp7_population_adverse_impact_ratio",
    "Real Gate 5 disparate_impact_audit.adverse_impact_ratio (four-fifths-rule selection-rate ratio).",
    registry=PROM_REGISTRY,
)
POPULATION_FOUR_FIFTHS_RULE_FLAGGED = Gauge(
    "bp7_population_four_fifths_rule_flagged",
    "1 if Gate 5's real disparate_impact_audit.flagged_four_fifths_rule is true, else 0.",
    registry=PROM_REGISTRY,
)
POPULATION_CONTRIBUTION_RECONSTRUCTION_EXACT = Gauge(
    "bp7_population_contribution_reconstruction_exact",
    "1 if Gate 5's real contribution_decomposition_summary.reconstruction_exact_within_tolerance "
    "is true across the full persisted population, else 0.",
    registry=PROM_REGISTRY,
)
POPULATION_WEIGHT_REDERIVATION_CONSISTENT = Gauge(
    "bp7_population_weight_rederivation_consistent",
    "1 iff Gate 5's real weight_rederivation_cross_check reported cramers_v_matches_config AND "
    "bp4_coverage_matches_config AND weights_match_config all true, else 0.",
    registry=PROM_REGISTRY,
)
POPULATION_INTERVENTION_FLAG_RATE = Gauge(
    "bp7_population_intervention_flag_rate",
    "Real Gate 5 champion_stats.intervention_flag_rate across the full persisted population.",
    registry=PROM_REGISTRY,
)
GATE5_ARTIFACT_LOADED = Gauge(
    "bp7_gate5_artifact_loaded",
    "1 if this instance's real Gate 5 records CSV + summary JSON loaded successfully at startup, else 0.",
    registry=PROM_REGISTRY,
)

# The one genuinely LIVE governance signal this static-lookup service can honestly expose (see
# module docstring): the real internal-consistency self-test's own last result, updated whenever a
# real client calls GET /decide/self-test AND, optionally, by the periodic background refresh -
# see _self_test_metrics_refresh_loop() below.
SELF_TEST_LAST_RESULT = Gauge(
    "bp7_self_test_last_result",
    "1 if the real /decide/self-test internal-consistency check last passed, 0 if it last failed. "
    "Absent (no data) until the first real self-test run since this process started.",
    registry=PROM_REGISTRY,
)
SELF_TEST_LAST_RUN_TIMESTAMP = Gauge(
    "bp7_self_test_last_run_timestamp_seconds",
    "Unix timestamp (seconds) of the last real self-test run (client-triggered or "
    "background-refreshed). Compare against time() to build a real staleness/'Data Quality' panel.",
    registry=PROM_REGISTRY,
)


def _update_static_gauges(handle: "DecisionEngineHandle") -> None:
    """Populates the population-level and service-info gauges from the real, already-loaded Gate 5
    summary. Called once from `lifespan()` right after `_handle` is set, and again defensively at
    the top of `GET /metrics/prometheus` (idempotent - re-setting the same real values) so a scrape
    never reads stale/default values if it somehow lands before `lifespan`'s own startup call did."""
    GATE5_ARTIFACT_LOADED.set(1.0 if handle.is_loaded else 0.0)
    summary = handle.summary or {}
    SERVICE_INFO.labels(
        app_version=app.version,
        git_commit=_resolve_git_commit() or "unknown",
        champion_rule_scheme=summary.get("champion_rule_scheme") or "unknown",
        gate5_generated_at_utc=summary.get("generated_at_utc") or "unknown",
    ).set(1)
    if not handle.is_loaded:
        return

    audit = summary.get("disparate_impact_audit") or {}
    if audit.get("adverse_impact_ratio") is not None:
        POPULATION_ADVERSE_IMPACT_RATIO.set(float(audit["adverse_impact_ratio"]))
    if "flagged_four_fifths_rule" in audit:
        POPULATION_FOUR_FIFTHS_RULE_FLAGGED.set(1.0 if audit["flagged_four_fifths_rule"] else 0.0)

    decomposition = summary.get("contribution_decomposition_summary") or {}
    if "reconstruction_exact_within_tolerance" in decomposition:
        POPULATION_CONTRIBUTION_RECONSTRUCTION_EXACT.set(
            1.0 if decomposition["reconstruction_exact_within_tolerance"] else 0.0
        )

    weight_check = summary.get("weight_rederivation_cross_check") or {}
    if weight_check:
        all_consistent = all(
            weight_check.get(key) is True
            for key in ("cramers_v_matches_config", "bp4_coverage_matches_config", "weights_match_config")
        )
        POPULATION_WEIGHT_REDERIVATION_CONSISTENT.set(1.0 if all_consistent else 0.0)

    champion_stats = summary.get("champion_stats") or {}
    if champion_stats.get("intervention_flag_rate") is not None:
        POPULATION_INTERVENTION_FLAG_RATE.set(float(champion_stats["intervention_flag_rate"]))


class SelfTestNotConfiguredError(RuntimeError):
    """Raised by `_compute_self_test()` when the real Gate 5 artifacts are not loaded. A plain
    exception (never `HTTPException`) because this is also called from a background asyncio task
    with no HTTP request to attach a status code to - the HTTP route below converts this to the
    real 503 it already returned before this refactor."""


class SelfTestEmptyArtifactError(RuntimeError):
    """Raised by `_compute_self_test()` when the real Gate 5 records CSV contains zero rows. Same
    plain-exception rationale as `SelfTestNotConfiguredError` above."""


def _compute_self_test(handle: DecisionEngineHandle, sample_size: int) -> "SelfTestResponse":
    """The real internal-consistency computation behind `GET /decide/self-test` - factored out
    (2026-09-26 Priority 3 addition) so BOTH the HTTP route below AND the optional periodic
    background metrics-refresh task (`_self_test_metrics_refresh_loop()`) call the exact same real
    logic, never two implementations that could silently drift apart. Behavior is byte-for-byte
    identical to this project's original Gate 6 `decide_self_test()` route body - see that
    function's own docstring (preserved below) for the full rationale of what this self-test does
    and does not prove."""
    if not handle.is_loaded:
        raise SelfTestNotConfiguredError(f"BP7 decision engine is not configured: {handle.error}")

    # Two independently-constructed lazy scans over the same real artifact - deterministic (the
    # file's own on-disk order, never random/unseeded) - proving the read path is reproducible.
    sample_a = pl.scan_csv(handle.records_csv_path).limit(sample_size).collect()
    sample_b = pl.scan_csv(handle.records_csv_path).limit(sample_size).collect()
    if sample_a.height == 0:
        raise SelfTestEmptyArtifactError("Real Gate 5 records CSV contains zero rows.")

    # Reuse (never reinvent) Gate 4/5's own real reconciliation function.
    from features.bp7_decision_engine_features import (
        DEFAULT_INTERVENTION_THRESHOLD,
        summarize_contribution_decomposition,
    )

    threshold = float((handle.summary or {}).get("intervention_threshold", DEFAULT_INTERVENTION_THRESHOLD))
    decomposition_summary = summarize_contribution_decomposition(sample_a)

    row_checks: list[SelfTestRowCheck] = []
    for row_a, row_b in zip(sample_a.iter_rows(named=True), sample_b.iter_rows(named=True)):
        dual_read_identical = row_a == row_b

        priority_score = row_a["priority_score"]
        intervention_flag = bool(row_a["intervention_flag"])
        if priority_score is None:
            intervention_matches_rule = intervention_flag is False
        else:
            intervention_matches_rule = intervention_flag == (priority_score >= threshold)

        # An unscored row (priority_score is null, structurally UNSCORED_MISSING_UPSTREAM_INPUT)
        # has no contribution_bp2/3/4 to reconstruct - vacuously consistent, matching
        # summarize_contribution_decomposition()'s own aggregate semantics above (it excludes null
        # rows from the reconstruction-error check entirely, never counts one as a failure).
        if priority_score is None:
            contribution_exact = True
        else:
            contrib_sum = (
                (row_a["contribution_bp2"] or 0.0)
                + (row_a["contribution_bp3"] or 0.0)
                + (row_a["contribution_bp4"] or 0.0)
            )
            contribution_exact = abs(contrib_sum - priority_score) < 1e-6

        recommended_action = row_a["recommended_action"]
        action_is_known = recommended_action in KNOWN_RECOMMENDED_ACTIONS
        if priority_score is None:
            action_consistent = recommended_action == "UNSCORED_MISSING_UPSTREAM_INPUT"
        elif intervention_flag:
            action_consistent = recommended_action in (
                "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
                "ESCALATE_SENIOR_REVIEWER",
                "PRIORITY_QUEUE_REVIEW",
            )
        else:
            action_consistent = recommended_action == "STANDARD_QUEUE"

        row_checks.append(
            SelfTestRowCheck(
                complaint_id=row_a["Complaint ID"],
                contribution_reconstruction_exact=contribution_exact,
                intervention_flag_matches_threshold_rule=intervention_matches_rule,
                recommended_action_structurally_consistent=action_is_known and action_consistent,
                dual_read_identical=dual_read_identical,
            )
        )

    all_checks_passed = decomposition_summary["reconstruction_exact_within_tolerance"] and all(
        (
            rc.contribution_reconstruction_exact
            and rc.intervention_flag_matches_threshold_rule
            and rc.recommended_action_structurally_consistent
            and rc.dual_read_identical
        )
        for rc in row_checks
    )

    return SelfTestResponse(
        all_checks_passed=all_checks_passed,
        sample_size_requested=sample_size,
        n_rows_checked=sample_a.height,
        contribution_decomposition_summary=decomposition_summary,
        row_checks=row_checks,
    )


def _record_self_test_metrics(result: "SelfTestResponse") -> None:
    """Records a real self-test outcome (client-triggered or background-refreshed) into the live
    self-test gauges - see module docstring."""
    SELF_TEST_LAST_RESULT.set(1.0 if result.all_checks_passed else 0.0)
    SELF_TEST_LAST_RUN_TIMESTAMP.set(time.time())


def _self_test_metrics_interval_seconds() -> float:
    """Read live (not cached at import time) so tests can monkeypatch the env var, matching
    `_rate_limit_per_minute()`'s own established pattern above. A value <= 0 disables the periodic
    background refresh entirely - the gauges are then only ever updated by real client calls to
    GET /decide/self-test."""
    raw = os.environ.get(SELF_TEST_METRICS_INTERVAL_ENV_VAR)
    if raw is None:
        return DEFAULT_SELF_TEST_METRICS_INTERVAL_SECONDS
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_SELF_TEST_METRICS_INTERVAL_SECONDS


_self_test_background_task: Optional[asyncio.Task] = None


async def _self_test_metrics_refresh_loop(interval_seconds: float) -> None:
    """Periodically re-runs the REAL `_compute_self_test()` - the identical real computation GET
    /decide/self-test performs, reused rather than reimplemented - and records its result into the
    live self-test gauges. This is the one genuinely live governance signal this static-lookup
    service can honestly expose (see module docstring): it never invents a drift statistic BP7 has
    no live inference to compute. If the real computation raises for any reason (Gate 5 artifacts
    not loaded, a transient read error, etc.) this cycle is simply skipped and the gauges keep
    their last real value - it never crashes the service and never fabricates a passing result,
    matching `DecisionEngineHandle._load()`'s own established "never raise past this point"
    precedent elsewhere in this file."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            handle = _get_handle()
            result = _compute_self_test(handle, DEFAULT_SELF_TEST_SAMPLE_SIZE)
            _record_self_test_metrics(result)
        except Exception:  # noqa: BLE001 - best-effort periodic refresh, never crashes the process
            continue  # nosec B112 - intentional: skip this cycle, loop keeps running


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle, _self_test_background_task
    project_root = resolve_project_root()
    _handle = DecisionEngineHandle(
        _default_records_csv_path(project_root), _default_summary_json_path(project_root)
    )
    _update_static_gauges(_handle)
    SERVICE_UPTIME_SECONDS.set_function(lambda: time.monotonic() - _SERVICE_STARTED_AT_MONOTONIC)

    interval = _self_test_metrics_interval_seconds()
    if interval > 0:
        _self_test_background_task = asyncio.create_task(_self_test_metrics_refresh_loop(interval))
    try:
        yield
    finally:
        if _self_test_background_task is not None:
            _self_test_background_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await _self_test_background_task
            _self_test_background_task = None


app = FastAPI(
    title="Customer360 Navigator - BP7 Customer Navigator Decision Engine",
    description=(
        "Read-only lookup service over BP7's real, persisted, full-population priority-decision "
        "records (Gate 5's own deterministic weighted-rule output) - never a live model/API call, "
        "never a prediction, never a fabricated result."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Production-hardening infrastructure (2026-09-26): request-ID + latency middleware, an in-memory
# request-metrics collector, and an in-memory per-key/per-IP rate limiter. All state below is
# module-level and per-process by design (see module docstring's disclosure) - it resets whenever
# this module is (re)imported, which is also what gives every test in
# tests/services/test_bp7_decision_engine_service.py a clean slate per test (that suite's own
# `service_module` fixture reloads this module before each test).
# ---------------------------------------------------------------------------

_SERVICE_STARTED_AT_MONOTONIC = time.monotonic()
_SERVICE_STARTED_AT_UTC = datetime.now(timezone.utc).isoformat()

_METRICS_LOCK = threading.Lock()
_METRICS_STATE: dict[str, Any] = {
    "total_requests": 0,
    "requests_by_route": {},
    "responses_by_status_class": {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0},
    "total_latency_ms": 0.0,
}


def _record_request_metric(route_template: str, status_code: int, latency_ms: float) -> None:
    status_class = f"{status_code // 100}xx"
    with _METRICS_LOCK:
        _METRICS_STATE["total_requests"] += 1
        _METRICS_STATE["requests_by_route"][route_template] = (
            _METRICS_STATE["requests_by_route"].get(route_template, 0) + 1
        )
        _METRICS_STATE["responses_by_status_class"][status_class] = (
            _METRICS_STATE["responses_by_status_class"].get(status_class, 0) + 1
        )
        _METRICS_STATE["total_latency_ms"] += latency_ms


def _rate_limit_per_minute() -> int:
    """Read live (not cached at import time) so tests can monkeypatch the env var; a value <= 0
    disables the limiter entirely."""
    raw = os.environ.get(RATE_LIMIT_PER_MINUTE_ENV_VAR)
    if raw is None:
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_RATE_LIMIT_PER_MINUTE


_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_STATE: dict[str, tuple[int, int]] = {}


def _rate_limit_key(request: Request) -> str:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def _check_rate_limit(request: Request) -> Optional[int]:
    """Returns None if the request is allowed, else the number of whole seconds to wait before
    retrying. Fixed-window (per real wall-clock minute), in-memory, per-process only - see module
    docstring's disclosure."""
    limit = _rate_limit_per_minute()
    if limit <= 0:
        return None
    if request.url.path in _RATE_LIMIT_EXEMPT_PATHS:
        return None
    key = _rate_limit_key(request)
    now = time.time()
    current_window = int(now // 60)
    with _RATE_LIMIT_LOCK:
        window_start, count = _RATE_LIMIT_STATE.get(key, (current_window, 0))
        if window_start != current_window:
            window_start, count = current_window, 0
        count += 1
        _RATE_LIMIT_STATE[key] = (window_start, count)
        if count > limit:
            return max(1, 60 - int(now % 60))
    return None


_ERROR_CODE_BY_STATUS = {
    401: "UNAUTHORIZED",
    404: "NOT_FOUND",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


def _request_id_of(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if existing:
        return existing
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Assigns/propagates a request ID, enforces the in-memory rate limit, times the request, and
    records it in the in-memory metrics counters. Runs for every route on both the bare and `/v1`
    mount (this is app-level middleware, applied once regardless of how many routers are
    mounted)."""
    request_id = _request_id_of(request)
    request.state.request_id = request_id
    start = time.perf_counter()

    retry_after = _check_rate_limit(request)
    if retry_after is not None:
        latency_ms = (time.perf_counter() - start) * 1000
        payload = {
            "detail": "Rate limit exceeded.",
            "error_code": "RATE_LIMITED",
            "status_code": 429,
            "request_id": request_id,
            "retry_after_seconds": retry_after,
            "disclosure": (
                f"In-memory, per-process rate limit ({_rate_limit_per_minute()} requests/minute, "
                f"keyed by {RATE_LIMIT_PER_MINUTE_ENV_VAR.lower()} API key or client IP) - resets "
                f"on process restart, never shared across instances. Set {RATE_LIMIT_PER_MINUTE_ENV_VAR} "
                "to change it, or 0 to disable."
            ),
        }
        response = JSONResponse(status_code=429, content=payload)
        response.headers["X-Request-ID"] = request_id
        response.headers["Retry-After"] = str(retry_after)
        _record_request_metric(request.url.path, 429, latency_ms)
        HTTP_REQUESTS_TOTAL.labels(method=request.method, route=request.url.path, status_code="429").inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, route=request.url.path).observe(
            latency_ms / 1000.0
        )
        return response

    response = await call_next(request)
    latency_ms = (time.perf_counter() - start) * 1000

    route = request.scope.get("route")
    route_template = route.path if route is not None else request.url.path
    _record_request_metric(route_template, response.status_code, latency_ms)
    HTTP_REQUESTS_TOTAL.labels(
        method=request.method, route=route_template, status_code=str(response.status_code)
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, route=route_template).observe(
        latency_ms / 1000.0
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{latency_ms:.2f}"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler_with_envelope(request: Request, exc: HTTPException) -> JSONResponse:
    """Consistent JSON error envelope for every HTTPException raised anywhere in this service -
    keeps the existing `detail` key (every pre-hardening test in
    tests/services/test_bp7_decision_engine_service.py only asserts on status codes, never on body
    shape, so this is purely additive) and adds `error_code`/`status_code`/`request_id`."""
    request_id = _request_id_of(request)
    payload = {
        "detail": exc.detail,
        "error_code": _ERROR_CODE_BY_STATUS.get(exc.status_code, "ERROR"),
        "status_code": exc.status_code,
        "request_id": request_id,
    }
    headers = dict(exc.headers or {})
    headers["X-Request-ID"] = request_id
    return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler_with_envelope(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Same consistent envelope for FastAPI/pydantic request-validation failures (e.g. a
    non-integer `complaint_id`, a `sample_size` outside its real bounds, or a `/score` batch over
    `MAX_BATCH_LOOKUP_SIZE`) - still a 422, still carrying the real validation detail, never
    silently swallowed."""
    request_id = _request_id_of(request)
    payload = {
        "detail": jsonable_encoder(exc.errors()),
        "error_code": "VALIDATION_ERROR",
        "status_code": 422,
        "request_id": request_id,
    }
    return JSONResponse(status_code=422, content=payload, headers={"X-Request-ID": request_id})


@app.exception_handler(Exception)
async def unhandled_exception_handler_with_envelope(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort safety net so a genuinely unexpected error (e.g. a corrupted CSV row) still
    returns the same consistent envelope with a real request ID to correlate against server logs,
    rather than an unstructured 500 or a raw traceback leaking to the caller. This never masks the
    real exception from server-side logs - only the HTTP response body is templated."""
    request_id = _request_id_of(request)
    payload = {
        "detail": "Internal server error.",
        "error_code": "INTERNAL_ERROR",
        "status_code": 500,
        "request_id": request_id,
    }
    return JSONResponse(status_code=500, content=payload, headers={"X-Request-ID": request_id})


def _resolve_git_commit() -> Optional[str]:
    """Best-effort, never-fabricated short git commit SHA for `GET /version`. Prefers an explicit
    `C360_GIT_COMMIT` env var (set this at build/deploy time - e.g. a Render environment variable
    or a Docker build-arg baked in at image-build time - since a built container image never
    contains a `.git` directory: this service's own Dockerfile COPYs only
    PROJECT_STRUCTURE_LOCKED.md and src/, never .git/). Falls back to a real local
    `git rev-parse --short HEAD` ONLY when a `.git` directory is actually present (e.g. running
    this service directly from a checkout rather than the built image) - returns None rather than
    inventing a hash when neither is available."""
    env_commit = os.environ.get(GIT_COMMIT_ENV_VAR)
    if env_commit:
        return env_commit
    try:
        project_root = resolve_project_root()
    except RuntimeError:
        return None
    if not (project_root / ".git").exists():
        return None
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell, no user input
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        commit = result.stdout.strip()
        return commit or None
    except Exception:  # noqa: BLE001 - best-effort only, never raises past this helper
        return None


class DecisionEngineHealthResponse(BaseModel):
    status: str = Field(description="'ok' if the real Gate 5 artifacts loaded, else 'not_configured'.")
    bp_id: str
    live_row_count: Optional[int] = None
    champion_rule_scheme: Optional[str] = None
    champion_weights_normalized: Optional[dict[str, float]] = None
    intervention_threshold: Optional[float] = None
    records_csv_path: Optional[str] = None
    records_csv_columns: Optional[list[str]] = None
    generated_at_utc: Optional[str] = None
    error: Optional[str] = None


class DecisionRecord(BaseModel):
    complaint_id: int
    priority_score: Optional[float] = None
    intervention_flag: bool
    recommended_action: str
    reason_codes: str
    contribution_bp2: Optional[float] = None
    contribution_bp3: Optional[float] = None
    contribution_bp4: Optional[float] = None
    bp2_predicted_label: Optional[str] = None
    bp2_confidence: Optional[float] = None
    bp3_predicted_label: Optional[str] = None
    bp3_probability_positive_class: Optional[float] = None
    bp4_review_priority_tier: Optional[str] = None
    bp4_review_priority_score: Optional[int] = None
    bp4_join_status: Optional[str] = None
    bp1_context_status: Optional[str] = None
    bp5_outcome_1_context: Optional[str] = None
    bp5_outcome_2_context: Optional[str] = None
    tags_group: Optional[str] = None


class SelfTestRowCheck(BaseModel):
    complaint_id: int
    contribution_reconstruction_exact: bool
    intervention_flag_matches_threshold_rule: bool
    recommended_action_structurally_consistent: bool
    dual_read_identical: bool


class SelfTestResponse(BaseModel):
    all_checks_passed: bool = Field(
        description=(
            "True iff every real, sampled row passed all four internal-consistency checks below. "
            "See the module docstring for why this - not a live re-derivation via score_priority_rule "
            "- is the honest proof BP7's no-external-API self-test can make."
        )
    )
    sample_size_requested: int
    n_rows_checked: int
    contribution_decomposition_summary: dict[str, Any]
    row_checks: list[SelfTestRowCheck]
    real_external_api_call_made: bool = False


class VersionResponse(BaseModel):
    service: str = "bp7_customer_navigator_decision_engine"
    app_version: str
    api_versions_supported: list[str] = Field(default_factory=lambda: list(API_VERSIONS_SUPPORTED))
    git_commit: Optional[str] = None
    dataset_and_model_version_proxy: dict[str, Any]
    started_at_utc: str
    note: str = (
        "This project has no semantic version tags for its dataset/decision-layer artifacts (the "
        "same disclosure appears on index.html's own Dataset & Model Provenance panel) - "
        "champion_rule_scheme + generated_at_utc from the real Gate 5 summary is the honest "
        "version proxy used here instead of a fabricated version number."
    )


class ModelInfoResponse(BaseModel):
    status: str
    bp_id: str
    decision_type: str = "deterministic_weighted_rule_lookup"
    champion_rule_scheme: Optional[str] = None
    champion_weights_normalized: Optional[dict[str, float]] = None
    intervention_threshold: Optional[float] = None
    live_row_count: Optional[int] = None
    generated_at_utc: Optional[str] = None
    upstream_inputs: list[str] = Field(default_factory=lambda: ["bp2", "bp3", "bp4"])
    disparate_impact_audit: Optional[dict[str, Any]] = None
    weight_rederivation_cross_check: Optional[dict[str, Any]] = None
    records_csv_path: Optional[str] = None
    error: Optional[str] = None
    disclosure: str = (
        "BP7 performs no live model inference and loads no model bundle. This describes the real, "
        "persisted Gate 5 decision-layer artifact this service serves lookups over (contrast "
        "BP1-3's /health, which reports a runtime-loaded joblib bundle)."
    )


class MetricsResponse(BaseModel):
    status: str = "ok"
    bp_id: str = BP_ID
    uptime_seconds: float
    started_at_utc: str
    total_requests: int
    requests_by_route: dict[str, int]
    responses_by_status_class: dict[str, int]
    average_latency_ms: Optional[float] = None
    rate_limit_per_minute: int
    disclosure: str = (
        "In-memory counters for this single process only - reset on restart, never aggregated "
        "across instances (this service is deployed as one process; see RENDER_DEPLOYMENT.md). "
        "No external metrics backend (e.g. Prometheus) is wired up - this is a lightweight "
        "built-in endpoint, not a claim of production-grade distributed observability."
    )


class BatchLookupRequest(BaseModel):
    complaint_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=MAX_BATCH_LOOKUP_SIZE,
        description=(
            "Real, unique CFPB 'Complaint ID' values to look up in one call - batch form of "
            f"GET /decide/{{complaint_id}}. Bounded to {MAX_BATCH_LOOKUP_SIZE} ids per call."
        ),
    )


class ScoreResultItem(BaseModel):
    complaint_id: int
    found: bool
    priority_score: Optional[float] = None
    contribution_bp2: Optional[float] = None
    contribution_bp3: Optional[float] = None
    contribution_bp4: Optional[float] = None


class ScoreResponse(BaseModel):
    results: list[ScoreResultItem]
    note: str = (
        "priority_score/contribution_* are BP7's real, pre-computed Gate 5 weighted-rule output "
        "(champion_rule_scheme) - not a live model inference. See GET /model-info."
    )


class DecisionResultItem(BaseModel):
    complaint_id: int
    found: bool
    intervention_flag: Optional[bool] = None
    recommended_action: Optional[str] = None
    reason_codes: Optional[str] = None


class DecisionResponse(BaseModel):
    results: list[DecisionResultItem]
    note: str = (
        "intervention_flag/recommended_action/reason_codes are BP7's real, pre-computed Gate 5 "
        "decision-layer output - not a live re-scoring. See GET /model-info."
    )


def _row_to_record(row: dict[str, Any]) -> DecisionRecord:
    return DecisionRecord(
        complaint_id=row["Complaint ID"],
        priority_score=row.get("priority_score"),
        intervention_flag=bool(row["intervention_flag"]),
        recommended_action=row["recommended_action"],
        reason_codes=row["reason_codes"],
        contribution_bp2=row.get("contribution_bp2"),
        contribution_bp3=row.get("contribution_bp3"),
        contribution_bp4=row.get("contribution_bp4"),
        bp2_predicted_label=row.get("bp2_predicted_label"),
        bp2_confidence=row.get("bp2_confidence"),
        # Real Gate 5 CSV stores bp3_predicted_label as BP3's real int64 binary label (0/1),
        # not a string like BP2's categorical friction tier - cast explicitly so the API's
        # documented `Optional[str]` contract (matching bp2_predicted_label's shape) holds for
        # both upstream fields, rather than letting pydantic reject the real int value outright.
        bp3_predicted_label=(
            str(row["bp3_predicted_label"]) if row.get("bp3_predicted_label") is not None else None
        ),
        bp3_probability_positive_class=row.get("bp3_probability_positive_class"),
        bp4_review_priority_tier=row.get("bp4_review_priority_tier"),
        bp4_review_priority_score=row.get("bp4_review_priority_score"),
        bp4_join_status=row.get("bp4_join_status"),
        bp1_context_status=row.get("bp1_context_status"),
        bp5_outcome_1_context=row.get("bp5_outcome_1_context"),
        bp5_outcome_2_context=row.get("bp5_outcome_2_context"),
        tags_group=row.get("tags_group"),
    )


def _fetch_complaint_row(handle: DecisionEngineHandle, complaint_id: int) -> Optional[dict[str, Any]]:
    """One real, per-request lazy-scan point lookup against the real Gate 5 CSV - never an eager
    full-file load (see module docstring)."""
    match = pl.scan_csv(handle.records_csv_path).filter(pl.col("Complaint ID") == complaint_id).collect()
    if match.height == 0:
        return None
    return match.row(0, named=True)


def _fetch_complaint_rows_batch(
    handle: DecisionEngineHandle, complaint_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """Batch form of `_fetch_complaint_row`, used by `/score` and `/decision`: ONE real lazy-scan
    filtered with `Complaint ID.is_in(complaint_ids)` rather than one scan per id - real, on-disk
    values only, still never an eager full-file load of the ~540MB/1,048,575-row CSV."""
    if not complaint_ids:
        return {}
    matches = (
        pl.scan_csv(handle.records_csv_path).filter(pl.col("Complaint ID").is_in(complaint_ids)).collect()
    )
    return {row["Complaint ID"]: row for row in matches.iter_rows(named=True)}


@app.get("/", tags=["meta"])
@app.get("/v1/", tags=["meta"], include_in_schema=False)
def root():
    return {
        "service": "bp7_customer_navigator_decision_engine",
        "docs": "/docs",
        "health": "/health",
        "version": "/version",
        "model_info": "/model-info",
        "metrics": "/metrics",
        "metrics_prometheus": "/metrics/prometheus",
        "decide": "/decide/{complaint_id}",
        "self_test": "/decide/self-test",
        "score": "/score",
        "decision": "/decision",
        "api_versions_supported": list(API_VERSIONS_SUPPORTED),
        "versioned_base_path": "/v1",
        "note": (
            "Read-only lookup service over BP7's real, persisted, full-population priority-decision "
            "records - not a live model/API inference endpoint. BP7 makes no external network call "
            "anywhere, unlike BP6."
        ),
    }


@app.get("/health", response_model=DecisionEngineHealthResponse, tags=["meta"])
@app.get(
    "/v1/health",
    response_model=DecisionEngineHealthResponse,
    tags=["meta"],
    include_in_schema=False,
)
def health():
    handle = _get_handle()
    if not handle.is_loaded:
        return DecisionEngineHealthResponse(status="not_configured", bp_id=BP_ID, error=handle.error)
    summary = handle.summary or {}
    return DecisionEngineHealthResponse(
        status="ok",
        bp_id=BP_ID,
        live_row_count=summary.get("live_row_count"),
        champion_rule_scheme=summary.get("champion_rule_scheme"),
        champion_weights_normalized=summary.get("champion_weights_normalized"),
        intervention_threshold=summary.get("intervention_threshold"),
        records_csv_path=str(handle.records_csv_path),
        records_csv_columns=handle.schema_columns,
        generated_at_utc=summary.get("generated_at_utc"),
    )


@app.get("/version", response_model=VersionResponse, tags=["meta"])
@app.get(
    "/v1/version",
    response_model=VersionResponse,
    tags=["meta"],
    include_in_schema=False,
)
def version():
    """Public (no API key), matching /health's precedent - orchestrators, load balancers, and
    uptime/version-drift monitors need this with no secret. Never fabricates a git commit or a
    semantic version this project doesn't really have - see `_resolve_git_commit()`."""
    handle = _get_handle()
    summary = (handle.summary or {}) if handle.is_loaded else {}
    return VersionResponse(
        app_version=app.version,
        git_commit=_resolve_git_commit(),
        dataset_and_model_version_proxy={
            "champion_rule_scheme": summary.get("champion_rule_scheme"),
            "generated_at_utc": summary.get("generated_at_utc"),
            "live_row_count": summary.get("live_row_count"),
            "gate5_artifacts_loaded": handle.is_loaded,
        },
        started_at_utc=_SERVICE_STARTED_AT_UTC,
    )


@app.get(
    "/model-info",
    response_model=ModelInfoResponse,
    tags=["meta", "governance"],
    dependencies=[Depends(require_api_key)],
)
@app.get(
    "/v1/model-info",
    response_model=ModelInfoResponse,
    tags=["meta", "governance"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def model_info():
    handle = _get_handle()
    if not handle.is_loaded:
        return ModelInfoResponse(status="not_configured", bp_id=BP_ID, error=handle.error)
    summary = handle.summary or {}
    return ModelInfoResponse(
        status="ok",
        bp_id=BP_ID,
        champion_rule_scheme=summary.get("champion_rule_scheme"),
        champion_weights_normalized=summary.get("champion_weights_normalized"),
        intervention_threshold=summary.get("intervention_threshold"),
        live_row_count=summary.get("live_row_count"),
        generated_at_utc=summary.get("generated_at_utc"),
        disparate_impact_audit=summary.get("disparate_impact_audit"),
        weight_rederivation_cross_check=summary.get("weight_rederivation_cross_check"),
        records_csv_path=str(handle.records_csv_path),
    )


@app.get(
    "/metrics",
    response_model=MetricsResponse,
    tags=["meta", "governance"],
    dependencies=[Depends(require_api_key)],
)
@app.get(
    "/v1/metrics",
    response_model=MetricsResponse,
    tags=["meta", "governance"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def metrics():
    with _METRICS_LOCK:
        total = _METRICS_STATE["total_requests"]
        total_latency_ms = _METRICS_STATE["total_latency_ms"]
        requests_by_route = dict(_METRICS_STATE["requests_by_route"])
        responses_by_status_class = dict(_METRICS_STATE["responses_by_status_class"])
    average_latency_ms = (total_latency_ms / total) if total else None
    return MetricsResponse(
        uptime_seconds=round(time.monotonic() - _SERVICE_STARTED_AT_MONOTONIC, 3),
        started_at_utc=_SERVICE_STARTED_AT_UTC,
        total_requests=total,
        requests_by_route=requests_by_route,
        responses_by_status_class=responses_by_status_class,
        average_latency_ms=(round(average_latency_ms, 3) if average_latency_ms is not None else None),
        rate_limit_per_minute=_rate_limit_per_minute(),
    )


@app.get(
    "/metrics/prometheus",
    tags=["meta", "governance"],
    dependencies=[Depends(require_api_key)],
)
@app.get(
    "/v1/metrics/prometheus",
    tags=["meta", "governance"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def metrics_prometheus():
    """Real Prometheus exposition-format metrics for this BP7 instance (2026-09-26 Priority 3
    addition - see the module docstring for the full disclosure on which series are live-per-
    request vs. static-Gate-5-artifact-refreshed-per-restart, and `MONITORING.md` for how to point
    a real Prometheus scrape config at this endpoint). Auth-protected via the same X-API-Key
    dependency, and subject to the same rate limiter, as `GET /metrics` above - a deliberate
    consistency choice (every governance endpoint in this service needs the key; see
    `MONITORING.md` for how to configure a scrape config's `http_headers` to send it, since
    Prometheus's native `authorization:` block only supports `Authorization: Bearer` tokens, never
    an arbitrary header name like `X-API-Key`)."""
    handle = _get_handle()
    _update_static_gauges(handle)
    return Response(content=generate_latest(PROM_REGISTRY), media_type=CONTENT_TYPE_LATEST)


@app.get(
    "/decide/self-test",
    response_model=SelfTestResponse,
    tags=["query", "governance"],
    dependencies=[Depends(require_api_key)],
)
@app.get(
    "/v1/decide/self-test",
    response_model=SelfTestResponse,
    tags=["query", "governance"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def decide_self_test(
    sample_size: int = Query(
        DEFAULT_SELF_TEST_SAMPLE_SIZE,
        ge=1,
        le=MAX_SELF_TEST_SAMPLE_SIZE,
        description="Number of real, already-scored rows to internal-consistency-check.",
    )
):
    """Master Plan paragraph 205's required BP6/BP7 Gate 6 deliverable, adapted for BP7's
    no-external-API nature (see module docstring for the full rationale): a REAL internal-
    consistency check over `sample_size` real rows read from the real, persisted Gate 5 CSV -
    never a mock, never a fabricated pass. Makes ZERO external network calls (BP7 makes none
    anywhere) - the honest analogue here is proving this service's own read/serve path introduces
    no drift versus the real artifact on disk, and that every served row is internally consistent
    with its own real, already-computed fields.

    2026-09-26 Priority 3 refactor: the actual computation now lives in the shared
    `_compute_self_test()` helper (defined above `lifespan`) so the optional periodic background
    metrics-refresh task can call the identical real logic - this route is now a thin wrapper that
    converts that helper's plain exceptions to the same real 503s it always returned, and records
    the real outcome into the live `bp7_self_test_last_result`/`bp7_self_test_last_run_timestamp_
    seconds` Prometheus gauges (see `GET /metrics/prometheus`)."""
    handle = _get_handle()
    try:
        result = _compute_self_test(handle, sample_size)
    except SelfTestNotConfiguredError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except SelfTestEmptyArtifactError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    _record_self_test_metrics(result)
    return result


@app.get(
    "/decide/{complaint_id}",
    response_model=DecisionRecord,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
)
@app.get(
    "/v1/decide/{complaint_id}",
    response_model=DecisionRecord,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def decide(complaint_id: int = PathParam(..., description="Real, unique CFPB 'Complaint ID'.")):
    """Real, read-only point lookup of one real complaint's already-computed
    priority_score/intervention_flag/recommended_action/reason_codes (Gate 5's own real,
    full-population output) - never a live re-score, never a fabricated result for an unknown ID.
    Registered AFTER `/decide/self-test` above so that literal path is matched first (Starlette/
    FastAPI route matching is order-dependent - a `/decide/{complaint_id}` route registered first
    would otherwise swallow `/decide/self-test` by parsing "self-test" as an int and 422'ing)."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP7 decision engine is not configured: {handle.error}")
    row = _fetch_complaint_row(handle, complaint_id)
    if row is None:
        LOOKUP_VOLUME_TOTAL.labels(endpoint="decide", found="false").inc()
        raise HTTPException(
            status_code=404, detail=f"No real decision record for Complaint ID {complaint_id}."
        )
    LOOKUP_VOLUME_TOTAL.labels(endpoint="decide", found="true").inc()
    record = _row_to_record(row)
    RECOMMENDED_ACTION_SERVED_TOTAL.labels(recommended_action=record.recommended_action).inc()
    return record


@app.post(
    "/score",
    response_model=ScoreResponse,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
)
@app.post(
    "/v1/score",
    response_model=ScoreResponse,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def score(request: BatchLookupRequest):
    """Batch form of `GET /decide/{complaint_id}`, projected to the real 'score' fields
    (priority_score + its contribution_bp2/3/4 decomposition) - see module docstring for why this
    is a real-field projection over the identical real lookup, never a new inference. An id not
    found in the real Gate 5 CSV is reported as `found: false`, never a fabricated score."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP7 decision engine is not configured: {handle.error}")
    rows_by_id = _fetch_complaint_rows_batch(handle, request.complaint_ids)
    results = []
    for complaint_id in request.complaint_ids:
        row = rows_by_id.get(complaint_id)
        if row is None:
            LOOKUP_VOLUME_TOTAL.labels(endpoint="score", found="false").inc()
            results.append(ScoreResultItem(complaint_id=complaint_id, found=False))
        else:
            LOOKUP_VOLUME_TOTAL.labels(endpoint="score", found="true").inc()
            results.append(
                ScoreResultItem(
                    complaint_id=complaint_id,
                    found=True,
                    priority_score=row.get("priority_score"),
                    contribution_bp2=row.get("contribution_bp2"),
                    contribution_bp3=row.get("contribution_bp3"),
                    contribution_bp4=row.get("contribution_bp4"),
                )
            )
    return ScoreResponse(results=results)


@app.post(
    "/decision",
    response_model=DecisionResponse,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
)
@app.post(
    "/v1/decision",
    response_model=DecisionResponse,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def decision(request: BatchLookupRequest):
    """Batch form of `GET /decide/{complaint_id}`, projected to the real 'decision' fields
    (intervention_flag, recommended_action, reason_codes) - see module docstring for why this is a
    real-field projection over the identical real lookup, never a new inference. An id not found in
    the real Gate 5 CSV is reported as `found: false`, never a fabricated decision."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP7 decision engine is not configured: {handle.error}")
    rows_by_id = _fetch_complaint_rows_batch(handle, request.complaint_ids)
    results = []
    for complaint_id in request.complaint_ids:
        row = rows_by_id.get(complaint_id)
        if row is None:
            LOOKUP_VOLUME_TOTAL.labels(endpoint="decision", found="false").inc()
            results.append(DecisionResultItem(complaint_id=complaint_id, found=False))
        else:
            LOOKUP_VOLUME_TOTAL.labels(endpoint="decision", found="true").inc()
            RECOMMENDED_ACTION_SERVED_TOTAL.labels(recommended_action=row["recommended_action"]).inc()
            results.append(
                DecisionResultItem(
                    complaint_id=complaint_id,
                    found=True,
                    intervention_flag=bool(row["intervention_flag"]),
                    recommended_action=row["recommended_action"],
                    reason_codes=row["reason_codes"],
                )
            )
    return DecisionResponse(results=results)
