# Customer360 Navigator - Activation Layer (SIMULATED downstream adapters over BP7's real output)
# Mirrors bp4/bp7's own Dockerfile structure (python:3.11-slim, non-root c360service user,
# project-root build context, HEALTHCHECK against /health).
#
# BUILD CONTEXT: the Customer360_Navigator_Enterprise_Suite project ROOT:
#
#   docker build -f src/services/docker/bp_activation_service/Dockerfile -t c360-activation-service .
#
# This service has NO model bundle and NO persisted data artifact to COPY at all - it is a
# stateless router over three SIMULATED adapters (see src/services/bp_activation_service.py's own
# module docstring for exactly what "simulated" means and does not mean here: no real CRM,
# case-management, or notification system is ever contacted). Its only real state is an
# in-process SQLite store created at startup, never persisted to disk and never baked into the
# image.
#
# MINIMAL REAL RUNTIME DEPENDENCY LIST - grep-verified against
# src/services/bp_activation_service.py's own module-level import statements: stdlib
# (sqlite3, threading, uuid, contextlib, datetime, typing, json) + fastapi + pydantic. NO polars,
# NO pandas, NO joblib, NO scikit-learn - the lightest of all 8 services' images.

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Customer360 Navigator - Activation Layer (SIMULATED)"
LABEL org.opencontainers.image.description="Simulated case/CRM/notification activation adapters over BP7's real decision output. No adapter contacts any real external system - see the service module's own docstring."

WORKDIR /app

RUN useradd --no-create-home --uid 1000 c360service

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "pydantic>=2.0" \
        "uvicorn>=0.30"

COPY --chown=c360service:c360service PROJECT_STRUCTURE_LOCKED.md ./PROJECT_STRUCTURE_LOCKED.md
COPY --chown=c360service:c360service src/services/bp_activation_service.py ./src/services/bp_activation_service.py
COPY --chown=c360service:c360service src/services/service_auth.py ./src/services/service_auth.py
COPY --chown=c360service:c360service src/services/__init__.py ./src/services/__init__.py

ENV C360_PROJECT_ROOT=/app
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

USER c360service

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "services.bp_activation_service:app", "--host", "0.0.0.0", "--port", "8010"]
