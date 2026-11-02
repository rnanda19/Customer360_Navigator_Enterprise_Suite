"""
src/services/serving_contracts.py — Customer360 Navigator

Phase H: Centralized model serving contracts. Additive shared infrastructure for this project's
FastAPI services, extending the existing service_common.py module-sharing pattern established in
Hardening Step 3 (BP1/BP2) rather than reimplementing it. Phase F's reassessment found 7
independent, structurally similar FastAPI services (src/services/bp1_inference_service.py through
bp7_decision_engine_service.py, plus bp_activation_service.py) sharing service_auth.py and
service_common.py, but with no shared request-correlation mechanism, no API-version signal, and
no consistent structured-logging shape across them. This module closes that gap WITHOUT rewriting
or changing the request/response shape of any existing, already-tested endpoint - a deliberate
design choice (see the module-level functions below) consistent with the Master Engineering
Directive's explicit backward-compatibility rule.

What this module provides, and why each piece is additive rather than a breaking change:

1. CorrelationIdMiddleware / get_correlation_id - lets ops correlate one logical request across
   a service's logs (and, once adopted by more than one service, across services) via a real
   X-Correlation-ID response header: generated with uuid4 if the caller didn't supply one, echoed
   back unchanged if they did. This is carried in HTTP headers, never in the response BODY, so it
   cannot change any existing Pydantic response_model's shape or break any existing client/test
   that only inspects the body.

2. ApiVersionHeaderMiddleware - an informational X-API-Version response header. Also header-only,
   for the same backward-compatibility reason: this project's response models (BP1PredictResponse
   etc.) are not wrapped in a generic envelope, because doing so would be a breaking change to
   every existing, already-verified response contract. A header-based "common envelope" is the
   honest way to add this without the rewrite the Master Engineering Directive's own rules
   (preserve BP1-8, maintain backward compatibility, never rewrite without disclosure) rule out.

3. log_event - one structured JSON logging helper, so any service that adopts it gets the same
   machine-parseable log shape (bp_id, event, correlation_id, timestamp, caller-supplied fields).
   Additive: does not require removing or replacing any existing logging/print call in any
   service.

install_serving_contracts(app) is the one call a service adds to adopt (1) and (2); log_event is
called directly wherever a service wants a structured log line.

Reference-instance wiring this phase: src/services/bp1_inference_service.py adopts all three
(see its own module docstring for the specific lines changed). Generalizing this to BP2-BP8 is an
explicit, disclosed follow-up - NOT claimed as done here (Master Engineering Directive Rule 2:
never claim unimplemented capabilities).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

CORRELATION_ID_HEADER = "X-Correlation-ID"
API_VERSION_HEADER = "X-API-Version"
DEFAULT_API_VERSION = "1.0"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reads X-Correlation-ID from the inbound request if the caller supplied one (so a caller
    that already has its own request-tracing ID gets it echoed back unchanged, letting them
    correlate across their own systems too); generates a real uuid4 otherwise. Stores it on
    request.state for handlers to read via get_correlation_id(), and sets it on the response
    headers either way - so every NORMALLY-COMPLETED response (2xx/3xx/4xx, including a 404 or a
    422 validation error - both handled by Starlette's own routing/validation before control
    returns from call_next) carries a real, non-empty correlation ID.

    Verified, honest limitation (see tests/services/test_serving_contracts.py's
    test_correlation_id_header_is_absent_on_a_truly_unhandled_exception): a handler that raises
    an exception with NO registered exception handler propagates that exception out of
    `await call_next(request)` before this method's own `response.headers[...]` line runs, so
    the ASGI server's bare 500 response the client actually receives carries neither of this
    module's headers. This is standard Starlette BaseHTTPMiddleware behavior, not something this
    class works around - a service wanting correlation IDs on unhandled-exception responses too
    would need its own @app.exception_handler, which is out of this module's additive scope."""

    def __init__(self, app: ASGIApp, header_name: str = CORRELATION_ID_HEADER):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(self.header_name)
        correlation_id = incoming if incoming else str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[self.header_name] = correlation_id
        return response


class ApiVersionHeaderMiddleware(BaseHTTPMiddleware):
    """Sets a fixed, informational X-API-Version response header on every response. Purely
    additive - carries no request/response body shape at all, so it can never break an existing
    client or test that doesn't look for this header."""

    def __init__(
        self,
        app: ASGIApp,
        api_version: str = DEFAULT_API_VERSION,
        header_name: str = API_VERSION_HEADER,
    ):
        super().__init__(app)
        self.api_version = api_version
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers[self.header_name] = self.api_version
        return response


def get_correlation_id(request: Request) -> str:
    """FastAPI dependency: returns the correlation ID CorrelationIdMiddleware attached to this
    request. Never raises - if a service forgets to mount the middleware, this still returns a
    real, usable (freshly generated) ID rather than erroring, so adopting it inside a handler is
    always safe even if the middleware wiring is somehow missing or misordered."""
    existing = getattr(request.state, "correlation_id", None)
    return existing if existing else str(uuid.uuid4())


def install_serving_contracts(app: FastAPI, *, api_version: str = DEFAULT_API_VERSION) -> None:
    """The one call a service's module adds (right after constructing its FastAPI `app`
    instance) to adopt the correlation-ID and API-version headers. Mounts both middlewares;
    order between these two specific middlewares has no functional effect since each only reads
    the request and sets its own, distinct response header - neither depends on the other having
    run first."""
    app.add_middleware(ApiVersionHeaderMiddleware, api_version=api_version)
    app.add_middleware(CorrelationIdMiddleware)


def log_event(
    logger: logging.Logger,
    *,
    bp_id: str,
    event: str,
    correlation_id: Optional[str] = None,
    **fields: Any,
) -> None:
    """Writes one structured JSON log line via the given logger (INFO level). Consistent,
    machine-parseable shape across every service that adopts it: bp_id, event name, correlation
    ID (None if the caller has none - never fabricated), a real UTC timestamp, plus whatever
    extra fields the caller passes (e.g. latency_ms, n_predictions, error). Additive - does not
    require removing or replacing any existing logging or print call in any service; a service
    can call this alongside its existing logging with no conflict."""
    payload: dict[str, Any] = {
        "bp_id": bp_id,
        "event": event,
        "correlation_id": correlation_id,
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(fields)
    logger.info(json.dumps(payload, sort_keys=True, default=str))
