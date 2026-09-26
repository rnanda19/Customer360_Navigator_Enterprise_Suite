# Production Readiness Matrix

Every cell below is grounded in a real, re-checked artifact in this repo as of this commit — pytest
counts were re-run live (`pytest tests/<bp>/... -q`) or read from each BP's own
`gate6_pytest_output.log`; model/tier/fairness values are read from each BP's `configs/<bp>.yaml`
Gate 3/4/5 blocks and `notebooks/<bp>/artifacts/gate*.json`; port and Docker facts are read from
`src/services/docker/<bp>_*/docker-compose.yml`. Nothing here is estimated or carried over from an
earlier draft without being re-verified against the file that actually produced it.

| BP | Model | Validation | Fairness | Explainability | API | Docker | Tests | Monitoring | Production Tier |
|---|---|---|---|---|---|---|---|---|---|
| **BP1** — Customer Intent Classification | Logistic Regression (champion of 6 candidates, Gate 3 CV benchmark) | Gate 4 statistical validation on BANKING77's own held-out test split (`gate4_statistical_validation.json`) | Structurally no check — BANKING77 carries no protected-class field to test | SHAP top features (`gate4_shap_top_features.csv`) | Yes — FastAPI, port **8001** | Yes | **52 passed** | No | Recommended for Production |
| **BP2** — Customer Friction Classification | XGBoost (champion, Gate 3 CV benchmark) | Gate 4 statistical validation (`gate4_statistical_validation.json`) | Structurally no check (same feature set shape as BP1) | SHAP top features | Yes — FastAPI, port **8002** | Yes | **105 passed, 1 skipped** | No | Recommended for Production |
| **BP3** — Complaint Escalation Prediction | XGBoost (champion, Gate 3 CV benchmark) | Gate 4 statistical validation + calibration curve + threshold analysis | **FLAGGED** — disparate-impact ratio **0.139** on the `Tags` field, below the four-fifths-rule convention (`gate4_disparate_impact_check.csv`) | SHAP top features | Yes — FastAPI, port **8003** | Yes | **189 passed, 4 skipped** | No | **CONDITIONAL — Governance Review Required** |
| **BP4** — Customer Journey Analytics | Polars lazy-streaming pipeline (event/issue-cluster analytics — not a trained classifier; no customer identifier exists in the real CFPB extract to classify against) | Gate 3 correctness + performance benchmark across 4 pandas/polars candidates, all independently verified `CORRECT` (`gate3_benchmark_results.csv`) | Structurally no check — no classifier decision exists to test | Not applicable (not a predictive model) | Yes — FastAPI, port **8004** | Yes | **219 passed, 5 skipped** | No | Recommended for Production |
| **BP5** — Root-Cause & Driver Analytics | Univariate logistic regression (association-strength reporting tool, not a deployed classifier) | Gate 4 bootstrap confidence intervals + calibration curve + confusion matrix | Not applicable — association/reporting output, no automated decision is made on a person | SHAP top features, per outcome (2 outcomes) | Yes — FastAPI, port **8005** | Yes | **325 passed, 3 skipped** | No | Recommended for Decision-Support Use With Monitoring |
| **BP6** — GenAI Resolution Assistant | Taxonomy bucket match (retrieval/rules-based; no trained classifier) | Gate 4 explainability trace + independent validation record (`gate4_independent_validation_record.json`) | Not applicable — retrieval/template output, no automated adverse decision | Explainability trace (`gate4_explainability_trace.json`) | Yes — FastAPI, port **8006** | Yes | **363 passed, 6 skipped** | No | Recommended for Production |
| **BP7** — Customer Navigator Decision Engine | Correlation-aware weighted rule + LR diagnostic, combining BP2/BP3/BP4 outputs | Gate 4 bootstrap CI + reproduction check + leakage reconfirmation + statistical-validation/explainability summary | **NOT FLAGGED** — `adverse_impact_ratio = 0.908127`, above the 0.8 four-fifths threshold (`gate4_disparate_impact_audit.json`) | Contribution decomposition — per-upstream-model weight breakdown for every decision | Yes — FastAPI, port **8007**, versioned + rate-limited + batch endpoints | Yes | **410 passed, 3 skipped** | **Yes — real `prometheus_client` instrumentation, `/metrics` + `/metrics/prometheus`** (the only BP with live metrics) | Recommended for Production |
| **BP8** — Executive/Product Analytics (Power BI Gold Layer) | Not applicable — Gold-layer aggregation only; explicitly never treated as a ninth modeling problem | Gate 2/3 manifest structural checks (row counts, schema, upstream-file-untouched verification) | Not applicable — no automated decision is made | Not applicable | No — Parquet + `.pbix` artifact only, no live service (explicit scope decision) | No | **30 passed** (re-run live: `pytest tests/bp8_executive_product_analytics/ -q`) | No | Not applicable (reporting layer) |

## Two cross-cutting layers (added on top of BP1–8, not a ninth modeling problem)

| Layer | What it is | Validation | Fairness | API | Docker | Tests | Monitoring | Status |
|---|---|---|---|---|---|---|---|---|
| **Identity Resolution** (`src/identity_resolution/`) | Deterministic + probabilistic entity resolution over a **disclosed synthetic** 14-row, 3-source fixture — demonstrates the golden-record pattern this architecture needs; never run against real CFPB data | 11 pytest cases including a deliberate near-miss pair proven to *not* merge | Not applicable — synthetic demo, not a production decision | No — CLI only (`python -m identity_resolution.run_demo`) | No | **11 passed** | No | Synthetic pattern demonstration, clearly disclosed |
| **Activation Layer** (`src/services/bp_activation_service.py`) | Routes BP7's 3 real `recommended_action` values to simulated CRM / notification / case-management channels | Verified against BP7's real policy mapping | Not applicable — routing layer, inherits BP7's fairness result | Yes — FastAPI, port **8010** | Yes | **9 passed** | No | Simulated adapters only — every response field prefixed `SIMULATED_`; disclosed as such, no real banking-system integration claimed |

## Honest gaps this table makes visible

- **Monitoring is real on exactly one service (BP7).** BP1–6, BP8, Identity Resolution, and the
  Activation Layer have no live metrics scraping. Phase 5 (Prometheus/Grafana) below explains why
  this isn't extended further without a deployed target to scrape.
- **BP3 is the only BP whose own governance status is CONDITIONAL.** Its disparate-impact finding on
  the `Tags` field is real, recomputed independently at both Gate 4 and Gate 5, and deliberately
  left unresolved rather than hidden — it is disclosed here exactly as the dashboard discloses it.
- **BP8 has no API, no Docker image, and no monitoring by design**, not by omission — it is a
  Python-built Gold/semantic layer feeding a `.pbix`, never a served model.
