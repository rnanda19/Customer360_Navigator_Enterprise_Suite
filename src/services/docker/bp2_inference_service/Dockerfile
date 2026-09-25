# Customer360 Navigator - BP2 Customer Friction Classification inference service
# Hardening Step 5 (Docker packaging). Mirrors bp1_inference_service's own Dockerfile - see that
# file's header for the shared build-context / real-model rationale (not repeated here).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp2_inference_service/Dockerfile -t c360-bp2-service .
#
# REQUIRES Hardening Step 2 to have been run FOR REAL first (see bp1's Dockerfile header) - COPYs
# your own real bp2_champion_bundle.joblib, never a Claude-generated one.
#
# xgboost is a REAL runtime dependency here, not a leftover from the notebook-execution
# requirements.txt: BP2's real, already-confirmed champion (configs/bp2_customer_friction_
# classification.yaml -> gate3_model_benchmark.champion_model) is "xgboost" - joblib/pickle needs
# the XGBClassifier class importable to reconstruct the fitted classifier when the bundle is
# loaded, even though src/features/bp2_friction_features.py itself only imports xgboost lazily,
# inside make_candidates() (verified by grep, 2026-09-22 - not assumed). lightgbm/catboost are
# NOT included: BP2's real champion is xgboost, not either of those, so installing them here would
# be dead weight this specific real model never needs - if a future re-run of Gate 3 changes the
# champion, this Dockerfile's dependency list needs a matching real update, not a speculative
# "install everything" hedge now.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - BP2 Inference Service"
LABEL org.opencontainers.image.description="Predicts a complaint's friction-severity class from real structured CFPB fields."

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
        "xgboost>=2.1"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/ ./src/
COPY --chown=c360service:c360service models/bp2_customer_friction_classification/bp2_champion_bundle.joblib \
     ./models/bp2_customer_friction_classification/bp2_champion_bundle.joblib
COPY --chown=c360service:c360service models/bp2_customer_friction_classification/bp2_model_metadata.json \
     ./models/bp2_customer_friction_classification/bp2_model_metadata.json

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER c360service

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp2_inference_service:app", "--host", "0.0.0.0", "--port", "8002"]
