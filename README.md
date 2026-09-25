<div align="center">

# 🧭 Customer360 Navigator
### Enterprise Complaint, Friction & Journey Intelligence Suite

**Eight real business problems. One shared CFPB dataset. Zero fabricated numbers — including the one time the fairness audit didn't come back clean.**

[![CI](https://github.com/rnanda19/Customer360_Navigator_Enterprise_Suite/actions/workflows/ci.yml/badge.svg)](https://github.com/rnanda19/Customer360_Navigator_Enterprise_Suite/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](requirements.txt)
[![License: MIT](https://img.shields.io/badge/license-MIT-informational)](LICENSE)
[![Zero Fabrication](https://img.shields.io/badge/policy-zero--fabrication-blueviolet)](#execution-boundary-standing-rule-disclosed-on-purpose)
[![Business problems](https://img.shields.io/badge/business%20problems-8%2F8%20real--run%20confirmed-success)](#business-problems)

**[⚡ Why it's different](#why-this-repo-is-different)** · **[📊 Real headline results](#at-a-glance)** · **[⚠️ The fairness finding](#leading-with-the-fairness-finding)** · **[🧭 Business problems](#business-problems)** · **[🗂️ Structure](#structure)** · **[🚀 Quickstart](#reproducing-this-locally)** · **[📌 What this is / isn't](#execution-boundary-standing-rule-disclosed-on-purpose)**

</div>

<br>

Enterprise AI-driven customer complaint, friction, and journey intelligence platform built on the real CFPB
Consumer Complaint Database (1,048,575 rows) and Banking77 (13,083 rows). Independent professional
portfolio project. Not affiliated with Capital One, PolyAI, or any financial institution.

<br>

## Why this repo is different

Most complaint-analytics portfolios stop at a confusion matrix and a clean-looking accuracy number. This one doesn't.

**A real fairness finding is disclosed, not buried.** BP3's complaint-escalation model came back with a real disparate-impact ratio of 0.139 on a protected-class-adjacent field — flagged against the regulatory four-fifths-rule floor of 0.80. Two rounds of fairness-aware retraining were built, real-run, and **rejected** because the real evidence showed they cost accuracy without closing the gap. The original model ships unchanged, the finding ships in the README, not hidden in an appendix.

**Every "real-run confirmed" claim is independently re-verified, not self-reported.** Every gate result in this repo was cross-checked against the actual on-disk artifact file (hash-verified) or the owner's own pasted console output before being called real — the same discipline applied to every one of the 8 business problems, not just the headline ones.

**No GenAI output is ever auto-applied.** BP6's resolution assistant makes a real, grounded call to Google Gemini, cites its real evidence IDs — and every single recommendation routes to `PENDING_HUMAN_REVIEW` before use. There is no code path that skips the human.

**The deployment-readiness verdict audits the filesystem, not a status flag.** Each business problem's `*_readiness_verdict.py` module recomputes SHA-256 hashes, reloads the persisted model, and re-runs the test suite as a subprocess — it never trusts a config file's own claim that something is done.

<br>

## At a glance

| Business problem | Champion / method | Headline metric | Status |
|---|---|---|---|
| BP1 — Customer Intent Classification | Logistic regression (77-class) | Accuracy **0.8224**, ROC-AUC **0.9933** | MEASURED — RECOMMENDED FOR PRODUCTION |
| BP2 — Customer Friction Classification | XGBoost | F1-macro **0.4559** (152:1 real class imbalance) | MEASURED — RECOMMENDED FOR PRODUCTION |
| BP3 — Complaint Escalation Prediction | XGBoost | PR-AUC **0.3496**, recall **0.9424** | MEASURED — CONDITIONAL, disparate-impact disclosed |
| BP4 — Customer Journey / Cluster Analytics | Polars/DuckDB lazy pipeline | **29.5x** speedup, 37,160 real clusters | MEASURED — RECOMMENDED FOR PRODUCTION |
| BP5 — Root-Cause & Driver Analytics | Association study (Cramér's V, log-odds) | Association-only, never causal | MEASURED — Decision-support, with monitoring |
| BP6 — GenAI Resolution Assistant | Retrieval + Gemini-grounded generation | Retrieval coverage **0.333**, 0 PII flagged | MEASURED — RECOMMENDED FOR PRODUCTION, human-gated |
| BP7 — Customer Navigator Decision Engine | Deterministic weighted-rule engine | Adverse impact ratio **0.908** (not flagged) | MEASURED — RECOMMENDED FOR PRODUCTION |
| BP8 — Executive/Product Analytics | Power BI Gold-layer aggregation | **11** real Gold Parquet tables | MEASURED — build complete, all 3 gates confirmed |

Suite-wide: **1,048,575** real CFPB rows, **13,083** real Banking77 rows, **1,000+** tests across the suite, **0** fabricated figures. Full detail, per BP, in `notebooks/<bp>/README.md` and `reports/<bp>/README.md`.

<br>

## Leading with the fairness finding

The suite's decision layer (BP7) runs a live ECOA/Regulation B disparate-impact audit against its own
full-population output — not a one-off check, a re-derivation on every run, cross-checked against an
earlier gate's own independently-computed number. On the most recent real run: **adverse impact ratio
0.908127**, against the EEOC four-fifths-rule floor of 0.80 — the audit does **not** flag the model.
Lowest-selection-rate group: Servicemember. Highest: Older American. This isn't a claim of legal
compliance (the pipeline says so explicitly, in its own output) — it's a monitoring signal a human
reviewer can act on, computed the same honest way every time.

That audit exists because BP3 (Complaint Escalation Prediction), the first model upstream to touch a
protected-class-adjacent field, surfaced a real disparate-impact question early (ratio 0.139, flagged),
and every model built after it — BP4, BP5, BP7 — inherited the same check rather than dropping it once
the initial finding was resolved. BP3's own finding was investigated, not patched over: a proxy-feature
audit found no single trained feature explains it, and two fairness-aware retraining candidates were
built, real-run, and rejected on real evidence before the original model was confirmed as final. Full
investigation trail in `notebooks/bp3_complaint_escalation_prediction/README.md`.

<br>

## Business problems

Eight business problems, each with its own real trained model or rule layer, each gated through the same
6-stage governance cycle (Business Understanding → Data/Feature Verification → Model/Rule Benchmark →
Statistical Validation & Explainability → Decision Layer & Reporting → Productization/Monitoring/
Governance), each closing with an executive rollup (dashboard + report + workbook + deck) built from its
own real, live-computed numbers — never a template with numbers dropped in.

<details>
<summary><b>BP1 — Customer Intent Classification</b> (click to expand)</summary>

77-class Banking77 intent taxonomy, TF-IDF text features. Champion: logistic regression. Held-out test
accuracy **0.8224**, F1-macro **0.8221**, ROC-AUC (OVR macro) **0.9933**. All 6 gates + executive rollup
real-run confirmed. Details: [`notebooks/bp1_customer_intent_classification/README.md`](notebooks/bp1_customer_intent_classification/README.md).
</details>

<details>
<summary><b>BP2 — Customer Friction Classification</b> (click to expand)</summary>

4-class ordinal friction severity from structured CFPB fields. Champion: XGBoost, under a real 152:1 class
imbalance. Held-out F1-macro **0.4559**, accuracy **0.755773**. All 6 gates + executive rollup real-run
confirmed. Details: [`notebooks/bp2_customer_friction_classification/README.md`](notebooks/bp2_customer_friction_classification/README.md).
</details>

<details>
<summary><b>BP3 — Complaint Escalation / Intervention Prediction</b> (click to expand)</summary>

Binary intervention prediction. Champion: XGBoost. Held-out PR-AUC **0.3496**, recall **0.9424**. First BP
to carry a live ECOA/Reg B disparate-impact check — real finding (ratio 0.139, flagged), fully
investigated (proxy-feature audit + 2 fairness-aware retraining candidates, both real-run and rejected on
the evidence), final governance decision: accept and disclose. Details:
[`notebooks/bp3_complaint_escalation_prediction/README.md`](notebooks/bp3_complaint_escalation_prediction/README.md).
</details>

<details>
<summary><b>BP4 — Customer Journey / Issue-Cluster Analytics</b> (click to expand)</summary>

No customer identifier exists in the real CFPB schema, so this is explicitly event/issue journey
analytics, never invented longitudinal customer journeys. Champion aggregation engine: Polars
`lazy_streaming`, **29.5x** speedup over a pandas baseline. 37,160 real issue clusters, 41.85% recurring.
Details: [`notebooks/bp4_customer_journey_analytics/README.md`](notebooks/bp4_customer_journey_analytics/README.md).
</details>

<details>
<summary><b>BP5 — Root-Cause & Driver Analytics</b> (click to expand)</summary>

Association-only, never causal — every output is a disclosed statistical association (Cramér's V,
chi-square, closed-form log-odds ratio + Wald CI), cross-checked against `statsmodels`. Two real outcomes
studied. Details: [`notebooks/bp5_root_cause_driver_analytics/README.md`](notebooks/bp5_root_cause_driver_analytics/README.md).
</details>

<details>
<summary><b>BP6 — GenAI Resolution Assistant</b> (click to expand)</summary>

Retrieval-grounded generation over Banking77's real narrative text, with a live call to Google Gemini.
Every recommendation cites real evidence IDs and routes to `PENDING_HUMAN_REVIEW` before use — no
auto-apply code path exists. Details: [`notebooks/bp6_genai_resolution_assistant/README.md`](notebooks/bp6_genai_resolution_assistant/README.md).
</details>

<details>
<summary><b>BP7 — Customer Navigator Decision Engine</b> (click to expand)</summary>

Deterministic, transparent weighted-rule triage layer over BP2/BP3/BP4 — no trained classifier, no GenAI
call. Full-population real scoring (1,048,575 rows). Adverse impact ratio **0.908127** — passes the
four-fifths floor. Details: [`notebooks/bp7_customer_navigator_decision_engine/README.md`](notebooks/bp7_customer_navigator_decision_engine/README.md).
</details>

<details>
<summary><b>BP8 — Executive/Product Analytics (Power BI Gold Layer)</b> (click to expand)</summary>

Aggregates Gold-layer outputs from BP1-7 into 11 real Power BI-ready Gold Parquet tables. No predictive
target, no classifier, no GenAI call — never treated as a ninth modeling problem. The interactive `.pbix`
is an explicit human, Power BI Desktop step. Details: [`notebooks/bp8_executive_product_analytics/README.md`](notebooks/bp8_executive_product_analytics/README.md).
</details>

A suite-wide executive rollup (`notebooks/00_suite_executive_rollup/`) consolidates all eight BPs' own real
findings into one dashboard/report/workbook/deck, cross-checking each BP's own recorded production tier
against its own artifact files rather than re-asserting it. Real-run confirmed: 5 of 8 BPs land at
RECOMMENDED FOR PRODUCTION, 1 at CONDITIONAL - GOVERNANCE REVIEW REQUIRED (BP3, disclosed above), 1 at
Recommended for Decision-Support Use With Monitoring (BP5); BP8 has no production-tier concept of its own
(a Gold-layer build, not a decision model).

<br>

## Two more things worth being upfront about

**BP7's flag rate.** The decision engine's `intervention_flag_rate` is 76.8% of the full population. That
number needs context, not a defense: `recommended_action` isn't binary. 75.2% of the population lands in
`ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER` — routing to an automated recurring-cluster root-cause
process, not a per-complaint manual review — and only 1.6% lands in `PRIORITY_QUEUE_REVIEW`, the tier that
actually implies individual human attention. The flag rate is a direct, transparent function of a
data-driven champion weighting scheme (BP4's cluster-tier signal carries 60.65% of the combined score) and
a flat 0.5 threshold on that combined score — every number in that sentence is reproducible from the
pipeline's own output, not tuned after the fact to look good.

**A definitional overlap, not leakage.** A correlation check between BP2's and BP3's predictions on the
full population found a 1.0 escalation-positive rate inside BP2's `LOW_FRICTION` class (2,331 of 1,048,575
rows). That is not a leak: `LOW_FRICTION` and BP3's positive class are both defined on the identical real
CFPB outcome value ("Closed with monetary relief") for that subset — the two labels are tautologically the
same event for those specific rows, not a model finding a shortcut. This was named as an open question in
the decision engine's own Gate 1 planning document, quantified live at Gate 3 (Cramer's V 0.214 overall —
weak), and the resulting redundancy is already discounted in how the champion combines BP2 and BP3, rather
than being silently double-counted.

<br>

## Structure

`notebooks/` — one folder per BP, one notebook per gate, each with a real README. `src/{taxonomy,features,
models,reporting,services,deployment,genai,utils}` — the shared component library, imported from BP1
onward. `configs/` — per-BP YAML, gate results appended as marker-delimited blocks. `reports/` —
MODEL_CARD.md, CHANGELOG.md, and each BP's executive rollup (dashboard/report/workbook/deck).
`powerbi/gold_tables/` — BP8's Python-built Gold/semantic layer (the interactive `.pbix` itself is a
human, Power BI Desktop step — never a notebook deliverable). `tests/` — 1,000+ tests, mirroring `src/`
1:1. `docs/` — architecture notes, BRD/FRD, data dictionary, and `evidence_ledger/EVIDENCE_LEDGER.md`,
the append-only record of every real run. `scripts/` — the notebook-syntax and structural-check tooling
every gate uses. `.github/workflows/ci.yml` — lint, security (bandit), pytest, notebook-syntax, and
Docker-compose-validate, generic across all 8 BPs.

<br>

## Reproducing this locally

```bash
python -m pip install -e .          # editable install of src/ (setuptools src-layout)
python -m pip install -r requirements.txt
jupyter lab                          # or notebook — run notebooks in gate order, G1 through G6/G7
```

Each notebook resolves its own project root (env override, else a bounded upward walk for a directory
containing both `configs/` and `src/`) rather than assuming a fixed path. `pytest tests/ -v` runs the full
suite (1,000+ tests across BP1-8, services, and deployment-readiness modules). Docker Compose files for
each BP's inference/decision service live under `src/services/docker/` — built and validated in CI, never
run behind a live public endpoint (see [Execution boundary](#execution-boundary-standing-rule-disclosed-on-purpose)
below).

<br>

## Execution boundary (standing rule, disclosed on purpose)

Every notebook here is generated by an AI assistant (Claude) but **executed only by the project owner, on
their own machine**. No claim in this repository's reports comes from a simulated or assistant-run
pipeline — every metric, chart, and verdict is produced by a real run the owner triggered and independently
verified, logged in the Evidence Ledger with file hashes. This boundary is enforced as a standing rule, not
an informal habit.

This also isn't a live production deployment. Every BP's FastAPI service (BP1-7) is real, Dockerized, and
covered by real tests (including end-to-end `TestClient` runs against the actual persisted model bundle),
and every Docker Compose file is CI-validated — but none of them has ever been run behind a live public
endpoint. That's an honest, disclosed gap, not an implied claim.

<br>

## Methodology lineage

AMEX RiskIQ Enterprise Credit Risk Platform → Home Credit RiskIQ Enterprise Suite → Customer360
Navigator (this project). Standing rules carried across all three: zero-fabrication, the execution
boundary above, WARP (runtime performance discipline), the 6-gate governance cycle, and the Evidence
Ledger. See `ROADMAP.md` for the build history and `BENCHMARKS.md` for real hardware/runtime numbers.
</content>
