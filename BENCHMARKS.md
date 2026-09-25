# Benchmarks

Real numbers only — no illustrative or assumption-based timings anywhere in this file.

## Build hardware (`00_hardware_benchmark`, real-run confirmed)
8 physical / 16 logical threads, 31.29 GB RAM. Recommended and used throughout: `n_jobs=16`,
`cv_mode=parallel`. WARP discipline caps utilization at ~92% of CPU/RAM (never 100% — a real incident on
an earlier project in this lineage hung the machine at full utilization).

## BP3 Gate 3 — 5-model classifier benchmark (real CV wall-clock)
| Model | Mean CV PR-AUC | Wall-clock (5-fold CV) |
|---|---|---|
| logistic_regression (baseline) | 0.0425 | fast |
| random_forest | 0.2710 | 325.27s — genuinely slow even on this hardware |
| hist_gradient_boosting | 0.3449 | moderate |
| **xgboost (champion)** | **0.3467** | **13.16s** |
| lightgbm | 0.3459 | 13.10s |

## BP4 Gate 3 — aggregation-pipeline benchmark (real wall-clock, full 1,048,575-row dataset)
| Candidate | Wall-clock |
|---|---|
| pandas_groupby (baseline) | 3.067079s |
| polars_eager | 0.108452s |
| polars_lazy (previous production) | 0.110692s |
| **polars_lazy_streaming (champion)** | **0.103927s** |
| duckdb_sql | 0.240335s — real and genuinely slower than every Polars candidate |

**Real speedup, champion vs. baseline: ~29.5x** (3.067079s → 0.103927s).

## BP7 — full-population decision scoring
1,048,575 rows scored end to end, deterministic weighted-rule engine, no external call. Serving-side
latency has not been separately load-tested (see `ROADMAP.md` — live deployment is not yet in scope).

## Test suite
1,000+ tests across `tests/` (mirrors `src/` 1:1: features, models, reporting, services, deployment,
shared). Run with `pytest tests/ -v`. CI runs the same suite on every push.
