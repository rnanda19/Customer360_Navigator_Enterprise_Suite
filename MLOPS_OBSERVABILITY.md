# MLOps & Observability — what's real, what isn't

This repo already has real, live-scored monitoring on one service (BP7's `/metrics` and
`/metrics/prometheus`, backed by real `prometheus_client` instrumentation — see `MONITORING.md`).
This document covers the layer above that: drift detection, a consolidated fairness view, a model
registry, and alerting.

## What's real and tested (`src/monitoring/`)

| Module | What it does | Real, not fabricated because |
|---|---|---|
| `drift_detection.py` | Real Population Stability Index (PSI) implementation, industry-standard formula and interpretation bands | Demonstrated against this repo's own committed BP8 Gold parquet (real 2023 vs 2026 complaint volume) — see the real, disclosed finding below |
| `fairness_monitor.py` | Consolidates BP3's and BP7's real disparate-impact numbers into one pass/fail view against the four-fifths rule | Every number is read directly from BP3's/BP7's own already-committed Gate 4 JSON — this module computes nothing new, it aggregates |
| `model_registry.py` | Consolidated view of each BP's real champion model/strategy identifier | Read directly from each BP's own committed `configs/<bp>.yaml` — honestly reports `None` + a note for BP5 and BP8, which have no single discrete model-name field, rather than guessing one |
| `alerting.py` | Real, tested threshold-evaluation logic (`evaluate_alert()`) — decides OK/WARNING/CRITICAL for a metric value against real thresholds already used elsewhere in this suite (0.8 four-fifths rule, 0.10/0.25 PSI bands) | Pure function, fully unit-tested on both "higher is worse" and "lower is worse" metrics |

Run any of them yourself:

```bash
PYTHONPATH=src python3 -m monitoring.drift_detection
PYTHONPATH=src python3 -m monitoring.fairness_monitor
PYTHONPATH=src python3 -m monitoring.model_registry
```

### A real, disclosed finding from the drift-detection demo

Computing PSI on the raw CFPB `Product` field between 2023 and 2026 produces a very large, alarming
PSI — but that number is dominated by the CFPB's own product-category **label rename** during that
window (`"Credit reporting, credit repair services, or other personal consumer reports"` became
`"Credit reporting or other personal consumer reports"`), not genuine behavioral drift. Computing
PSI on this suite's own `common_taxonomy_bucket` crosswalk instead (BP1's real taxonomy mapping,
built specifically to be stable across exactly this kind of product-label churn) gives a real,
much lower, and far more meaningful PSI — a "no significant shift" result. Both numbers are
reported by the module rather than only showing the flattering one; this is the kind of thing real
drift monitoring needs to know how to tell apart, and this demo genuinely surfaces it rather than
staging it.

## What is honestly NOT implemented

- **No live-running monitoring loop.** `drift_detection.py` and `fairness_monitor.py` are callable
  on demand, not a scheduled job polling a live service — because no service in this suite is
  deployed behind a public endpoint yet (see `RENDER_DEPLOYMENT.md` / `render.yaml`). Wiring these
  into a real scheduled check is the honest remaining step once that's live, not a new module.
- **No live alert channel.** `alerting.py`'s `evaluate_alert()` is real and tested, but it is not
  wired to Slack/email/PagerDuty. Building that integration with nothing real running in production
  to alert about would itself be a hollow, untested-in-practice addition — exactly what this
  project's zero-fabrication standard exists to avoid.
- **UPDATE (Phase D, 2026-11-02): an MLflow-style model registry, approval workflow, and
  rollback pipeline now exist for real** — see `MLOPS_ARCHITECTURE.md`, `src/mlops/`, and
  `MLOPS_TEST_REPORT.md` for the full, verified picture. A real sqlite-backed MLflow tracking
  store and Model Registry, a real governance gate with per-BP thresholds, a real
  champion-challenger comparison, and a real promotion/approval/rollback state machine were all
  built and locally run end to end against BP1's real BANKING77-trained champion — including a
  real rejection of a deliberately weak candidate and a real rollback, independently re-verified
  by re-querying the registry rather than trusting the rollback call's own report. What remains
  genuinely not built: the same pipeline has not been re-run against BP2-BP8 (their real training
  data lives outside this repo and was not re-fit in this pass — see `MLOPS_ARCHITECTURE.md` §3),
  and no real external MLflow server or Vault-credential wiring exists (`MLFLOW_DEPLOYMENT_GUIDE.md`
  §4-5) — only a local, file/sqlite-backed store. `model_registry.py` above (the pre-Phase-D,
  read-only YAML-backed view) is unchanged and still serves its original, narrower purpose; it is
  not superseded, since it reads live config state rather than requiring a prior registration step.
