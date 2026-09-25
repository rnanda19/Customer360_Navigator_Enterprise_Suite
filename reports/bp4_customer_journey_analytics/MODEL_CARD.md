# Model Card — BP4 Customer Journey Analytics

*Generated 2026-09-23T15:18:29.558475+00:00 by `bp4_customer_journey_analytics_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP4 Gates 1-5's own real runs on this machine. No field
below was authored freeform or by a generative model (project zero-fabrication rule).*

**A note on this document's name:** BP4 has no supervised target and trains no predictive model - it
is a deterministic aggregation and reporting pipeline over real, already-verified issue-cluster
statistics. "MODEL_CARD.md" is kept as the filename only for naming consistency with the Master
Plan's own literal Gate 6 output list across every BP; every section below documents the real
pipeline (its execution-engine benchmark, its statistical validation, its reporting layer), never a
trained model's architecture, training run, or predictive performance, none of which exists here.

## Pipeline Details
- **Champion aggregation pipeline (Gate 3, real benchmark):** `polars_lazy_streaming` — real min_seconds
  0.103927s, 2.0x-champion slow-candidate threshold
  0.207854s
- **Candidates evaluated (real Gate 3 correctness + timing benchmark, all 5):**

  | candidate | status | min_seconds | mean_seconds | champion |
  |---|---|---|---|---|
  | polars_lazy_streaming | CORRECT | 0.103927 | 0.10541 | YES |
  | polars_eager | CORRECT | 0.108452 | 0.123225 |  |
  | polars_lazy | CORRECT | 0.110692 | 0.118765 |  |
  | duckdb_sql | CORRECT | 0.240335 | 0.256269 |  |
  | pandas_groupby | CORRECT | 3.067079 | 3.362423 |  |

- **Real speedup over the slowest correctness-passing baseline:** 29.5119x
  (3.067079s -> 0.103927s)
- **Journey-grouping key (real, CFPB's own schema, never a fabricated identifier):**
  `Company, Product, Sub-product, Issue, Sub-issue`
- **Barred from every BP4 journey-grouping key (Gate 1 scope decision):**
  `Tags, ZIP code`

## Intended Use
- **Journey definition:** Event/issue journey analytics only - never customer/longitudinal journey analytics (Master Plan Section 5.1/7's own explicit instruction for BP4).
- **Unit 1 (complaint-event journey):** Row-level, keyed by real 'Complaint ID'; 'Date received' -> 'Date sent to company' with a real computed response_lag_days duration.
- **Unit 2 (issue-cluster journey):** Aggregate-level, keyed by real (Company, Product, Sub-product, Issue, Sub-issue); ordered by 'Date received' into a real monthly volume time series per cluster. Optionally overlaid with the Gold-layer 'common_taxonomy_bucket' column for its real 6.55%-of-rows in-scope subset only.
- **Out of scope:** no per-customer or per-consumer journey, cohort, retention, or survival-style
  analysis is buildable or intended — this real extract carries no customer/consumer identifier
  (Gate 1, live-verified).

## Training Data
*Not applicable — BP4 trains no model. The real data this pipeline aggregates:*
- **Source:** real CFPB extract, `data/processed/cfpb_journey_event_gold.parquet`
- **Real journey-event row count (Gate 2):** 1,048,575 (matches raw:
  True)
- **Real issue-cluster count (Gate 2, matches Gate 1: True):**
  37,160 clusters, 15,551 recurring
- **Gate 2 (real run, Gold layer's own file modification time
  2026-09-23T14:05:46.792973+00:00):** issue-cluster-summary Gold
  layer written from this real journey-event population.
- **Feature/aggregation lineage (Gate 2, real):**

  | engineered feature | source column(s) |
  |---|---|
  | response_lag_days | Date received, Date sent to company |
  | complaint_month | Date received |
  | common_taxonomy_bucket, banking77_in_scope | Complaint ID (join key) -> data/processed/cfpb_common_taxonomy_gold.parquet |
  | Sub-product (sentinel-filled, part of CLUSTER_KEY) | Sub-product |
  | Sub-issue (sentinel-filled, part of CLUSTER_KEY) | Sub-issue |
  | State (sentinel-filled, not part of CLUSTER_KEY) | State |
  | (none - barred from every BP4 journey-grouping key) | Tags |
  | (none - barred from every BP4 journey-grouping key) | ZIP code |

## Evaluation Data & Results
- **Statistical validation (Gate 4, real, 1,000-resample bootstrap, 95% CI):**
  - Mean response lag (days): point estimate 0.4652266170755549,
    95% CI [0.457265574708533,
    0.47372591374007583]
  - Recurring-cluster rate: point estimate 0.4184876210979548,
    95% CI [0.4133476856835307,
    0.42333423035522066]
  - Mean cluster size: point estimate 28.217841765339074, 95% CI
    [21.003661867599572, 36.86651305166846]
  - Reproducibility confirmed (Gate 4, real re-run comparison): True
- **Decision/reporting layer (Gate 5, real, 37,160 clusters scored):**
  19,237 clusters carry at least one triggered review flag;
  0 reason-code grounding failures recorded.
- **Real tier rollup (Gate 5):**

  | tier | n_clusters | n_complaint_rows_covered | mean BANKING77 coverage |
  |---|---|---|---|
  | HIGH | 2,284 | 94,410 | 0.3279334500875657 |
  | LOW | 12,033 | 29,630 | 0.23493725587966427 |
  | MEDIUM | 4,920 | 906,612 | 0.2914634146341463 |
  | NONE | 17,923 | 17,923 | 0.20660603693578083 |

- **Row-coverage cross-check:** Gate 5's real tier rollup sums to
  1,048,575 rows, matching Gate 1/2's own real
  journey_row_count (1,048,575):
  True

## Explainability
- **Method:** not applicable in the SHAP/feature-attribution sense (no predictive model). Every Gate
  5 review flag instead carries a grounded, deterministic `reason_codes`/`reason_evidence` pair — the
  real number that triggered each flag (recurring_flag from Gate 2's own is_recurring_cluster;
  elevated_lag_flag from a live comparison against Gate 4's own bootstrap point estimate;
  high_volume_flag from a live-computed 90th percentile of the real cluster population) — never a
  black-box score.

## Ethical Considerations / Compliance Touchpoints
- **CFPB supervisory & complaint-handling standards (Gate 1):** BP4's primary journey-grouping key (Company, Product, Sub-product, Issue, Sub-issue) is CFPB's own real product/issue/sub-issue schema, used as-is, with no fabricated outcomes anywhere. Two real dataset limitations are stated plainly rather than left implicit: (1) no customer/consumer identifier exists in this extract, so every 'repeat-contact' or 'journey' claim in BP4's deliverables is an issue-cluster-level signal, never a per-person claim; (2) the Gold-layer BANKING77-derived taxonomy overlay real-covers only 6.55% of rows, so it is never presented as a population-level view of customer intent across the full real dataset.
- **UDAAP language review (Gate 5):** Not Applicable to BP4 Gate 5 - this gate generates no GenAI or customer-facing text; review_priority_score/tier and reason_codes/reason_evidence are deterministic outputs of a transparent rule evaluated over real, already-confirmed BP4 statistics. Real GenAI-drafted customer-facing text (subject to UDAAP review) is scoped to BP6 per the Master Plan, the same standing scope decision confirmed for BP1/BP2/BP3 Gate 5.
- **NIST AI RMF Measure/Manage (Gate 5):**
  Not Applicable to BP4 Gate 5 for the same reason - no GenAI output is produced here. Applies at BP6.
- **BP7 decision-engine boundary (Gate 5):**
  review_priority_score/tier is a BP4-local reporting flag built only from BP4's own real Gate 2/4 statistics. It is not the cross-BP priority + intervention-risk decision engine Master Plan Section 5.1/7 scopes to BP7 (which combines BP1-BP5 outputs with its own reason codes and thresholds) - this gate's output may become one real input BP7 later combines, but is never presented as BP7's own decision.
- **ECOA/Reg B disparate-impact applicability (Gate 4):**
  NOT_APPLICABLE — ECOA/Reg B is not a BP4 compliance touchpoint
  per Master Plan Section 9 (mapped to BP1, BP2, BP3, BP7 only); `Tags` remains barred from every
  BP4 journey-grouping key anyway, as a conservative scope decision (Gate 1).
- **Model inventory (SR 11-7):** NOT_APPLICABLE — BP4 registers no trained model, only this
  benchmarked, statistically-validated execution/reporting pipeline; there is no
  `model_inventory_entry.json` equivalent for BP4 (see gate6_governance_summary.json instead, which
  folds this Gate's own accumulation of Gates 1-5's real recorded facts).
- **GenAI API used in BP4:** False (scope decision
  confirmed by user 2026-09-22)

## Known Limitations
- No candidate failed Gate 3's correctness benchmark on this real run (all 5 CORRECT).
- **`pandas_groupby`**: real min_seconds 3.067079 is more than 2.0x the champion `polars_lazy_streaming`'s real min_seconds (0.103927, threshold 0.207854) despite passing correctness - not a defect, expected variation across execution-engine designs at this row count; noted here for future re-benchmarking against the full real dataset, where the ranking can shift.
- **`duckdb_sql`**: real min_seconds 0.240335 is more than 2.0x the champion `polars_lazy_streaming`'s real min_seconds (0.103927, threshold 0.207854) despite passing correctness - not a defect, expected variation across execution-engine designs at this row count; noted here for future re-benchmarking against the full real dataset, where the ranking can shift.

## Governance & Testing (this Gate 6 run, 2026-09-23T15:18:29.558475+00:00)
- **pytest suite** (`pytest tests/ -v --tb=short`): '\x1b[33m================ \x1b[32m219 passed\x1b[0m, \x1b[33m\x1b[1m5 skipped\x1b[0m, \x1b[33m\x1b[1m125 warnings\x1b[0m\x1b[33m in 13.58s\x1b[0m\x1b[33m ================\x1b[0m' → parsed as
  {'passed': 219, 'failed': 0, 'skipped': 5, 'errors': 0, 'xfailed': 0, 'xpassed': 0} (exit code 0, all_passed=True). First run
  with real BP4 coverage — `src/features/bp4_journey_features.py` needed no Gate 6 extension (its
  CLUSTER_KEY/BARRED_JOURNEY_COLUMNS/NULL_SENTINEL_MAP were already centralized at Gate 2); 2 new
  test files delivered alongside this notebook
  (`tests/bp4_customer_journey_analytics/test_bp4_journey_features.py`,
  `tests/bp4_customer_journey_analytics/test_gate_artifacts.py`) give it its first-ever coverage.
- **Static notebook audit** (`scripts/check_notebook_syntax.py` — nbformat + ast + pyflakes, static
  only, nothing executed): 34 passed / 0 failed (exit
  code 0, all_passed=True)
- Full logs:
  `notebooks/bp4_customer_journey_analytics/artifacts/gate6_pytest_output.log`,
  `gate6_notebook_syntax_check_output.log`

## Change History
See `CHANGELOG.md` in this same folder.
