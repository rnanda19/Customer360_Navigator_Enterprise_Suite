# Model Card — BP1 Customer Intent Classification

*Generated 2026-09-22T06:25:18.547134+00:00 by `bp1_customer_intent_classification_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP1 Gates 1-5's own real runs on this machine. No field
below was authored freeform or by a generative model (project zero-fabrication rule).*

## Model Details
- **Champion model:** `logistic_regression` (family: `TF-IDF + logistic_regression`)
- **Pipeline:** TF-IDF (`{'max_features': 5000, 'ngram_range': (1, 2), 'min_df': 2, 'sublinear_tf': True, 'stop_words': 'english'}`) -> `logistic_regression`
  (`src/models/bp1_intent_classifier.py`, single source of truth for Gates 3/4/5's inline pipeline definition)
- **Random state:** 42 (`configs/bp1_customer_intent_classification.yaml`)
- **Candidates evaluated (real Gate 3 CV benchmark):**

  | model | status | mean F1-macro | std F1-macro | mean accuracy | elapsed |
  |---|---|---|---|---|---|
  | logistic_regression | OK | 0.8040 | 0.0043 | 0.8095 | 5.4s |
  | xgboost | OK | 0.7494 | 0.0064 | 0.7548 | 103.8s |
  | random_forest | OK | 0.7084 | 0.0125 | 0.7143 | 2.2s |
  | catboost | OK | 0.7034 | 0.0114 | 0.7039 | 769.8s |
  | lightgbm | OK | 0.4403 | 0.3554 | 0.4488 | 17.1s |
  | hist_gradient_boosting | OK | 0.0137 | 0.0261 | 0.0278 | 1730.8s |

- **Candidates failed (real, Gate 3):** []

## Intended Use
- **Primary target:** `category` — BANKING77's real 77-class fine-grained customer-intent
  label, attached to the `text` field it was collected with.
- **Secondary target:** `common_taxonomy_bucket` — the 9-bucket common taxonomy (Gate 2), used only
  for coarser reporting and CFPB cross-dataset comparability; never trained on directly.
- **Split source:** BANKING77's own provided train/test split - never re-randomized.
- **Out of scope:** not trained or evaluated on any CFPB narrative text (none exists in this extract - see
  Training Data below); not intended for protected-class or demographic inference (no such field is present
  anywhere in this pipeline).

## Training Data
- **Source:** PolyAI BANKING77 train split (real, provided split, never re-randomized)
- **n_train_rows:** 10,003 | **n_test_rows:** 3,080
  | **n_classes:** 77
- **Class balance (Gate 1, live-verified):** 77-class imbalance ratio 5.34x
  (min=35, max=187);
  9-bucket imbalance ratio 3.85x
  (min=460, max=1770)
- **Leakage rules enforced (Gate 1, live-verified train/test exact-text overlap = 0 rows):**
  - No CFPB row-level data is ever joined into BANKING77 training/evaluation data (zero shared columns, verified live in the Gate 1 notebook).
  - BANKING77 train/test split used as provided, never re-randomized or re-merged (live exact-text overlap check run every Gate 1 execution).
  - CFPB Gate-2 bucket-tagged rows are descriptive/reporting inputs only (BP8), never training/eval data for this classifier.
- **CFPB<->BANKING77 integration:** a documented taxonomy/semantic crosswalk (`configs/taxonomy_mapping.yaml`,
  77 BANKING77 categories mapped), never a row-level join.
  Gate 2 (real run, this file's own modification time 2026-09-22T04:54:33.532183+00:00): CFPB Gold = 1048575 rows,
  BANKING77 Gold = 13083 rows.

## Evaluation Data & Results
- **Held-out test set:** BANKING77's provided test split, 3,080 rows, evaluated once.
- **CV mean F1-macro:** 0.804 (5-fold)
- **Held-out test F1-macro:** 0.8221 | **F1-weighted:**
  0.8221 | **Accuracy:** 0.8224
- **95% bootstrap CI on held-out F1-macro** (1000 resamples):
  [0.808, 0.8334]
- **Paired t-test vs runner-up `xgboost`:** p=0.0001
  (n=5 CV folds — n=5 CV folds is a small sample - treat p-values as directional evidence, not a high-powered statistical claim.)
- **77-class one-vs-rest macro ROC-AUC:** 0.9933
- **Decision layer (Gate 5):** 3,080 decision records; recomputed accuracy
  0.822403 (Gate 3 recorded: 0.8224,
  diff=3e-06)

## Explainability
- **Method:** real SHAP, explainer chosen live by the champion's model type (LinearExplainer for a linear
  model, TreeExplainer for a tree-based model).
- **Global top-10 important terms** (Gate 4, 150-row sample /
  50-row background):
  1. `card` (mean |SHAP| = 0.13430)
  2. `transfer` (mean |SHAP| = 0.06656)
  3. `account` (mean |SHAP| = 0.04116)
  4. `pin` (mean |SHAP| = 0.03200)
  5. `payment` (mean |SHAP| = 0.02668)
  6. `transaction` (mean |SHAP| = 0.02643)
  7. `cash` (mean |SHAP| = 0.02559)
  8. `pending` (mean |SHAP| = 0.02427)
  9. `fee` (mean |SHAP| = 0.02272)
  10. `atm` (mean |SHAP| = 0.02261)
- **Per-instance reason codes (Gate 5):** grounded by construction — a term is only ever reported for a row if
  that term's TF-IDF weight in that row's own vectorized text is nonzero. 150
  of 3,080 decision records carry reason codes;
  0 grounding failures recorded.
- **Gate 4 vs Gate 5 independently-computed top-10 term overlap:** 4/10
  (['account', 'card', 'pending', 'transfer'])

## Ethical Considerations / Compliance Touchpoints
- **Data minimization & purpose limitation (Gate 1):** BP1 processes only the `text` and `category` fields of the publicly released BANKING77 dataset (anonymized customer-service intent utterances, no real-customer PII) for the stated purpose of intent classification. CFPB fields used elsewhere in this suite are limited to structured Product/Sub-product/Issue categories already published by CFPB - no narrative text, no demographic or protected-class field, and no CFPB data is used as training or evaluation data for this classifier. No data is collected, retained, or processed beyond what is documented here.
- **UDAAP language review:** Not Applicable to BP1 Gate 5 - this gate generates no GenAI or customer-facing text; reason codes and confidence scores are deterministic outputs of the champion classifier and real per-instance SHAP values. Real GenAI-drafted customer-facing text (subject to UDAAP review) is scoped to BP6 (GenAI Resolution Assistant) per the Master Execution Plan's own Section 24 Sprint 5 mapping.
- **NIST AI RMF Measure/Manage:** Not Applicable to BP1 Gate 5 for the same reason - no GenAI output is produced here. Applies at BP6.
- **Model inventory (SR 11-7):** Model inventory entry opened (SR 11-7 first-line record)
- **GenAI API used in BP1:** False (scope decision confirmed
  by user 2026-09-22)

## Known Limitations
- **hist_gradient_boosting**: real CV mean F1-macro 0.0137 (near the 77-class random baseline of ~0.013) despite 1730.8s of real CV wall-clock time and `status: OK` (no exception raised) - not yet root-caused; tracked as Evidence Ledger open item #1. Champion selection is unaffected (logistic_regression's 0.8040 is unambiguously the best real CV score).
- **hist_gradient_boosting**: real CV fold-to-fold std 0.0261 vs mean 0.0137 (std/mean ratio 1.91) - fold-to-fold variance nearly as large as the mean itself, indicating an unstable fit for this candidate on this data; not yet root-caused, tracked as Evidence Ledger open item #1.
- **lightgbm**: real CV fold-to-fold std 0.3554 vs mean 0.4403 (std/mean ratio 0.81) - fold-to-fold variance nearly as large as the mean itself, indicating an unstable fit for this candidate on this data; not yet root-caused, tracked as Evidence Ledger open item #1.
- Gate 4/Gate 5 SHAP top-10 term overlap is 4/10, not higher — two
  different random samples of noisy real data are expected to diverge somewhat; not treated as a code defect.
- n=5 CV folds is a small sample - treat p-values as directional evidence, not a high-powered statistical claim.

## Governance & Testing (this Gate 6 run, 2026-09-22T06:25:18.547134+00:00)
- **pytest suite** (`pytest tests/ -v --tb=short`): '\x1b[32m============================= \x1b[32m\x1b[1m52 passed\x1b[0m\x1b[32m in 2.21s\x1b[0m\x1b[32m ==============================\x1b[0m' → parsed as {'passed': 52, 'failed': 0, 'skipped': 0, 'errors': 0, 'xfailed': 0, 'xpassed': 0}
  (exit code 0, all_passed=True)
- **Static notebook audit** (`scripts/check_notebook_syntax.py` — nbformat + ast + pyflakes, static only,
  nothing executed): 8 passed / 0 failed
  (exit code 0, all_passed=True)
- Full logs: `notebooks/bp1_customer_intent_classification/artifacts/gate6_pytest_output.log`,
  `gate6_notebook_syntax_check_output.log`

## Change History
See `CHANGELOG.md` in this same folder.
