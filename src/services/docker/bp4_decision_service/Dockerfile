# Customer360 Navigator - BP4 Customer Journey Analytics decision-records lookup/query service
# Hardening Step 5 (Docker packaging), BP4 variant. Mirrors bp1/bp2/bp3_inference_service's own
# Dockerfiles' structure (python:3.11-slim base, non-root c360service user, project-root build
# context, HEALTHCHECK against /health) - see bp1's Dockerfile header for the shared build-
# context rationale (not repeated here).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp4_decision_service/Dockerfile -t c360-bp4-service .
#
# BP4 IS ARCHITECTURALLY DIFFERENT FROM BP1/BP2/BP3: it fits no supervised model (an explicit
# standing user decision - see
# notebooks/bp4_customer_journey_analytics/bp4_customer_journey_analytics_decision_artifact_persistence.ipynb's
# own module docstring). This image therefore does NOT COPY a joblib model bundle - it COPYs the
# real, persisted Parquet decision-artifact INDEX
# (models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet) plus its metadata
# sidecar (bp4_decision_artifact_metadata.json) instead, and serves read-only lookup/query
# endpoints over it, never a prediction.
#
# REQUIRES the Hardening Step 2 persistence notebook (linked above) to have been run FOR REAL
# FIRST - as of this Dockerfile being written (2026-09-24), it has NOT: no real
# bp4_decision_artifact_index.parquet exists yet on the real device
# (models/bp4_customer_journey_analytics/ contains only a .gitkeep placeholder, live-verified).
# The COPY step below will fail loudly (file not found) until the user runs that notebook for
# real - the same honesty pattern as bp1/bp2/bp3's own Dockerfiles ("COPYs your own real
# ...bundle.joblib, never a Claude-generated one"), adapted here to a Parquet artifact instead of
# a joblib bundle. This is expected and correct: no placeholder artifact is baked into this image
# to make the build silently "succeed" against a fabricated substitute.
#
# MINIMAL REAL RUNTIME DEPENDENCY LIST - grep-verified (2026-09-24) against
# src/services/bp4_decision_service.py's own module-level import statements:
#   `import os`, `from contextlib import asynccontextmanager`, `from pathlib import Path`,
#   `from typing import Any, Optional`                              -> stdlib only, no install
#   `import polars as pl`                                            -> polars
#   `from fastapi import FastAPI, HTTPException, Query`              -> fastapi
#   `from pydantic import BaseModel, Field`                          -> pydantic
# `grep -n "^import\|^from" src/services/bp4_decision_service.py` (live-run against this real
# file) shows NO pandas, NO pyarrow, NO joblib, NO scikit-learn, NO xgboost/catboost/lightgbm, and
# NO PyYAML import anywhere in this service module - unlike bp1/bp2/bp3_inference_service.py
# (which all import a joblib model bundle, and bp3's which additionally pulls in polars+PyYAML
# transitively through src/features/bp3_escalation_features.py and src/taxonomy/taxonomy_mapper.py).
# bp4_decision_service.py imports neither of those feature/taxonomy modules at all - its own
# CLUSTER_KEY/route logic is fully self-contained (see its own module docstring: "does NOT import
# src/services/service_common.py ... Project-root resolution is reimplemented here"). polars' own
# native Parquet reader (pl.read_parquet) needs no separate pyarrow install - confirmed by the
# Hardening Step 2 notebook itself, which writes the artifact via `indexed_frame.write_parquet(...)`
# (a native polars call, not a pandas/pyarrow one) and this service reads it back the same way.
# `uvicorn` is added below (same as bp1/2/3's own Dockerfiles) purely as the ASGI server this
# image's CMD invokes from the command line - bp4_decision_service.py itself never imports it.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - BP4 Customer Journey Analytics (Decision Records)"
LABEL org.opencontainers.image.description="Read-only lookup/query service over BP4's real, persisted per-issue-cluster review-priority decision/reporting records - not an ML inference service (BP4 fits no model)."

WORKDIR /app

RUN useradd --no-create-home --uid 1000 c360service

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "pydantic>=2.0" \
        "uvicorn>=0.30" \
        "polars>=1.9"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/ ./src/
COPY --chown=c360service:c360service models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet \
     ./models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet
COPY --chown=c360service:c360service models/bp4_customer_journey_analytics/bp4_decision_artifact_metadata.json \
     ./models/bp4_customer_journey_analytics/bp4_decision_artifact_metadata.json

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER c360service

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8004/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp4_decision_service:app", "--host", "0.0.0.0", "--port", "8004"]
