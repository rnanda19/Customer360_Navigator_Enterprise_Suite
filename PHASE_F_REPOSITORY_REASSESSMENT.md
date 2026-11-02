# Phase F — Repository Reassessment (Master Engineering Directive)

**Baseline commit:** `3283c29de78da6f1e53bc7d75f9fc10dc1d4352f` (confirmed `git log -1`, HEAD, pushed,
`origin/main` matches). **All 11 CI checks on this commit are green** (verified live via the
GitHub API, not assumed): `deploy`, `report-build-status`, `Real MLflow registry + governance +
promotion + rollback mechanics`, `lint`, `docker-validate`, `Start dev-mode Vault, write + read a
real secret, verify it matches`, `security`, `notebook-syntax-check`, `build`, `Analyze (python)`,
`test` — all `completed`/`success`.

This document does not repeat Phase E's own repository assessment (`PHASE_E_IMPLEMENTATION_
REPORT.md`'s Stage A section already covers per-BP service/Docker/CI/security/monitoring
structure in detail) — it extends that assessment with what changed since, and organizes findings
by the 10 forward phases (G–P) this directive defines, per that document's own request.

## New findings since Phase E Stage A+C

1. **19 open Dependabot PRs**, not yet individually reviewed (Rule 13 explicitly forbids merging
   without compatibility testing). Checked live: every one of them reports GitHub's
   `mergeable_state: unstable` (at least one required check is failing or pending on that PR's own
   branch) — consistent with this project's own documented history of exact-pinned lint/format/
   security tool versions breaking on an unpinned bump (`requirements.txt`'s own 2026-09-26 CI
   incident comment, and the already-known mypy 1.11.2→2.3.1 INTERNAL ERROR regression, which is
   PR #5). Categories: 7 Docker base-image bumps (python:3.11-slim → 3.14-slim, one per service),
   2 GitHub Actions bumps (checkout, setup-python), 1 mypy bump (known-broken), and 9 pip
   dependency bumps (pyarrow, shap, transformers, statsmodels, psutil, duckdb, catboost, pytest,
   pre-commit). None merged in this phase — real compatibility testing per PR is scoped into
   Phase J.
2. **`BENCHMARKS.md` carries a stale claim**: "1,000+ tests" — the real, CI-verified count is
   **732** (723 passed + 9 skipped, 0 failed). A prior commit (`f9d2897`) already fixed this exact
   claim in `README.md` but missed this file. Flagged for correction in Phase O (docs), not fixed
   here to avoid scattering unrelated one-line fixes across phases that should each stay
   independently reviewable.
3. **`src/monitoring/prediction_monitor.py` is already BP-agnostic in its real implementation**
   (every function takes `bp_id` as a plain parameter) — the informal shorthand "BP1-only" used
   in this project's own prior commentary describes that no service actually *calls* it yet, not
   a code-level limitation. This matters for Phase G's scope: the integration gap is wiring, not
   genericization.
4. **A real Docker-permissions risk was found during Phase G planning, not yet present as a bug**:
   `src/services/docker/bp1_inference_service/Dockerfile` never creates or `COPY --chown`s a
   `governance/` directory, and `WORKDIR /app` is created while the image is still root (before
   `USER c360service`), so it is `root:root` `755`. If a service tries to write to
   `governance/*.jsonl` at runtime (needed to wire real monitoring into a live endpoint), the
   non-root `c360service` user cannot create that directory and the write fails. This is addressed
   as part of Phase G below, not deferred, because it would otherwise make the "actual monitoring
   integration" acceptance criterion silently fail in the one environment (a running container)
   where it matters most.
5. **A real architecture diagram already exists** (`docs/architecture/c360_architecture_diagram.svg`)
   — Phase O updates it rather than creating one from nothing.

## Required implementation, by phase (capability / evidence / missing / risks / dependencies / required work / acceptance criteria / 13-dimension impact)

### Phase G — Unified production monitoring
- **Existing capability**: four real, independently-tested modules (`prediction_monitor.py`,
  `drift_detection.py`, `fairness_monitor.py`, `alerting.py`) that have never been composed.
- **Evidence**: each module's own docstring explicitly discloses this (see Phase E's Stage A
  survey); 100% of their current test coverage exercises them in isolation.
- **Missing**: a real composition layer; schema/data-quality validation; wiring into a live
  service; structured per-run monitoring events; an alert audit trail.
- **Risks**: the Docker-permissions issue above; a composition layer that merely imports all four
  without using their outputs together would satisfy the letter but not the intent of "actual
  integration."
- **Dependencies**: none external; pure Python + the existing MLflow/registry modules for model
  version lookup.
- **Required implementation**: `src/monitoring/unified_monitor.py` (data-quality validator +
  drift-from-two-windows + fairness composition + alert evaluation + structured event log);
  wire `record_prediction_event` into BP1's real `/predict` endpoint (resilient — a monitoring
  failure must not break the real prediction response); fix the Dockerfile permissions gap.
- **Acceptance criteria**: real tests per module interaction; a real FastAPI TestClient test
  proving a `/predict` call produces a real `governance/prediction_events.jsonl` entry; a test
  proving a monitoring-write failure is caught, logged, and does not raise past the endpoint.
- **13-dimension impact**: Model monitoring and observability (direct); Production integration
  and resilience (the graceful-degradation test); Software architecture (composition over
  duplication).

### Phase H — Centralized model serving
- **Existing**: 7 independent, structurally similar FastAPI services sharing `service_auth.py`
  and `service_common.py`.
- **Missing**: no shared request/response envelope, no correlation ID, no API version header,
  no consistent exception shape across services.
- **Required**: a shared `src/services/serving_contracts.py` (correlation-ID middleware/dependency,
  a common response envelope BPs can adopt without breaking their existing response models,
  structured logging helper) — additive, not a breaking rewrite of 7 working services.
- **13-dimension impact**: API and Docker engineering; Software architecture.

### Phase I — Multi-model governance
- **Existing**: Phase E Stage C's `enterprise_status.py` (structural, cross-BP, real).
- **Missing**: BP2/BP3 real retraining is gated on real data availability in this environment —
  addressed honestly (attempted where the real BANKING77-style data is reachable; reported as a
  gap otherwise, never fabricated); BP4–BP8 problem-specific versioning per the directive's own
  examples.
- **13-dimension impact**: MLOps and model governance.

### Phase J — Security and secrets
- **Existing**: real fail-closed API-key auth; a real but unwired Vault dev-mode PoC.
- **Missing**: a secrets-provider abstraction; individual Dependabot PR triage; secret-scanning in
  CI; SBOM.
- **13-dimension impact**: Security and privacy; CI/CD and automated testing.

### Phase K — Disaster recovery
- **Existing**: real, tested rollback (Phase D) for BP1 only.
- **Missing**: backup/restore drills for the MLflow store and governance logs; measured (not
  invented) RTO/RPO.
- **13-dimension impact**: Production integration and resilience.

### Phase L — Performance and scalability
- **Existing**: per-BP build-time benchmarks (`BENCHMARKS.md`, pre-existing, unrelated to
  serving). No serving-layer benchmark exists.
- **Missing**: real latency/throughput measurement against a real running service.
- **Risk**: no Docker in this sandbox — load-testing a containerized service requires either the
  user's own machine or CI; a real in-process benchmark (uvicorn test server, not Docker) is the
  honest, achievable substitute here, disclosed as such.
- **13-dimension impact**: Production integration and resilience; Software architecture.

### Phase M — Data quality and lineage
- **Existing**: per-BP ad hoc validation inside notebooks; no shared contract layer.
- **13-dimension impact**: Data engineering and quality.

### Phase N — Responsible AI
- **Existing**: real, substantial evidence already scattered across BP3 (disparate impact), BP6
  (human review precedent), BP7 (self-test + fairness audit), SHAP (`requirements.txt` already
  lists it). Missing: consolidation into auditable model cards.
- **13-dimension impact**: Responsible AI and fairness; Documentation and reproducibility.

### Phase O — CI/CD and docs
- Extends existing workflows for whatever G–N add; writes/updates the 10 named documents.

### Phase P — Independent audit and rescoring
- Final honest 13-dimension scoring against real, verified evidence only.

## Plan going forward

Executing in the directive's own stated priority order (G → H → I → J → K → L → M → N → O → P),
each phase: implemented, tested (unit + full regression), linted/security-scanned, committed
separately, and pushed with its real CI result checked before moving on — matching Section 15's
execution rules exactly. No phase will be marked complete in documentation without matching code
and passing tests.
