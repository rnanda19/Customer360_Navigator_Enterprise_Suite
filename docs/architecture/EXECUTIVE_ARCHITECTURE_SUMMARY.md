# Executive Architecture Summary

One page, for a time-constrained reader. Every box below is real and shipped in this repo; the
[Production Readiness Matrix](../PRODUCTION_READINESS_MATRIX.md) has the per-BP evidence behind each
one, and the dashed pieces are explicitly labeled as synthetic/simulated where they are.

```mermaid
flowchart TB
    subgraph SRC["Source data"]
        CFPB["Real CFPB complaint extract\n(no customer identifier — see BP4)"]
        B77["BANKING77 intent corpus\n(BP1 training data)"]
    end

    subgraph MODEL["Modeling layer — BP1-BP6 (independent FastAPI services, ports 8001-8006)"]
        BP1["BP1 Intent\nLogistic Regression"]
        BP2["BP2 Friction\nXGBoost"]
        BP3["BP3 Escalation\nXGBoost\n(fairness: CONDITIONAL)"]
        BP4["BP4 Journey\nPolars streaming"]
        BP5["BP5 Root-cause\nUnivariate logistic"]
        BP6["BP6 GenAI Resolution\nTaxonomy match"]
    end

    subgraph DECISION["Decision layer — BP7 (FastAPI, port 8007)"]
        BP7["BP7 Decision Engine\ncorrelation-aware weighted rule + LR diagnostic\nfairness: NOT FLAGGED (AIR=0.908)\nPrometheus /metrics — the only live-monitored service"]
    end

    subgraph ACT["Activation layer (FastAPI, port 8010)"]
        ACTS["Simulated CRM / notification / case routing\nevery field prefixed SIMULATED_ — no real system contacted"]
    end

    subgraph GOLD["Executive/reporting layer — BP8 (no service, Gold Parquet + .pbix)"]
        BP8["11 Gold tables → 7-page Power BI report"]
    end

    subgraph IDR["Identity Resolution (disclosed synthetic demo, not wired to real data)"]
        IDRBOX["Deterministic + probabilistic matcher\n14-row fictional 3-source fixture\n→ golden customer_360_id"]
    end

    CFPB --> BP2 & BP3 & BP4 & BP5 & BP6
    B77 --> BP1
    BP2 --> BP7
    BP3 --> BP7
    BP4 --> BP7
    BP7 --> ACTS
    BP1 & BP2 & BP3 & BP4 & BP5 & BP6 & BP7 --> BP8
    IDRBOX -.demonstrates pattern only.-> GOLD

    style IDR stroke-dasharray: 5 5
    style ACT stroke-dasharray: 5 5
```

## What's real vs. what's a disclosed pattern demo

| Layer | Status | Evidence |
|---|---|---|
| BP1–BP7 models, APIs, tests | **Real** — trained, tested, containerized | 1,663 passing tests across BP1-7; see matrix |
| BP7 fairness audit & Prometheus metrics | **Real and live-scored** | `adverse_impact_ratio=0.908127`; real `prometheus_client` instrumentation |
| BP8 Gold layer + `.pbix` | **Real** — 11 Parquet tables, committed 7-page report | [`powerbi/README.md`](../../powerbi/README.md) |
| Activation layer | **Real code, simulated destinations** — routes BP7's real decisions to mock CRM/notification/case adapters | Every response field prefixed `SIMULATED_`; disclosed in module docstring |
| Identity Resolution / Golden Customer Record | **Real code, synthetic fixture** — demonstrates the pattern; never touches real CFPB rows because the real extract has no customer identifier to resolve | [`data/synthetic_identity_demo/README.md`](../../data/synthetic_identity_demo/README.md) |
| Live production deployment (HTTPS front door, auth gateway) | **Not done** — requires a cloud account (Render/similar) this repo cannot create on its own | See `RENDER_DEPLOYMENT.md` |
| Prometheus/Grafana live scraping | **Not done** — nothing is deployed yet for Grafana to scrape; depends on the item above | — |

## Technologies per layer

- **Modeling (BP1-6):** Python, scikit-learn, XGBoost, Polars, SHAP, FastAPI, Docker
- **Decision engine (BP7):** FastAPI, `prometheus_client`, request-rate limiting, request tracing
- **Activation:** FastAPI, SQLite (real event log, simulated destinations)
- **Executive layer (BP8):** Python/Pandas Gold-table builders, Parquet, Power BI Desktop
- **Identity resolution demo:** Python stdlib (`difflib`), union-find, weighted similarity scoring
- **CI/CD:** GitHub Actions — lint/format, pytest, bandit, Docker build+health-check, CodeQL
- **Hosting:** GitHub Pages (dashboards, live today); no application layer is deployed live yet
