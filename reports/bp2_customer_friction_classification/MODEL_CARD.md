# Model Card — BP2 Customer Friction Classification

*Generated 2026-09-22T15:38:48.420509+00:00 by `bp2_customer_friction_classification_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP2 Gates 1-5's own real runs on this machine. No field
below was authored freeform or by a generative model (project zero-fabrication rule).*

## Model Details
- **Champion model:** `xgboost` (family: `one-hot/frequency-encoded structured features + xgboost`)
- **Pipeline:** one-hot (7 columns) + frequency-encoded `Company` -> `xgboost`
  (`src/features/bp2_friction_features.py`, single source of truth for Gates 3/4/5's inline pipeline
  definition, extracted at this gate)
- **Random state:** 42 (`configs/bp2_customer_friction_classification.yaml`)
- **Candidates evaluated (real Gate 3 CV benchmark, all 6, including the failed one):**

  | model | status | mean F1-macro | std F1-macro | mean accuracy | elapsed |
  |---|---|---|---|---|---|
  | xgboost | OK | 0.4584 | 0.0075 | 0.7582 | 32.1s |
  | hist_gradient_boosting | OK | 0.4525 | 0.0068 | 0.7570 | 148.7s |
  | lightgbm | OK | 0.4478 | 0.0013 | 0.6642 | 24.3s |
  | random_forest | OK | 0.3942 | 0.0037 | 0.5792 | 542.9s |
  | logistic_regression | OK | 0.1384 | 0.0000 | 0.3827 | 7.1s |

## Intended Use
- **Primary target:** `friction_severity_class` — an ordinal friction-severity class derived
  from real CFPB `Company response to consumer` and `Timely response?` fields (bucket-to-class
  mapping documented in `configs/bp2_friction_severity_taxonomy.yaml`, Gate 2).
- **Scoped-out signals:** sentiment proxy and repeat-contact signal — both honestly scoped out for
  documented real-data reasons (no narrative text column; no persistent customer identifier), not
  silently substituted. See `target_definition.scoped_out_signals` in the config for the full
  reasoning.
- **Split source:** Fresh random split of the real CFPB extract (CFPB ships no pre-defined split), stratified by the derived target, random_state=42.
- **Out of scope:** not trained or evaluated on `Company public response` (ablation not yet run,
  see Known Limitations); not intended for protected-class or demographic inference (Gate 3's live
  compliance check on `Tags` found demographic-adjacent values, but `Tags` is excluded from the
  feature set regardless — see Known Limitations).

## Training Data
- **Source:** Real CFPB extract, fresh stratified 80/20 split (CFPB provides no split of its own), random_state=42
- **n_train_rows:** 653,373 | **n_test_rows:** 163,344
  | **n_classes:** 4
- **Class imbalance (Gate 3, live-computed):** 152.0:1
  (majority/minority ordinal class) — this is why macro-F1, not accuracy, is the champion-selection
  metric (see Evaluation Data & Results below for why this matters in practice).
- **Leakage rules enforced:**
  - 'Company response to consumer' and 'Timely response?' define the target and must never also be used as input features.
  - 'Company public response' is not pre-cleared as a safe feature (~54% null, live-checked) - Gate 2/3 must test it for leakage before use.
  - No CFPB row may appear in both train and test splits - enforced structurally at Gate 3.
  - BANKING77 is never a source of friction/severity training labels (schema verified live: text, category only) - contributes only the Gate-2/BP1 taxonomy-bucket feature.
- **CFPB<->BANKING77 integration:** the Gate-2/BP1 `common_taxonomy_bucket` feature
  (68,710 of the trainable rows are in scope for
  it), never a row-level join — BANKING77 itself carries no friction/severity signal.
  Gate 2 (real run, Gold layer's own file modification time
  2026-09-22T14:42:52.331336+00:00): CFPB friction-severity Gold =
  1048575 rows
  (trainable, 4 ordinal classes: 816,717; excluded
  pending/unknown: 231,858).

## Evaluation Data & Results
- **Held-out test set:** a fresh stratified 80/20 split of the real CFPB extract (CFPB ships no
  provided split), 163,344 rows, evaluated once.
- **CV mean F1-macro:** 0.4584 (5-fold)
- **Held-out test F1-macro:** 0.4559 | **F1-weighted:**
  0.7355 | **Accuracy:** 0.7558
- **Accuracy vs. macro-F1 divergence:** the 0.7558
  accuracy is substantially higher than the 0.4559
  macro-F1 — an expected, honest consequence of the real
  152.0:1 class imbalance (a model
  that leans toward the majority class scores well on accuracy while doing poorly on minority
  classes). This divergence is evidence supporting Gate 1's original decision to select the
  champion by macro-F1 rather than accuracy, not a new finding at this gate.
- **95% bootstrap CI on held-out F1-macro** (1000 resamples):
  [0.4452, 0.4666]
- **Paired t-test vs runner-up `hist_gradient_boosting`:** p=0.2371
  (n=5 CV folds — n=5 CV folds is a small sample - treat p-values as directional evidence, not a high-powered statistical claim.)
- **4-class one-vs-rest macro ROC-AUC:** 0.8857
- **Decision layer (Gate 5):** 163,344 decision records; recomputed accuracy
  0.755773 (Gate 3 recorded:
  0.7558, diff=2.7e-05)

## Explainability
- **Method:** real SHAP, explainer chosen live by the champion's model type (LinearExplainer for a
  linear model, TreeExplainer for a tree-based model — densified whenever the champion is not
  LogisticRegression, per the real environment finding fixed in Gate 4; see
  `features.bp2_friction_features.is_linear_champion`).
- **Global top-10 important features** (Gate 4, 150-row sample /
  50-row background):
  1. `Company_freq` (mean |SHAP| = 2.11225)
  2. `ohe__Sub-product_Federal student loan servicing` (mean |SHAP| = 0.57674)
  3. `ohe__Product_Credit reporting or other personal consumer reports` (mean |SHAP| = 0.32713)
  4. `ohe__Sub-issue_Application denied` (mean |SHAP| = 0.26306)
  5. `ohe__Sub-product_Title loan` (mean |SHAP| = 0.25808)
  6. `ohe__State_CA` (mean |SHAP| = 0.23618)
  7. `ohe__State_NV` (mean |SHAP| = 0.23500)
  8. `ohe__State_RI` (mean |SHAP| = 0.23229)
  9. `ohe__State_NJ` (mean |SHAP| = 0.21989)
  10. `ohe__Sub-issue_Received bad information about your loan` (mean |SHAP| = 0.20969)
- **Per-instance reason codes (Gate 5):** grounded by construction — for the shared one-hot/
  frequency feature space, a feature is only ever reported for a row if its value in that row is
  nonzero (the exact rule BP1's `reason_codes_for_row` already implements, reused unmodified here
  via `reason_codes_for_row_shared`); for CatBoost's raw categorical path (no "absent" concept),
  codes are formatted `Column=Value`. 150 of
  163,344 decision records carry reason codes;
  0 grounding failures recorded.
- **Gate 4 vs Gate 5 independently-computed top-10 term overlap:** 2/10
  (['Company_freq', 'ohe__Product_Credit reporting or other personal consumer reports']) — a raw-categorical champion's `Column=Value` codes
  will not literally match Gate 4's bare feature names even on real overlap, so this is most
  informative when the champion uses the shared one-hot feature space (recorded here as-is, not
  adjusted for that asymmetry).

## Ethical Considerations / Compliance Touchpoints
- **UDAAP framing (Gate 1):** Per Master Plan Section 9: friction findings from this classifier are framed as potential risk indicators only when statistically supported - never as a determination of unfair, deceptive, or abusive conduct by any named company. No demographic or protected-class field exists in the real CFPB extract in scope for this project (docs/data_dictionary/RAW_DATA_MANIFEST.md Finding 3), so ECOA/Regulation B disparate-impact testing is Not Applicable - No Protected-Class Field in Scope, stated honestly rather than skipped silently.
- **UDAAP language review (Gate 5):** Not Applicable to BP2 Gate 5 - this gate generates no GenAI or customer-facing text; reason codes and confidence scores are deterministic outputs of the champion classifier and real per-instance SHAP values. Real GenAI-drafted customer-facing text (subject to UDAAP review) is scoped to BP6 (GenAI Resolution Assistant) per the Master Execution Plan, same standing scope decision as BP1 Gate 5.
- **NIST AI RMF Measure/Manage:** Not Applicable to BP2 Gate 5 for the same reason - no GenAI output is produced here. Applies at BP6.
- **Model inventory (SR 11-7):** Model inventory entry opened (SR 11-7 first-line record)
- **GenAI API used in BP2:** False (scope decision
  confirmed by user 2026-09-22)
- **Demographic-adjacent `Tags` finding (Gate 3, live):** real values found —
  ['servicemember', 'older american', 'older american, servicemember']. `Tags` is excluded from the feature
  set regardless (low information), but this finding updates Gate 1's "No Protected-Class Field in
  Scope" statement and is flagged here for ECOA/Regulation B review rather than left only as a code
  comment.

## Known Limitations
- No candidate-level near-random-score or high-variance anomalies detected among the 5 passing candidate(s) in this run's `gate3_cv_benchmark_results.csv`.
- `Company public response` ablation not yet run (Gate 3 open item, ~54% null, not yet tested for
  leakage or predictive value) - carried forward unresolved into this gate, not silently dropped.
- Gate 4/Gate 5 SHAP top-10 term overlap is 2/10 - see the
  Explainability section above for why this number is expected to be less informative than BP1's
  own equivalent overlap check.
- n=5 CV folds is a small sample - treat p-values as directional evidence, not a high-powered statistical claim.
- With only 4 real severity classes, Gate 5's top-3-of-4
  confidence breakdown is far less differentiating than BP1's 77-class equivalent (rank-3 is nearly
  always just the lowest-probability remaining class) - reported anyway for structural consistency,
  not omitted.
- `EXCLUDED_PENDING` rows (Gate 2, 22.11% of the real extract, "In progress" status) are excluded
  from the trainable target as a right-censored/pending status, not a resolution outcome - the real
  extract's date-ordering (most-recent-first, per RAW_DATA_MANIFEST.md Finding 4) means these rows
  likely skew toward the most recent complaints, a documented assumption/limitation, not resolved
  here.

## Governance & Testing (this Gate 6 run, 2026-09-22T15:38:48.420509+00:00)
- **pytest suite** (`pytest tests/ -v --tb=short`): '\x1b[32m======================= \x1b[32m\x1b[1m105 passed\x1b[0m, \x1b[33m1 skipped\x1b[0m\x1b[32m in 2.99s\x1b[0m\x1b[32m ========================\x1b[0m' → parsed as {'passed': 105, 'failed': 0, 'skipped': 1, 'errors': 0, 'xfailed': 0, 'xpassed': 0}
  (exit code 0, all_passed=True). First run with real BP2
  coverage - `src/features/bp2_friction_features.py` and its 3 new test files
  (`tests/bp2_customer_friction_classification/test_bp2_friction_features.py`,
  `tests/bp2_customer_friction_classification/test_gate_artifacts.py`,
  `tests/shared/test_friction_severity_mapper.py`) were delivered alongside this notebook.
- **Static notebook audit** (`scripts/check_notebook_syntax.py` — nbformat + ast + pyflakes, static
  only, nothing executed): 19 passed / 0 failed
  (exit code 0, all_passed=True)
- Full logs: `notebooks/bp2_customer_friction_classification/artifacts/gate6_pytest_output.log`,
  `gate6_notebook_syntax_check_output.log`

## Change History
See `CHANGELOG.md` in this same folder.
