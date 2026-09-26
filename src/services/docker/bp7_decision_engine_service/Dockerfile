# Customer360 Navigator - BP7 Customer Navigator Decision Engine FastAPI service
# Gate 6 (Productization, Monitoring & Governance) deliverable - Master Plan paragraph 205's
# mandatory BP6/BP7 "runnable FastAPI service" requirement (not an optional hardening extra, unlike
# BP1-4's own Docker packaging under Section 18.1). Mirrors bp1-6's own Dockerfiles' structure
# (python:3.11-slim base, non-root c360service user, project-root build context, HEALTHCHECK
# against /health) - see bp1's Dockerfile header for the shared build-context rationale (not
# repeated here).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp7_decision_engine_service/Dockerfile -t c360-bp7-decision-engine-service .
#
# BP7 IS ARCHITECTURALLY CLOSER TO BP4 THAN TO BP6: it fits no model and makes no external network
# call anywhere (contrast BP6's real, live Gemini call on every /resolve). This image COPYs the
# real, persisted, full-population decision-records CSV Gate 5 already wrote for real
# (gate5_full_population_decision_records.csv) plus its summary JSON, and serves read-only
# point-lookup/self-test endpoints over them - never a live re-score, never a fabricated result.
#
# REQUIRES BP7 Gate 5 to have been run for real first - the COPY step below fails loudly (file not
# found) until it has, the same honesty pattern as every other BP's own Dockerfile in this project.
#
# DISCLOSED SIZE NOTE (unlike BP4's compact ~few-MB Parquet index): BP7's real Gate 5 CSV is large
# (~540MB, 1,048,575 rows, one row per real CFPB complaint) - this image genuinely bakes that whole
# real artifact in, matching this project's own established "COPY the real persisted artifact"
# convention exactly (see BP4's Dockerfile header for the precedent), rather than deviating from it
# for size alone. This is a real, disclosed characteristic of this specific service image, not an
# error - operationally it means this image is meaningfully larger than BP1-6's own.
#
# MINIMAL REAL RUNTIME DEPENDENCY LIST - grep-verified (2026-09-24) against
# src/services/bp7_decision_engine_service.py's own module-level import statements: fastapi,
# pydantic, polars. UNLIKE BP4 (whose dependency list stops there), this image ALSO installs
# pandas/numpy/scipy/scikit-learn/joblib/PyYAML - not because bp7_decision_engine_service.py's own
# module-level imports need them (it grep-verified does not import any of them at module level),
# but because its `/decide/self-test` endpoint's own deferred import of
# `features.bp7_decision_engine_features` (Gate 4/5's own real
# `summarize_contribution_decomposition` reconciliation function, reused rather than reimplemented
# - see that module's own docstring for why) transitively imports the full shared BP2/BP3/BP4
# feature-module chain (features.bp3_escalation_features -> scikit-learn; models.model_persistence
# -> joblib/scipy; taxonomy.taxonomy_mapper -> PyYAML). This is a real, disclosed trade-off: honest
# reuse of Gate 5's own already-validated arithmetic over reimplementing it inline to keep this
# image's own dependency footprint as small as BP4's. `uvicorn` is added below purely as the ASGI
# server this image's CMD invokes - the service module itself never imports it.

# API-key auth added 2026-09-26 (src/services/service_auth.py, see SECURITY.md): this image's
# dependency list above is UNCHANGED - the new services.service_auth import needs only fastapi
# (already installed above), nothing new.

# Production-hardening addition (2026-09-26, see the service module's own docstring): API
# versioning (/v1 mirror), GET /version + /model-info + /metrics, POST /score + /decision,
# request-ID/latency headers, a consistent JSON error envelope, and an in-memory rate limiter.
# This image's dependency list above is STILL UNCHANGED - every addition uses only the Python
# standard library (uuid, time, threading, subprocess, datetime) plus fastapi/pydantic, already
# installed above. See RENDER_DEPLOYMENT.md at the repo root for how to deploy this image as a
# real public API on Render's free tier.

# AMENDED same day (2026-09-26, Priority 3 - "add real observability: Prometheus + Grafana"): the
# "STILL UNCHANGED" sentence directly above was true for the production-hardening pass it
# described - it is NO LONGER true as of this later, separate addition. `prometheus-client` is
# added to the pip install list below - the first genuinely NEW runtime dependency this image has
# ever needed (every earlier addition, including the one directly above, used only the standard
# library plus fastapi/pydantic already installed). It backs the new GET /metrics/prometheus
# endpoint (real Prometheus exposition-format metrics). See MONITORING.md at the repo root.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - BP7 Customer Navigator Decision Engine"
LABEL org.opencontainers.image.description="Read-only lookup service over BP7's real, persisted, full-population priority-decision records - never a live model/API call, never a prediction, never a fabricated result. Self-test performs a real internal-consistency check, makes zero external network calls."

WORKDIR /app

RUN useradd --no-create-home --uid 1000 c360service

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "pydantic>=2.0" \
        "uvicorn>=0.30" \
        "polars>=1.9" \
        "pandas>=2.2" \
        "numpy>=1.26" \
        "scipy>=1.13" \
        "scikit-learn>=1.5" \
        "joblib>=1.3" \
        "PyYAML>=6.0" \
        "prometheus-client>=0.20"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/ ./src/

# Real, static prerequisites this service reads at startup (schema-only) and at request time
# (never at build time) - Gate 5's own real, persisted full-population decision-records CSV and
# its summary JSON.
COPY --chown=c360service:c360service notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_full_population_decision_records.csv \
     ./notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_full_population_decision_records.csv
COPY --chown=c360service:c360service notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_decision_layer_summary.json \
     ./notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_decision_layer_summary.json

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER c360service

EXPOSE 8007

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8007/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp7_decision_engine_service:app", "--host", "0.0.0.0", "--port", "8007"]
