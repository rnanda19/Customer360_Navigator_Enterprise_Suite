# Phase H — Centralized Model Serving Contracts: Implementation Report

**Status:** Complete. **Prior commit:** `c7a05b1` (Phase G). **Part of:** the Master Engineering Directive, executed per the user's standing instruction to proceed through all phases without re-prompting.

## What this phase adds

Phase F's reassessment found 7 independent, structurally similar FastAPI services (BP1-BP7, plus `bp_activation_service.py`) sharing `service_auth.py` and `service_common.py`, but with no shared request-correlation mechanism, no API-version signal, and no consistent structured-logging shape across them. Phase H closes that gap with one new, fully additive module:

- **`src/services/serving_contracts.py`** (new, 147 lines): `CorrelationIdMiddleware` (echoes a caller-supplied `X-Correlation-ID` or generates a real `uuid4`), `ApiVersionHeaderMiddleware` (a fixed, informational `X-API-Version` header), `get_correlation_id` (a FastAPI dependency reading the ID the middleware attached, with a safe fallback if the middleware isn't mounted), `install_serving_contracts(app)` (the one call a service adds to adopt both middlewares), and `log_event` (one structured-JSON logging helper).

### Design decision: headers, not a body envelope

The directive's own Phase F scoping called for "a common response envelope BPs can adopt without breaking their existing response models." Wrapping existing response bodies (`BP1PredictResponse` etc.) in a generic envelope would be a breaking change to every already-verified response contract — exactly what the Master Engineering Directive's backward-compatibility rule prohibits. The honest way to add a common envelope without that rewrite is to carry it in HTTP headers (`X-Correlation-ID`, `X-API-Version`) rather than the body — verified by a dedicated test (`test_response_body_shape_is_completely_unchanged_by_adopting_the_middleware`) that the JSON body is byte-for-byte identical with or without this module adopted.

### A real, verified limitation disclosed rather than assumed

While testing, a genuine Starlette behavior was found and is now both tested and documented rather than silently assumed: `CorrelationIdMiddleware`'s `response.headers[...]` line runs for every *normally-completed* response — including a handled 404 or a 422 validation error, both confirmed with a real test — but **not** on a request whose handler raises an exception with no registered exception handler. In that case the exception propagates out of `await call_next(request)` before the header-setting line ever executes, and the ASGI server's bare 500 response carries neither header. This is standard `BaseHTTPMiddleware` behavior, not a defect in this module, but the first draft of this module's own docstring overstated coverage ("even on a request this middleware never saw reach a handler (e.g. a 404 or a validation 422)") — this was corrected after `test_correlation_id_header_is_present_even_on_an_unhandled_server_error` failed against the real implementation, and two tests now pin the real, verified behavior for both the covered case (404) and the uncovered one (unhandled 500), so a future change that silently alters this can't pass CI unnoticed.

## Reference-instance wiring (BP1 only — disclosed, not generalized)

`src/services/bp1_inference_service.py` adopts all three pieces: `install_serving_contracts(app, api_version="1.0")` right after constructing `app`; `/predict` now takes a `correlation_id: str = Depends(get_correlation_id)` and calls `log_event(...)` with `bp_id`, `correlation_id`, `n_predictions`, and `latency_ms` inside the same resilience `try/except` that already wraps the Phase G monitoring write (a logging failure, like a monitoring failure, must never turn a real prediction into a 5xx).

**Generalizing this to BP2-BP8 is an explicit, disclosed follow-up — not claimed as done in this phase**, consistent with the Master Engineering Directive's rule against claiming unimplemented capabilities. The pattern established here (one `install_serving_contracts()` call plus one `Depends(get_correlation_id)` per predict-style endpoint) is additive and should generalize directly, but each service needs its own test-isolation review first (BP1's own test file needed one — see Phase G's report — before it could safely adopt a per-request side effect).

## Verification performed this phase

- `tests/services/test_serving_contracts.py` (new, 12 tests): 12/12 passed, including the real-vs-assumed-behavior pair described above.
- `tests/services/test_bp1_inference_service.py`: 2 new tests added (`test_predict_response_carries_phase_h_serving_contract_headers`, `test_predict_echoes_back_a_caller_supplied_correlation_id`) proving the wiring reaches the real `/predict` endpoint, not just the standalone module. All 16 tests in this file pass.
- Full regression suite (same batching as Phase G, to fit this environment's per-command time budget): `tests/mlops` 78 passed; `tests/monitoring tests/shared tests/identity_resolution tests/services tests/deployment` 444 passed/3 skipped; all eight `tests/bp*` directories 238 passed/6 skipped. **Total: 760 passed, 9 skipped, 0 failed (769 total)** — up from Phase G's 746/9/755 by exactly the 14 new tests (12 + 2), zero regressions.
- `black --config pyproject.toml`, `isort --check-only`, `flake8`: clean on all 4 changed/new files (one real `F401` unused-import finding on a first pass, fixed before this report was written).
- `bandit -c pyproject.toml -r`: 0 unaddressed findings (the one B110 nosec from Phase G's resilience wrapper remains, unchanged, still justified).
- `git status` reconfirmed zero pollution of the real, committed `governance/prediction_events.jsonl` after this phase's test runs (the Phase G autouse isolation fixture still holds for the 2 new predict-calling tests added here).

## What this phase does NOT claim

- Does not wire `serving_contracts.py` into BP2-BP8 (see above).
- Does not add a correlation ID to log lines or responses on a truly unhandled 500 (documented, tested limitation, not a silent gap).
- Does not add distributed tracing, a metrics backend, or cross-service log aggregation — `log_event` is a local, structured logging helper only.
- Does not change any BP's existing request/response Pydantic model, business logic, or governance schema.

## Files changed/added this phase

- `src/services/serving_contracts.py` (new)
- `tests/services/test_serving_contracts.py` (new, 12 tests)
- `src/services/bp1_inference_service.py` (modified — reference-instance wiring)
- `tests/services/test_bp1_inference_service.py` (modified — 2 new tests)
- `PHASE_H_IMPLEMENTATION_REPORT.md` (this file)
