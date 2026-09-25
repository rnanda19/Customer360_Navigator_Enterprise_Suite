# Customer360 Navigator - BP3 Complaint Escalation Prediction inference service
# Hardening Step 5 (Docker packaging). Mirrors bp1_inference_service's and bp2_inference_service's
# own Dockerfiles - see bp1's Dockerfile header for the shared build-context / real-model
# rationale (not repeated here).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp3_inference_service/Dockerfile -t c360-bp3-service .
#
# REQUIRES Hardening Step 2 to have been run FOR REAL first (see bp1's Dockerfile header) - COPYs
# your own real bp3_champion_bundle.joblib, never a Claude-generated one.
#
# xgboost is a REAL runtime dependency here, same real reason as bp2_inference_service's Dockerfile:
# BP3's real, already-confirmed champion (configs/bp3_complaint_escalation_prediction.yaml ->
# gate5_decision_layer.champion_model) is "xgboost" - joblib/pickle needs the XGBClassifier class
# importable to reconstruct the fitted classifier when the bundle is loaded.
#
# polars and PyYAML are REAL runtime dependencies here that BP1's and BP2's Dockerfiles do NOT
# need - a genuine BP3-specific finding, grep-verified against this service's actual import chain
# (2026-09-24), not assumed by copying bp2's dependency list: bp3_inference_service.py imports
# COMPANY_COL/FEATURE_COLS_CATEGORICAL from src/features/bp3_escalation_features.py, which itself
# `import polars as pl` at module level and imports CFPB_DTYPES from src/taxonomy/taxonomy_mapper.py,
# which in turn imports both `polars` and `yaml` at module level - so importing bp3_inference_service
# transitively executes all of that, even though the service's own request/response handling never
# touches a Polars DataFrame directly. lightgbm/catboost are NOT included, same reasoning as bp2's
# Dockerfile: BP3's real champion is xgboost, not either of those.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - BP3 Inference Service"
LABEL org.opencontainers.image.description="Predicts whether a complaint requires intervention (monetary relief) from real structured CFPB fields."

WORKDIR /app

RUN useradd --no-create-home --uid 1000 c360service

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "pydantic>=2.0" \
        "uvicorn>=0.30" \
        "joblib>=1.3" \
        "numpy>=1.26" \
        "pandas>=2.2" \
        "scikit-learn>=1.5" \
        "scipy>=1.13" \
        "xgboost>=2.1" \
        "polars>=1.0" \
        "PyYAML>=6.0"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/ ./src/
COPY --chown=c360service:c360service models/bp3_complaint_escalation_prediction/bp3_champion_bundle.joblib \
     ./models/bp3_complaint_escalation_prediction/bp3_champion_bundle.joblib
COPY --chown=c360service:c360service models/bp3_complaint_escalation_prediction/bp3_model_metadata.json \
     ./models/bp3_complaint_escalation_prediction/bp3_model_metadata.json

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER c360service

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8003/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp3_inference_service:app", "--host", "0.0.0.0", "--port", "8003"]
