# CHANGELOG — BP3 Complaint Escalation / Intervention Prediction

All dates below are real UTC timestamps read live from each gate's own recorded artifact at the
moment this Gate 6 notebook was run (2026-09-23T10:52:03.150028+00:00) — not typed in from memory.

## [Gate 6] Productization, Monitoring & Governance — 2026-09-23T10:52:03.150028+00:00
- pytest suite: 189 passed, 0 failed,
  4 skipped, 0 errors (193 total) -
  first run with real BP3 coverage (`src/features/bp3_escalation_features.py` extension + 2 new
  test files)
- Static notebook-syntax audit: 27/27 notebooks passed
- MODEL_CARD.md and this CHANGELOG.md generated deterministically from Gates 1-5's real recorded artifacts
- `gate6_governance` block written to `configs/bp3_complaint_escalation_prediction.yaml`
- Open items detected live this run: 0 near-random PR-AUC, 2
  near-zero-recall, 0 failed candidates

## [Gate 5] Decision Layer & Reporting — 2026-09-23T09:13:17.664996+00:00
- Champion: `xgboost` — 163,091 decision records
  (150 with grounded reason codes)
- Recomputed held-out PR-AUC: 0.349569 (Gate 3 recorded:
  0.3496)
- Recomputed disparate-impact ratio: 0.139 (Gate 4
  recorded: 0.139)
- Offline decision-record layer — no GenAI API call (scope decision confirmed by user
  2026-09-22)

## [Gate 4] Statistical Validation & Explainability — 2026-09-23T08:44:28.367140+00:00
- Champion `xgboost` vs runner-up `lightgbm`:
  paired t-test p=0.6995
- Held-out PR-AUC 95% bootstrap CI: [0.3299, 0.3709] | ROC-AUC CI:
  [0.974, 0.978]
- Brier score: 0.0533 | Disparate-impact ratio (Tags):
  0.139 (FLAGGED (< 0.8, four-fifths-rule convention))

## [Gate 3] Model/Classifier Benchmark & Champion Selection — 2026-09-23T07:43:50.243503+00:00
- Champion: `xgboost` (CV mean PR-AUC 0.3467,
  held-out test PR-AUC 0.3496, ROC-AUC
  0.9762, recall
  0.9424)
- Candidates evaluated: ['logistic_regression', 'random_forest', 'hist_gradient_boosting', 'xgboost', 'lightgbm']; candidates failed:
  []
- Positive-class ratio: 0.0129
- Open items detected live this run from `gate3_cv_benchmark_results.csv`: 0
  near-random PR-AUC passing, 2 near-zero-recall passing,
  0 failed (see MODEL_CARD.md Known Limitations)

## [Gate 2] Data Verification & Feature/Taxonomy Engineering — 2026-09-23T07:04:51.020616+00:00
(file modification time of `cfpb_intervention_escalation_gold.parquet`; Gate 2 does not record its
own JSON timestamp)
- CFPB intervention-escalation Gold:
  1048575 rows
  (trainable: 815,453, excluded: 233,122)

## [Gate 1] Business Understanding & Policy — 2026-09-23T06:43:07.078848+00:00
- Target: `intervention_required` (Binary: 1 if real 'Company response to consumer' == 'Closed with monetary relief' (CFPB's own explicit observed outcome, Master Plan's named example proxy); 0 if 'Closed with explanation' or 'Closed with non-monetary relief'. 'In progress', 'Untimely response', and null-response rows excluded from the trainable set - see policy.json exclusion_reasons for the full live-computed row accounting.)
- Live-verified: 1,048,575 real CFPB rows,
  demographic-adjacent `Tags` values found:
  ['Servicemember', 'Older American', 'Older American, Servicemember']
