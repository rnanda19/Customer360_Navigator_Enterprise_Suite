# CHANGELOG — BP4 Customer Journey Analytics

All dates below are real UTC timestamps read live from each gate's own recorded artifact at the
moment this Gate 6 notebook was run (2026-09-23T15:18:29.558475+00:00) — not typed in from memory.

## [Gate 6] Productization, Monitoring & Governance — 2026-09-23T15:18:29.558475+00:00
- pytest suite: 219 passed, 0 failed,
  5 skipped, 0 errors (224 total) - first
  run with real BP4 coverage (2 new test files; no shared-module extension was needed)
- Static notebook-syntax audit: 34/34 notebooks passed
- MODEL_CARD.md and this CHANGELOG.md generated deterministically from Gates 1-5's real recorded artifacts (MODEL_CARD.md reframed for a deterministic pipeline, not a trained model - BP4 has none)
- `gate6_governance` block written to `configs/bp4_customer_journey_analytics.yaml`; config `status`
  set to `"gate6_complete"`
- Open items detected live this run: 0 failed candidates,
  2 slow-but-correct candidates (>2.0x champion)

## [Gate 5] Decision Layer & Reporting — 2026-09-23T15:00:20.192069+00:00
- 37,160 real clusters scored; 19,237 with
  at least one triggered review flag (0 grounding failures)
- Real tier rollup: HIGH=2,284, LOW=12,033, MEDIUM=4,920, NONE=17,923
- Row-coverage sum matches Gate 1's real journey_row_count:
  True
- No GenAI API call (scope decision confirmed by user
  2026-09-22)

## [Gate 4] Statistical Validation — real bootstrap CIs recorded in
`configs/bp4_customer_journey_analytics.yaml`
- Mean response lag (days): 0.4652266170755549 95% CI
  [0.457265574708533, 0.47372591374007583]
- Recurring-cluster rate: 0.4184876210979548 95% CI
  [0.4133476856835307, 0.42333423035522066]
- Reproducibility confirmed: True | ECOA/Reg B applicability:
  NOT_APPLICABLE

## [Gate 3] Aggregation-Pipeline Benchmark & Champion Selection
- Champion: `polars_lazy_streaming` (real min_seconds 0.103927s, real speedup
  29.5119x over the slowest correctness-passing baseline)
- Candidates evaluated: 5; failed: 0
- Open items detected live this run from `gate3_benchmark_results.csv`: 0
  failed, 2 slow-but-correct (see MODEL_CARD.md Known Limitations)

## [Gate 2] Data Verification & Feature/Taxonomy Engineering — 2026-09-23T14:05:46.792973+00:00
(file modification time of the issue-cluster-summary Gold layer; Gate 2 does not record its own JSON
timestamp)
- Real journey_row_count: 1,048,575 (matches raw:
  True)
- Real n_clusters: 37,160 (15,551 recurring;
  matches Gate 1: True)

## [Gate 1] Business Understanding & Policy — 2026-09-23T13:53:52.050197+00:00
- Journey definition: Event/issue journey analytics only - never customer/longitudinal journey analytics (Master Plan Section 5.1/7's own explicit instruction for BP4).
- Live-verified: 1,048,575 real CFPB rows,
  1,048,575 unique Complaint IDs (event-key uniqueness
  confirmed: True)
