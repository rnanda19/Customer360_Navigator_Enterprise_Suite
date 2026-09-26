# Customer360 Navigator - BP6 GenAI Resolution Assistant FastAPI service
# Gate 6 (Productization, Monitoring & Governance) deliverable - Master Plan paragraph 205's
# mandatory BP6/BP7 "runnable FastAPI service" requirement (not an optional hardening extra, unlike
# BP1-4's own Docker packaging under Section 18.1). Mirrors bp1-4's own Dockerfiles' structure
# (python:3.11-slim base, non-root c360service user, project-root build context, HEALTHCHECK
# against /health) - see bp1's Dockerfile header for the shared build-context rationale (not
# repeated here).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp6_resolution_service/Dockerfile -t c360-bp6-resolution-service .
#
# BP6 IS ARCHITECTURALLY DIFFERENT FROM BP1-4 AGAIN: it fits no model and indexes no static
# artifact - it is a live, retrieval + grounded-generation service. This image therefore does NOT
# COPY a joblib bundle or a Parquet index; it COPYs the real, static prerequisites every real
# /resolve call reads (BP1-5's own real Gate 7 executive rollup manifests, and BP6 Gate 2's
# PII-screened CSV + Gate 4's eligible-bucket trace), and makes a REAL, LIVE external call to the
# Google Gemini API on every request - it never fabricates a recommendation.
#
# REQUIRES a real GEMINI_API_KEY at container RUN time (not build time - never baked into the
# image; pass with `docker run -e GEMINI_API_KEY=... ` or the compose file's own env_file/
# environment section) and REQUIRES BP6 Gates 2 and 4 (and BP1-5's own Gate 7) to have been run
# for real first - the COPY steps below fail loudly (file not found) until they have, the same
# honesty pattern as every other BP's own Dockerfile in this project.
#
# MINIMAL REAL RUNTIME DEPENDENCY LIST - grep-verified (2026-09-24) against
# src/services/bp6_resolution_service.py's and src/genai/bp6_grounded_generation.py's own
# module-level import statements: fastapi, pydantic, pandas (bp6_grounded_generation.py's own
# `import pandas as pd`, used by select_real_narrative_sample), google-genai (the real Gemini SDK,
# floor >=1.0 per requirements.txt's own disclosed version-floor reasoning). `uvicorn` is added
# below purely as the ASGI server this image's CMD invokes - the service module itself never
# imports it.

# API-key auth added 2026-09-26 (src/services/service_auth.py, see SECURITY.md): this image's
# dependency list above is UNCHANGED - the new services.service_auth import needs only fastapi
# (already installed above), nothing new.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - BP6 GenAI Resolution Assistant"
LABEL org.opencontainers.image.description="Real, live, grounded-generation resolution-recommendation service. Every /resolve call makes one real external call to the Google Gemini API - never a mock or cached response."

WORKDIR /app

RUN useradd --no-create-home --uid 1000 c360service

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "pydantic>=2.0" \
        "uvicorn>=0.30" \
        "pandas>=2.0" \
        "google-genai>=1.0"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/ ./src/

# Real, static prerequisites this service reads at request time (never at build time) - BP1-5's
# own real Gate 7 executive rollup manifests (evidence bundle) and BP6's own Gate 2/Gate 4 outputs.
COPY --chown=c360service:c360service notebooks/bp1_customer_intent_classification/artifacts/executive_rollup_manifest.json \
     ./notebooks/bp1_customer_intent_classification/artifacts/executive_rollup_manifest.json
COPY --chown=c360service:c360service notebooks/bp2_customer_friction_classification/artifacts/executive_rollup_manifest.json \
     ./notebooks/bp2_customer_friction_classification/artifacts/executive_rollup_manifest.json
COPY --chown=c360service:c360service notebooks/bp3_complaint_escalation_prediction/artifacts/executive_rollup_manifest.json \
     ./notebooks/bp3_complaint_escalation_prediction/artifacts/executive_rollup_manifest.json
COPY --chown=c360service:c360service notebooks/bp4_customer_journey_analytics/artifacts/executive_rollup_manifest.json \
     ./notebooks/bp4_customer_journey_analytics/artifacts/executive_rollup_manifest.json
COPY --chown=c360service:c360service notebooks/bp5_root_cause_driver_analytics/artifacts/executive_rollup_manifest.json \
     ./notebooks/bp5_root_cause_driver_analytics/artifacts/executive_rollup_manifest.json
COPY --chown=c360service:c360service notebooks/bp6_genai_resolution_assistant/artifacts/gate2_pii_screened_narrative_text.csv \
     ./notebooks/bp6_genai_resolution_assistant/artifacts/gate2_pii_screened_narrative_text.csv
COPY --chown=c360service:c360service notebooks/bp6_genai_resolution_assistant/artifacts/gate4_explainability_trace.json \
     ./notebooks/bp6_genai_resolution_assistant/artifacts/gate4_explainability_trace.json

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
# GEMINI_API_KEY is intentionally NOT set here - pass it at `docker run` / compose time. A missing
# key is handled honestly (MissingApiKeyError, 503) by call_grounded_generation() itself, never
# silently substituted.

USER c360service

EXPOSE 8006

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8006/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp6_resolution_service:app", "--host", "0.0.0.0", "--port", "8006"]
