"""
tests/services/test_serving_contracts.py — Customer360 Navigator

Tests for src/services/serving_contracts.py (Phase H). Builds tiny, real FastAPI apps in-process
and drives them through the real TestClient - no mocking of the middleware or dependency
internals - to prove the headers, dependency fallback, and structured logging actually behave as
documented, and that adopting this module changes no existing response body shape.
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from services.serving_contracts import (
    API_VERSION_HEADER,
    CORRELATION_ID_HEADER,
    DEFAULT_API_VERSION,
    get_correlation_id,
    install_serving_contracts,
    log_event,
)


def _build_app(api_version: str = DEFAULT_API_VERSION) -> FastAPI:
    app = FastAPI()
    install_serving_contracts(app, api_version=api_version)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/whoami")
    def whoami(correlation_id: str = Depends(get_correlation_id)):
        return {"correlation_id": correlation_id}

    @app.get("/boom")
    def boom():
        raise ValueError("deliberate test failure")

    return app


def test_response_carries_a_generated_correlation_id_when_none_supplied():
    client = TestClient(_build_app())
    response = client.get("/ping")
    assert response.status_code == 200
    correlation_id = response.headers.get(CORRELATION_ID_HEADER)
    assert correlation_id
    # A real uuid4 - 36 chars including hyphens, not an empty placeholder.
    assert len(correlation_id) == 36


def test_response_echoes_back_a_caller_supplied_correlation_id_unchanged():
    client = TestClient(_build_app())
    response = client.get("/ping", headers={CORRELATION_ID_HEADER: "caller-supplied-id-123"})
    assert response.status_code == 200
    assert response.headers.get(CORRELATION_ID_HEADER) == "caller-supplied-id-123"


def test_two_requests_with_no_caller_id_get_two_different_generated_ids():
    client = TestClient(_build_app())
    first = client.get("/ping").headers.get(CORRELATION_ID_HEADER)
    second = client.get("/ping").headers.get(CORRELATION_ID_HEADER)
    assert first != second


def test_response_carries_the_configured_api_version_header():
    client = TestClient(_build_app(api_version="2.3"))
    response = client.get("/ping")
    assert response.headers.get(API_VERSION_HEADER) == "2.3"


def test_default_api_version_is_used_when_not_overridden():
    client = TestClient(_build_app())
    response = client.get("/ping")
    assert response.headers.get(API_VERSION_HEADER) == DEFAULT_API_VERSION


def test_get_correlation_id_dependency_returns_the_same_id_the_header_carries():
    client = TestClient(_build_app())
    response = client.get("/whoami", headers={CORRELATION_ID_HEADER: "match-me-456"})
    assert response.status_code == 200
    assert response.json()["correlation_id"] == "match-me-456"
    assert response.headers.get(CORRELATION_ID_HEADER) == "match-me-456"


def test_response_body_shape_is_completely_unchanged_by_adopting_the_middleware():
    """The whole point of the header-only design: a client that only reads the JSON body sees
    no difference at all from a service that never adopted this module."""
    client = TestClient(_build_app())
    response = client.get("/ping")
    assert response.json() == {"ok": True}


def test_correlation_id_header_is_present_on_a_handled_404():
    """A 404 is handled by Starlette's own routing before it ever leaves call_next, so the
    middleware's response.headers[...] line after call_next still runs - verified real behavior,
    not assumed."""
    client = TestClient(_build_app())
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.headers.get(CORRELATION_ID_HEADER)
    assert response.headers.get(API_VERSION_HEADER) == DEFAULT_API_VERSION


def test_correlation_id_header_is_absent_on_a_truly_unhandled_exception():
    """Documents a real, verified limitation rather than an assumed guarantee: when a handler
    raises an exception with no exception handler registered for it, Starlette's
    BaseHTTPMiddleware.dispatch() never reaches its own response.headers[...] line - the
    exception propagates out of `await call_next(request)` before that line runs, and the ASGI
    server's own bare 500 response is what the client actually sees, with neither of this
    module's headers on it. This test exists so a future change to serving_contracts.py (or to
    the Starlette/FastAPI version pinned in pyproject.toml) that silently changes this behavior
    gets caught, rather than this module's docstring quietly drifting from what it actually
    does."""
    client = TestClient(_build_app(), raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.headers.get(CORRELATION_ID_HEADER) is None
    assert response.headers.get(API_VERSION_HEADER) is None


def test_get_correlation_id_never_raises_when_middleware_is_not_mounted():
    """Documented fallback: a handler using the dependency on an app that never called
    install_serving_contracts still gets a real, usable ID rather than an AttributeError."""
    app = FastAPI()

    @app.get("/no-middleware")
    def no_middleware(correlation_id: str = Depends(get_correlation_id)):
        return {"correlation_id": correlation_id}

    client = TestClient(app)
    response = client.get("/no-middleware")
    assert response.status_code == 200
    assert response.json()["correlation_id"]


def test_log_event_writes_one_structured_json_line_with_the_given_fields(caplog):
    logger = logging.getLogger("test_serving_contracts_logger")
    with caplog.at_level(logging.INFO, logger="test_serving_contracts_logger"):
        log_event(logger, bp_id="bp1", event="predict_succeeded", correlation_id="xyz", latency_ms=5.5)

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["bp_id"] == "bp1"
    assert payload["event"] == "predict_succeeded"
    assert payload["correlation_id"] == "xyz"
    assert payload["latency_ms"] == 5.5
    assert "logged_at_utc" in payload


def test_log_event_defaults_correlation_id_to_none_rather_than_fabricating_one(caplog):
    logger = logging.getLogger("test_serving_contracts_logger_2")
    with caplog.at_level(logging.INFO, logger="test_serving_contracts_logger_2"):
        log_event(logger, bp_id="bp2", event="no_correlation_id_available")

    payload = json.loads(caplog.records[0].message)
    assert payload["correlation_id"] is None
