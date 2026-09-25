# CHANGELOG — BP1 Customer Intent Classification

All dates below are real UTC timestamps read live from each gate's own recorded artifact at the
moment this Gate 6 notebook was run (2026-09-22T06:25:18.547134+00:00) — not typed in from memory.

## [Gate 6] Productization, Monitoring & Governance — 2026-09-22T06:25:18.547134+00:00
- pytest suite: 52 passed, 0 failed,
  0 skipped, 0 errors (52 total)
- Static notebook-syntax audit: 8/8 notebooks passed
- MODEL_CARD.md and this CHANGELOG.md generated deterministically from Gates 1-5's real recorded artifacts
- `gate6_governance` block written to `configs/bp1_customer_intent_classification.yaml`

## [Gate 5] Decision Layer & Reporting — 2026-09-22T06:07:25.491973+00:00
- Champion: `logistic_regression` — 3,080 decision records
  (150 with grounded reason codes)
- Recomputed test accuracy: 0.822403 (Gate 3 recorded:
  0.8224)
- Offline decision-record layer — no GenAI API call (scope decision confirmed by user
  2026-09-22)

## [Gate 4] Statistical Validation & Explainability — 2026-09-22T06:05:06.306025+00:00
- Champion `logistic_regression` vs runner-up `xgboost`: paired
  t-test p=0.0001
- Held-out F1-macro 95% bootstrap CI: [0.808, 0.8334]
- 77-class one-vs-rest macro ROC-AUC: 0.9933

## [Gate 3] Model/Classifier Benchmark & Champion Selection — 2026-09-22T05:39:07.988130+00:00
- Champion: `logistic_regression` (CV mean F1-macro 0.804, held-out test
  F1-macro 0.8221, accuracy 0.8224)
- Candidates evaluated: ['logistic_regression', 'random_forest', 'hist_gradient_boosting', 'xgboost', 'lightgbm', 'catboost']; candidates failed: []
- Open anomalies detected live this run from `gate3_cv_benchmark_results.csv`: 1 near-random,
  2 high-variance (see MODEL_CARD.md Known Limitations)

## [Gate 2] Data Verification & Taxonomy Engineering — 2026-09-22T04:54:33.532183+00:00 (file modification time of
`taxonomy_mapping_coverage_report.csv`; Gate 2 does not record its own JSON timestamp)
- CFPB Gold: 1048575 rows | BANKING77 Gold:
  13083 rows
- 77 BANKING77 categories mapped via
  `configs/taxonomy_mapping.yaml` (documented crosswalk, not a row-level join)

## [Gate 1] Business Understanding & Policy — 2026-09-22T04:53:54.488546+00:00
- Target: `category` (feature: `text`)
- Live-verified leakage checks: [] shared CFPB/BANKING77 columns,
  0 train/test text-overlap rows
- Class balance: 77-class ratio 5.34x,
  9-bucket ratio 3.85x
