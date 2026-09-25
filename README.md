# Customer360 Navigator Enterprise Suite

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Status](https://img.shields.io/badge/8%2F8%20business%20problems-real--run%20confirmed-brightgreen.svg)
![Execution boundary](https://img.shields.io/badge/execution-owner--run%20only-informational.svg)

Enterprise AI-driven customer complaint, friction, and journey intelligence platform built on the CFPB
Consumer Complaint Database (1,048,575 rows) and Banking77 (13,083 rows). Independent professional
portfolio project. Not affiliated with Capital One or any financial institution.

## Leading with the fairness finding

The suite's decision layer (BP7) runs a live ECOA/Regulation B disparate-impact audit against its own
full-population output — not a one-off check, a re-derivation on every run, cross-checked against an
earlier gate's own independently-computed number. On the most recent real run: **adverse impact ratio
0.908127**, against the EEOC four-fifths-rule floor of 0.80 — the audit does **not** flag the model.
Lowest-selection-rate group: Servicemember. Highest: Older American. This isn't a claim of legal
compliance (the pipeline says so explicitly, in its own output) — it's a monitoring signal a human
reviewer can act on, computed the same honest way every time.

That audit exists because BP3 (Complaint Escalation Prediction), the first model upstream to touch a
protected-class-adjacent field, surfaced a real disparate-impact question early, and every model built
after it — BP4, BP5, BP7 — inherited the same check rather than dropping it once the initial finding was
resolved.

## What's actually in here

Eight business problems, each with its own real trained model or rule layer, each gated through the same
6-stage governance cycle (Business Understanding -> Data/Feature Verification -> Model/Rule Benchmark ->
Statistical Validation & Explainability -> Decision Layer & Reporting -> Productization/Monitoring/
Governance), each closing with an executive rollup (dashboard + report + workbook + deck) built from its
own real, live-computed numbers — never a template with numbers dropped in.

| BP | What it does | Real status |
|----|---------------|-------------|
| BP1 | Customer intent classification (77-class Banking77 + CFPB taxonomy) | Closed. Champion: logistic regression, test accuracy 0.8224, ROC-AUC (OVR macro) 0.9933 |
| BP2 | Customer friction severity classification | Closed. Champion: XGBoost, test accuracy 0.7558, ROC-AUC (OVR macro) 0.8857 |
| BP3 | Complaint escalation / intervention prediction | Closed. Champion: XGBoost. ECOA/Reg B disparate-impact check introduced here (first model in the suite to carry one) |
| BP4 | Customer journey / cluster analytics | Closed. Recommended for production |
| BP5 | Root-cause & driver analytics (association, not causation) | Closed. Recommended for decision-support use, with monitoring |
| BP6 | GenAI resolution assistant (retrieval-grounded, human-in-the-loop) | Closed. Recommended for production; every generated recommendation routes to human review before use |
| BP7 | Decision engine — transparent, deterministic weighted-rule triage layer over BP2/BP3/BP4 | Closed. Recommended for production. Adverse impact ratio 0.908127, not flagged |
| BP8 | Cross-BP executive/product Power BI Gold-layer aggregation | Closed. 3 gates real-run confirmed, 11 real Gold Parquet tables written; the interactive `.pbix` is a human Power BI Desktop step, deliberately never a notebook deliverable |

A suite-wide executive rollup (`notebooks/00_suite_executive_rollup/`) consolidates all eight BPs' own real
findings into one dashboard/report/workbook/deck, cross-checking each BP's own recorded production tier
against its own artifact files rather than re-asserting it. Real-run confirmed: 5 of 8 BPs land at
RECOMMENDED FOR PRODUCTION, 1 at CONDITIONAL - GOVERNANCE REVIEW REQUIRED (BP3, disclosed above), 1 at
Recommended for Decision-Support Use With Monitoring (BP5); BP8 has no production-tier concept of its own
(a Gold-layer build, not a decision model).

## Two things worth being upfront about

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

## Structure

`notebooks/` — one folder per BP, one notebook per gate. `src/{taxonomy,features,models,reporting,utils}` —
the shared component library, imported from BP1 onward. `configs/` — per-BP YAML, gate results appended as
marker-delimited blocks. `reports/` — MODEL_CARD.md, CHANGELOG.md, and each BP's executive rollup.
`powerbi/gold_tables/` — BP8's Python-built Gold/semantic layer (the interactive `.pbix` itself is a human,
Power BI Desktop step — never a notebook deliverable). `docs/evidence_ledger/EVIDENCE_LEDGER.md` — the
append-only record of every real run. Every `notebooks/<bp>/README.md` and `reports/<bp>/README.md` carries
that BP's own real champion metric, gate status, and production tier — not a generic template.

## Reproducing this locally

```bash
python -m pip install -e .          # editable install of src/ (setuptools src-layout)
python -m pip install -r requirements.txt
jupyter lab                          # or notebook — run notebooks in gate order, G1 through G6/G7
```

Each notebook resolves its own project root (env override, else a bounded upward walk for a directory
containing both `configs/` and `src/`) rather than assuming a fixed path. `pytest tests/ -v` runs the full
suite (1,000+ tests across BP1-8, services, and deployment-readiness modules). Docker Compose files for each
BP's inference/decision service live under `src/services/docker/`.

## Execution boundary (standing rule, disclosed on purpose)

Every notebook here is generated by an AI assistant (Claude) but **executed only by the project owner, on
their own machine**. No claim in this repository's reports comes from a simulated or assistant-run
pipeline — every metric, chart, and verdict is produced by a real run the owner triggered and independently
verified, logged in the Evidence Ledger with file hashes. This boundary is enforced as a standing rule, not
an informal habit.

## Methodology lineage

AMEX RiskIQ Enterprise Credit Risk Platform -> Home Credit RiskIQ 5-Mega-Project Suite -> Customer360
Navigator (this project). Standing rules carried across all three: zero-fabrication, the execution
boundary above, WARP (runtime performance discipline), the 6-gate governance cycle, and the Evidence
Ledger.
