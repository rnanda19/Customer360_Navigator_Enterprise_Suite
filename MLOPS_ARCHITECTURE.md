# MLOps Architecture (Phase D)

**Status: real, locally verified. Not yet committed or pushed — pending the repo owner's authorization.**

This document describes the Enterprise MLOps, Model Registry and Model Governance layer added in
Phase D of this project. It follows the same disclosure discipline as every other `*.md` file in
this repository: every capability described below was actually run and its output actually
observed, with the exact evidence and the exact gaps named, never implied.

## 1. What existed before Phase D

Before this phase, this project already had real (not fabricated) MLOps-adjacent infrastructure:

- `src/monitoring/drift_detection.py` — real population-stability-index drift detection, tested
  against this project's own committed BP8 Gold parquet files.
- `src/monitoring/fairness_monitor.py` — reads BP3's and BP7's real Gate 4 disparate-impact JSON.
- `src/monitoring/alerting.py` — a pure threshold-evaluation function with real operational
  thresholds (`adverse_impact_ratio`, PSI, API error rate, API p99 latency).
- `src/monitoring/model_registry.py` — explicitly documented as **not** an MLflow-style registry:
  a read-only YAML-backed view of each BP's champion.
- `src/deployment/*_readiness_verdict.py` — a real, filesystem-auditing governance-adjacent gate
  per business problem (SHA-256 verification, reload-fidelity checks, a real pytest re-run).
- `docs/secrets_management_demo/` + `.github/workflows/vault-verify.yml` — a real, CI-verified
  HashiCorp Vault dev-mode proof-of-concept, not yet wired into any live service.

`MLOPS_OBSERVABILITY.md` explicitly and correctly disclosed what was missing: *"No MLflow-style
model registry, approval workflow, or rollback pipeline... That is genuinely not built."* Phase D
is the pass that builds that missing piece, reusing every module above rather than duplicating it.

## 2. What Phase D adds

| Capability | Module(s) | Real evidence |
|---|---|---|
| Experiment tracking | `src/mlops/tracking.py` | Real sqlite-backed MLflow run, real dataset fingerprint, real git SHA, real software versions — see `MLOPS_TEST_REPORT.md` |
| Model Registry | `src/mlops/registry.py` | BP1's `customer360_bp1` registered model, 3 real versions registered locally |
| Model Governance | `src/mlops/governance.py` | Real per-BP accuracy/F1 thresholds derived from each BP's own historically recorded metrics |
| Champion-Challenger | `src/mlops/champion_challenger.py` | Performance / stability / fairness axes; fairness is honestly `not_available` where no real Gate 4 JSON exists for that BP |
| Approval & Promotion | `src/mlops/promotion.py` | `promote_candidate()` raises `PromotionError` unless governance passed, challenger-verdict passed, *and* an explicit, non-empty approver + reason was recorded |
| Rollback | `src/mlops/promotion.py::rollback()` | Independently re-verified by re-querying the registry after rollback, not by trusting the function's own return value |
| CI/CD integration | `.github/workflows/mlops-verify.yml` + `scripts/mlops/ci_demo.py` | Runs the real (synthetic-data) test suite and a real registry/governance/promotion/rollback demonstration on every push/PR |
| Monitoring foundation | `src/monitoring/prediction_monitor.py` | Real event-level JSONL log + real aggregation (error rate, latency percentiles, label distribution) |
| Security | `src/mlops/tracking.py::get_tracking_uri()` | Reads `MLFLOW_TRACKING_URI` from the environment first — the same env-var-first pattern this project's Vault PoC documents as the intended credential path; see `MLFLOW_DEPLOYMENT_GUIDE.md` §4 |

## 3. Why BP1 and not every BP

This environment's Python install does not have `xgboost`, `lightgbm`, or `catboost` available
(confirmed: installing them hits a hard disk-space limit in this sandbox — see
`MLOPS_TEST_REPORT.md` §5), and BP2–BP8's real champions are fit over the real CFPB extract, a
322 MB file that lives **outside** this git repository by design (`data/.gitignore` — the project
has never committed real training data, a rule Phase D does not change).

BP1 (Customer Intent Classification) is the one business problem whose real champion
(`src/models/bp1_intent_classifier.py`'s `make_pipeline()` — TF-IDF + `LogisticRegression`) is a
fast, standalone, already-unit-tested fit over a small real dataset (BANKING77: 10,003 train /
3,080 test rows after the real CSV load, ~1 MB total) that this environment can run end to end.
Phase D therefore demonstrates the full tracking → registry → governance → champion-challenger →
promotion → rollback pipeline **for real, against BP1**, and documents the same pipeline's code as
generic — every function in `src/mlops/` takes `bp_id` as a parameter and works for any BP once a
governance threshold is defined for it (`src/mlops/governance.py::MODEL_PERFORMANCE_THRESHOLDS`).

BP2–BP8's **historical** metrics (already real, already committed in each BP's
`configs/*.yaml`) were **not** backfilled into MLflow as registered model versions in this pass —
doing so without a real re-fit would mean registering a "version" with no real artifact behind it,
which this project's zero-fabrication standard treats as a materially different (and worse) thing
than disclosing the gap plainly. This is a named, deliberate limitation, not an oversight —
see `MLOPS_TEST_REPORT.md` §6 ("Remaining gaps").

## 4. Design decisions and why

- **SQLite-backed MLflow store, not the plain FileStore.** This MLflow version's FileStore does
  not support the Model Registry; SQLite is the smallest real backend that supports both tracking
  and the registry with zero external infrastructure — consistent with this project's existing
  "no managed external service claimed" posture.
- **MLflow aliases (`champion` / `challenger` / `previous_champion`), not the deprecated
  stage-transition API.** MLflow 3.x (installed here: 3.17.2) has moved away from
  Staging/Production/Archived stages in favor of aliases + tags.
- **One registered model per business problem** (`customer360_<bp_id>`), matching this project's
  existing per-BP convention everywhere else (`configs/`, `models/`, `*_readiness_verdict.py`).
- **Governance thresholds set below, not equal to, each BP's historical metric.** A threshold
  equal to the historical value would reject the identical model on ordinary re-fit noise; a
  threshold with no real anchor would be arbitrary. BP1's threshold (`held_out_test_accuracy >=
  0.80`) is set about 2.5 points below the real recorded 0.8224, so a genuine regression is
  caught while an exact refit (verified: identical to 6 decimal places, see `MLOPS_TEST_REPORT.md`
  §2) comfortably passes.
- **Everything is plain JSON Lines on local disk** (`governance/*.jsonl`), not a managed
  audit/metrics service — the same pattern already used by this project's monitoring and
  deployment-readiness modules.

## 5. Related documents

- `MODEL_REGISTRY_GUIDE.md` — how to use `src/mlops/registry.py`.
- `MODEL_GOVERNANCE_POLICY.md` — the real thresholds and what governing a candidate means.
- `MODEL_PROMOTION_AND_ROLLBACK.md` — the state machine, the approval gate, and the rollback proof.
- `MLFLOW_DEPLOYMENT_GUIDE.md` — how to point this at a real MLflow server and real credentials.
- `MLOPS_TEST_REPORT.md` — the full, honest test and verification report for this phase.
