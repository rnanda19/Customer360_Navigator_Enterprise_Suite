# CHANGELOG — BP2 Customer Friction Classification

All dates below are real UTC timestamps read live from each gate's own recorded artifact at the
moment this Gate 6 notebook was run (2026-09-22T15:38:48.420509+00:00) — not typed in from memory.

## [Gate 6] Productization, Monitoring & Governance — 2026-09-22T15:38:48.420509+00:00
- pytest suite: 105 passed, 0 failed,
  1 skipped, 0 errors (106 total) -
  first run with real BP2 coverage (`src/features/bp2_friction_features.py` + 3 new test files)
- Static notebook-syntax audit: 19/19 notebooks passed
- MODEL_CARD.md and this CHANGELOG.md generated deterministically from Gates 1-5's real recorded artifacts
- `gate6_governance` block written to `configs/bp2_customer_friction_classification.yaml`

## [Gate 5] Decision Layer & Reporting — 2026-09-22T15:38:17.744233+00:00
- Champion: `xgboost` — 163,344 decision records
  (150 with grounded reason codes)
- Recomputed test accuracy: 0.755773 (Gate 3 recorded:
  0.7558)
- Offline decision-record layer — no GenAI API call (scope decision confirmed by user
  2026-09-22)

## [Gate 4] Statistical Validation & Explainability — 2026-09-22T15:35:22.086950+00:00
- Champion `xgboost` vs runner-up `hist_gradient_boosting`: paired
  t-test p=0.2371
- Held-out F1-macro 95% bootstrap CI: [0.4452, 0.4666]
- 4-class one-vs-rest macro ROC-AUC: 0.8857

## [Gate 3] Model/Classifier Benchmark & Champion Selection — 2026-09-22T14:58:50.729269+00:00
- Champion: `xgboost` (CV mean F1-macro 0.4584, held-out test
  F1-macro 0.4559, accuracy 0.7558)
- Candidates evaluated: ['logistic_regression', 'random_forest', 'hist_gradient_boosting', 'xgboost', 'lightgbm']; candidates failed:
  [] (real recorded status, see MODEL_CARD.md Known Limitations)
- Class imbalance ratio: 152.0:1
- Open items detected live this run from `gate3_cv_benchmark_results.csv`: 0
  near-random passing, 0 high-variance passing, 0
  failed (see MODEL_CARD.md Known Limitations)

## [Gate 2] Data Verification & Taxonomy Engineering — 2026-09-22T14:42:52.331336+00:00
(file modification time of `cfpb_friction_severity_gold.parquet`; Gate 2 does not record its own
JSON timestamp)
- CFPB friction-severity Gold: 1048575 rows
  (trainable: 816,717, excluded:
  231,858)
- BANKING77 taxonomy-bucket in-scope rows: 68,710

## [Gate 1] Business Understanding & Policy — 2026-09-22T08:40:12.439074+00:00
- Target: `friction_severity_class` (bucket-to-class mapping deferred to Gate 2)
- Scoped-out signals: sentiment proxy, repeat-contact signal (documented real-data reasons)
- Live-verified: 1,048,575 real CFPB rows,
  570,861 null `Company public response` rows
