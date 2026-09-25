# Customer360 Navigator - BP5 Root-Cause & Driver Analytics reporting service
# Hardening pass, BP5 variant. Mirrors bp4_decision_service's and bp6_resolution_service's own
# Dockerfiles' structure (python:3.11-slim base, non-root c360service user, project-root build
# context, HEALTHCHECK against /health) - see bp1's Dockerfile header for the shared build-
# context rationale (not repeated here).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp5_driver_service/Dockerfile -t c360-bp5-driver-service .
#
# BP5 IS ARCHITECTURALLY DIFFERENT FROM BP1/BP2/BP3 (no supervised classifier is served) AND FROM
# BP4 (BP4 wraps a Parquet decision-artifact INDEX persisted to models/ by its own dedicated
# Hardening Step 2 persistence notebook; BP5 has NO such persistence notebook -
# models/bp5_root_cause_driver_analytics/ holds only a .gitkeep, live-verified 2026-09-24). This
# image therefore does NOT COPY a joblib bundle or a Parquet index - it COPYs BP5's real,
# statically-committed Gate 5 prioritized root-cause report JSON artifacts (one per real outcome)
# and the Gate 7 executive rollup manifest, the same "COPY the real committed
# notebooks/**/artifacts/ JSON directly" shape bp6_resolution_service's own Dockerfile already
# established. Unlike models/**/*.joblib (gitignored), notebooks/**/artifacts/ is NOT gitignored
# (see .gitignore) - these are real, already-committed evidence (BP5 Gates 5 and 7 are both
# real-run-confirmed complete), not artifacts this build step generates.
#
# BP5 makes no GenAI call (unlike BP6) and needs no runtime API key.
#
# MINIMAL REAL RUNTIME DEPENDENCY LIST - grep-verified (2026-09-24) against
# src/services/bp5_driver_service.py's own module-level import statements:
#   `import json`, `import os`, `from contextlib import asynccontextmanager`,
#   `from pathlib import Path`, `from typing import Any, Optional`   -> stdlib only, no install
#   `from fastapi import FastAPI, HTTPException`                     -> fastapi
#   `from pydantic import BaseModel, Field`                          -> pydantic
# No polars, no pandas, no pyarrow, no joblib, no scikit-learn, no google-genai anywhere in this
# service module - it reads plain JSON with the stdlib `json` module only. `uvicorn` is added below
# (same as every other BP's own Dockerfile) purely as the ASGI server this image's CMD invokes -
# bp5_driver_service.py itself never imports it.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - BP5 Root-Cause & Driver Analytics (Reporting)"
LABEL org.opencontainers.image.description="Read-only reporting service over BP5's real, committed Gate 5 prioritized root-cause reports and Gate 7 executive rollup manifest - not an ML inference service and not a GenAI service. Association only, never causal."

WORKDIR /app

RUN useradd --no-create-home --uid 1000 c360service

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "pydantic>=2.0" \
        "uvicorn>=0.30"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/ ./src/

# Real, static prerequisites this service reads at request time (never at build time) - BP5's own
# real Gate 5 prioritized root-cause reports (one per real outcome) and Gate 7 executive rollup.
COPY --chown=c360service:c360service notebooks/bp5_root_cause_driver_analytics/artifacts/gate5_prioritized_root_cause_report_outcome_1_intervention_required.json \
     ./notebooks/bp5_root_cause_driver_analytics/artifacts/gate5_prioritized_root_cause_report_outcome_1_intervention_required.json
COPY --chown=c360service:c360service notebooks/bp5_root_cause_driver_analytics/artifacts/gate5_prioritized_root_cause_report_outcome_2_timely_response_failure.json \
     ./notebooks/bp5_root_cause_driver_analytics/artifacts/gate5_prioritized_root_cause_report_outcome_2_timely_response_failure.json
COPY --chown=c360service:c360service notebooks/bp5_root_cause_driver_analytics/artifacts/executive_rollup_manifest.json \
     ./notebooks/bp5_root_cause_driver_analytics/artifacts/executive_rollup_manifest.json

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER c360service

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8005/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp5_driver_service:app", "--host", "0.0.0.0", "--port", "8005"]
