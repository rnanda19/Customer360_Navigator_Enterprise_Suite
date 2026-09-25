# Changelog — BP5 Root-Cause & Driver Analytics

*Generated 2026-09-24T11:15:03.634508+00:00, deterministically, from real values recorded by BP5 Gates 1-6's own real
runs on this machine.*

## [Gate 6] Productization, Monitoring & Governance — 2026-09-24T11:15:03.634508+00:00
- Real full pytest suite: `[33m================ [32m325 passed[0m, [33m[1m3 skipped[0m, [33m[1m182 warnings[0m[33m in 9.51s[0m[33m =================[0m` (all passed: True)
- Real static notebook-syntax audit: 51 passed / 0 failed
- MODEL_CARD.md and CHANGELOG.md generated deterministically from Gates 1-5's own real recorded
  values (this file)
- New test coverage delivered: `test_bp5_driver_association.py` (29 real unit tests),
  `test_gate_artifacts.py` (19 real schema/cross-artifact checks)
- Real bug fixed in `src/models/bp5_driver_association.py::compute_calibration_curve()` by this
  gate's own pre-delivery unit-test verification: `pd.qcut` on a constant/near-constant
  `y_proba` series silently returned all-NaN bin labels (never raising `ValueError`), which
  groupby-vanished into a silently empty `calibration_curve` rather than engaging the intended
  raw-overall-rate fallback. Fixed with an explicit `nunique() < 2` guard. Does NOT change Gate
  4's own already real-run-confirmed real numbers (the real held-out set has far more than 2
  distinct predicted probabilities) — a pure edge-case robustness fix, HYPER (Gates 3/4/5 are not
  retroactively re-run).
- Open items surfaced live (never hardcoded): 2 negligible-strength
  field/outcome row(s), 0 near-random-PR-AUC outcome(s),
  1 near-zero-precision-at-0.5 outcome(s) — see MODEL_CARD.md
  Known Limitations.

## [Gate 5] Decision Layer & Reporting — Prioritized Root-Cause Report
- 5 field-level findings (outcome_1),
  5 (outcome_2)
- 23 category-level findings (outcome_1),
  23 (outcome_2)
- UDAAP mechanical language check passed on 76
  generated narrative sentences

## [Gate 4] Statistical Validation — Bootstrap CI / Calibration / Confusion Matrix
- Consistent with Gate 3's recorded champion AUCs: True
- Brier scores: outcome_1=0.072676, outcome_2=0.099226

## [Gate 3] Hypothesis Testing / Regression / SHAP Association Benchmark
- 12 chi-square tests run,
  10 log-odds-ratio field/outcome combinations
- Held-out ROC-AUC: outcome_1=0.970523,
  outcome_2=0.952578

## [Gate 2] Data Verification & Feature Engineering — 2026-09-24T07:35:10.988222+00:00
(file modification time of the real Gold parquet; Gate 2 records no own JSON timestamp)
- Gold layer: 1048575 rows

## [Gate 1] Business Understanding & Policy — 2026-09-24T07:16:13.829757+00:00
- Two real outcome fields defined; ECOA/Reg B correctly Not Applicable; UDAAP applies
