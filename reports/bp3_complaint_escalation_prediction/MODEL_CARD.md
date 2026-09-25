# Model Card — BP3 Complaint Escalation / Intervention Prediction

*Generated 2026-09-23T10:52:03.150028+00:00 by `bp3_complaint_escalation_prediction_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP3 Gates 1-5's own real runs on this machine. No field
below was authored freeform or by a generative model (project zero-fabrication rule).*

## Model Details
- **Champion model:** `xgboost` (family: `one-hot/frequency-encoded structured features + xgboost`)
- **Pipeline:** one-hot (6 columns) + frequency-encoded `Company`
   -> `xgboost`
  (`src/features/bp3_escalation_features.py`, single source of truth for Gates 3/4/5's inline
  pipeline definition, extended at this gate)
- **Random state:** 42 (`configs/bp3_complaint_escalation_prediction.yaml`)
- **Candidates evaluated (real Gate 3 CV benchmark, all 5):**

  | model | status | mean PR-AUC | mean ROC-AUC | mean recall | elapsed |
  |---|---|---|---|---|---|
  | xgboost | OK | 0.3467 | 0.9774 | 0.9383 | 13.2s |
  | lightgbm | OK | 0.3459 | 0.9784 | 0.9623 | 13.1s |
  | hist_gradient_boosting | OK | 0.3449 | 0.9777 | 0.0734 | 91.8s |
  | random_forest | OK | 0.2710 | 0.9713 | 0.9453 | 325.3s |
  | logistic_regression | OK | 0.0425 | 0.8620 | 0.0000 | 4.8s |

## Intended Use
- **Primary target:** `intervention_required` — Binary: 1 if real 'Company response to consumer' == 'Closed with monetary relief' (CFPB's own explicit observed outcome, Master Plan's named example proxy); 0 if 'Closed with explanation' or 'Closed with non-monetary relief'. 'In progress', 'Untimely response', and null-response rows excluded from the trainable set - see policy.json exclusion_reasons for the full live-computed row accounting.
- **Disputed-flag note:** No 'Consumer disputed?' column exists in this real CFPB extract (CFPB dropped it from the public dataset in 2017) - re-verified live, not assumed.
- **Split source:** Fresh random split of the real, trainable-only CFPB rows, stratified by intervention_required, random_state=42.
- **Out of scope:** not intended for protected-class or demographic inference (`Tags` is excluded
  from the feature set entirely — see Ethical Considerations below for the real, live disparate-
  impact monitoring finding on this same column, used only as a read-only post-hoc lens).

## Training Data
- **Source:** Real CFPB extract, fresh stratified 80/20 split (CFPB provides no split of its own), random_state=42
- **n_train_rows:** 652,362 | **n_test_rows:**
  163,091
- **Positive-class ratio (real, live-computed):**
  0.0129 — this is why PR-AUC/average_precision,
  never accuracy, is the champion-selection metric (Master Plan's explicit BP3 methodology rule).
- **Leakage rules enforced:**
  - 'Company response to consumer' defines the target and must never also be used as an input feature.
  - 'Timely response?' barred from the feature set as a conservative default - real disagreement with 'Company response to consumer' found on this data by BP2 Gate 2 (1,963 rows); deferred to Gate 3 for an explicit leakage test.
  - 'Date received' and 'Date sent to company' barred - a computed response-time duration leaked BP2's own target on this identical data (BP2 Gate 3 finding); assumed to apply here until Gate 3 tests it directly.
  - 'Tags' barred - live-re-checked (not assumed from BP1/BP2 Gate 1's now-superseded claim) and found to contain demographic-adjacent values, matching BP2 Gate 3's real finding. BP3 is ECOA/Reg B-mapped (Master Plan Section 9).
  - 'Complaint ID' and 'ZIP code' barred as identifier / quasi-identifier, matching BP2's BARRED_COLUMNS precedent.
  - No BANKING77 data used at all for BP3 (Master Plan BP table: Integrates BANKING77? = NO).
  - No CFPB row may appear in both train and test splits - enforced structurally at Gate 3.
- **Gate 2 (real run, Gold layer's own file modification time
  2026-09-23T07:04:51.020616+00:00):** CFPB intervention-escalation
  Gold = 1048575
  rows (trainable: 815,453; excluded: 233,122).

## Evaluation Data & Results
- **Held-out test set:** a fresh stratified 80/20 split of the real CFPB extract (CFPB ships no
  provided split), 163,091 rows, evaluated once.
- **CV mean PR-AUC:** 0.3467 (5-fold)
- **Held-out test PR-AUC:** 0.3496 | **ROC-AUC:**
  0.9762 | **Recall:**
  0.9424 | **Precision:**
  0.1510 | **F1:**
  0.2603 (all at the default 0.5 threshold)
- **95% bootstrap CI on held-out PR-AUC** (1000 resamples):
  [0.3299, 0.3709] | **ROC-AUC CI:**
  [0.974, 0.978]
- **Paired t-test vs runner-up `lightgbm`:** p=0.6995
  (n=5 CV folds —
  n=5 CV folds is a small sample - treat p-values as directional evidence, not a high-powered statistical claim.)
- **Brier score (calibration):** 0.0533 | **F1-maximizing threshold in Gate 4's
  9-point grid:** 0.9 (reported as an alternate reference point
  only — Gate 3's official reporting stays at the default 0.5 threshold)
- **Decision layer (Gate 5):** 163,091 decision records; recomputed
  held-out PR-AUC 0.349569 (Gate 3 recorded:
  0.3496, diff=3.1e-05)

## Explainability
- **Method:** real SHAP, explainer chosen live by the champion's model type (LinearExplainer for a
  linear model, TreeExplainer for a tree-based model — densified whenever the champion is not
  LogisticRegression, per the real environment finding fixed in Gate 4; see
  `features.bp3_escalation_features.is_linear_champion`).
- **Global top-10 important features** (Gate 4, 150-row sample /
  50-row background):
  1. `Company_freq` (mean |SHAP| = 6.86853)
  2. `ohe__Issue_Credit limit changed` (mean |SHAP| = 1.38485)
  3. `ohe__Sub-issue_Problem with additional add-on products or services purchased with the loan` (mean |SHAP| = 1.34030)
  4. `ohe__Sub-product_General-purpose credit card or charge card` (mean |SHAP| = 1.31392)
  5. `ohe__State_NY` (mean |SHAP| = 1.27556)
  6. `ohe__Issue_Other transaction problem` (mean |SHAP| = 1.17813)
  7. `ohe__State_GA` (mean |SHAP| = 1.09065)
  8. `ohe__Sub-product_Telecommunications debt` (mean |SHAP| = 0.99301)
  9. `ohe__Sub-issue_Didn't receive services that were advertised` (mean |SHAP| = 0.98188)
  10. `ohe__Sub-issue_Excess mileage, damage, or wear fees, or other problem after the lease is finished` (mean |SHAP| = 0.97384)
- **Per-instance reason codes (Gate 5):** grounded by construction — a feature is only ever
  reported for a row if its value in that row is nonzero (the exact rule
  `features.bp3_escalation_features.reason_codes_for_row_shared` implements, extended into this
  module at this gate). 150 of
  163,091 decision records carry reason codes;
  0 grounding failures recorded.
- **Gate 4 vs Gate 5 independently-computed top-10 term overlap:**
  1/10 (['Company_freq']) — real
  sampling variance across two independent 150-row samples from a very high-cardinality feature
  space, reported as-is rather than adjusted for.

## Ethical Considerations / Compliance Touchpoints
- **ECOA/Reg B framing (Gate 1):** The real CFPB extract's 15 named columns carry no demographic or protected-class field by name. However, 'Tags' (one of those 15 columns) was found - live, in Section 5 above, re-confirming BP2 Gate 3's own real finding on the same data - to contain demographic-adjacent values. Per Master Plan Section 9's own rule ('if any demographic-adjacent field is present, disparate-impact-style testing runs before Gate 6'), BP3 excludes 'Tags' from its feature set outright at this Gate rather than deferring that compliance burden. With 'Tags' excluded, no remaining candidate feature is demographic-adjacent, so disparate-impact-style testing is not required for the feature set BP3 actually uses - stated as a scoping decision, not a claim that no protected-class-adjacent data exists anywhere in the source file.
- **Disparate-impact monitoring check (Gate 4, real, FLAGGED (< 0.8, four-fifths-rule convention)):** per-group selection
  rate and recall at the default 0.5 threshold, real held-out test data:

  | Tags group | n rows | n real positive | selection rate | recall |
  |---|---|---|---|---|
  | NO_TAG | 153,194 | 1,625 | 0.0684 | 0.9477 |
  | Servicemember | 6,726 | 161 | 0.1615 | 0.913 |
  | Older American | 2,447 | 252 | 0.492 | 0.9365 |
  | Older American, Servicemember | 724 | 64 | 0.4862 | 0.9062 |

  **Adverse-impact ratio (min/max group selection rate): 0.139** — FLAGGED (< 0.8, four-fifths-rule convention).
  Independently recomputed at Gate 5 on the full refit: 0.139.
  Explicitly a monitoring signal for a human reviewer, not a legal determination of ECOA/Reg B
  compliance — selection-rate parity alone does not establish or rule out disparate impact. This
  finding is carried here verbatim, not softened or omitted from this governance document.
- **UDAAP language review (Gate 5):** Not Applicable to BP3 Gate 5 - this gate generates no GenAI or customer-facing text; predicted labels, probabilities, and per-instance SHAP reason codes are deterministic outputs of the champion classifier. Real GenAI-drafted customer-facing text (subject to UDAAP review) is scoped to BP6 (GenAI Resolution Assistant) per the Master Execution Plan, same standing scope decision as BP1/BP2 Gate 5.
- **NIST AI RMF Measure/Manage:** Not Applicable to BP3 Gate 5 for the same reason - no GenAI output is produced here. Applies at BP6.
- **Model inventory (SR 11-7):** Model inventory entry opened (SR 11-7 first-line record)
- **GenAI API used in BP3:** False (scope
  decision confirmed by user
  2026-09-22)

## Known Limitations
- No candidate-level near-random PR-AUC anomalies detected among the 5 passing candidate(s) (floor: 0.0258, 2.0x the real positive-class base rate 0.0129).
- **logistic_regression**: real CV mean recall 0.0000 at the default 0.5 threshold (< 0.1) despite passing PR-AUC 0.0425 and ROC-AUC 0.8620 - the model ranks positives well above random but the default threshold yields almost no positive predictions on this real data. Not yet root-caused; champion selection uses PR-AUC, not threshold-dependent recall, so this never had a path to silently becoming the champion.
- **hist_gradient_boosting**: real CV mean recall 0.0734 at the default 0.5 threshold (< 0.1) despite passing PR-AUC 0.3449 and ROC-AUC 0.9777 - the model ranks positives well above random but the default threshold yields almost no positive predictions on this real data. Not yet root-caused; champion selection uses PR-AUC, not threshold-dependent recall, so this never had a path to silently becoming the champion.
- No candidate failed Gate 3's CV benchmark on this real run (all 5 OK).
- n=5 CV folds is a small sample - treat p-values as directional evidence, not a high-powered statistical claim.
- Monitoring signal for a human reviewer, not a legal determination of ECOA/Reg B compliance.

## Governance & Testing (this Gate 6 run, 2026-09-23T10:52:03.150028+00:00)
- **pytest suite** (`pytest tests/ -v --tb=short`): '\x1b[33m================ \x1b[32m189 passed\x1b[0m, \x1b[33m\x1b[1m4 skipped\x1b[0m, \x1b[33m\x1b[1m125 warnings\x1b[0m\x1b[33m in 29.18s\x1b[0m\x1b[33m ================\x1b[0m' → parsed as
  {'passed': 189, 'failed': 0, 'skipped': 4, 'errors': 0, 'xfailed': 0, 'xpassed': 0} (exit code 0, all_passed=True). First run
  with real BP3 coverage — `src/features/bp3_escalation_features.py`'s Gate 6 extension and its 2
  new test files (`tests/bp3_complaint_escalation_prediction/test_bp3_escalation_features.py`,
  `tests/bp3_complaint_escalation_prediction/test_gate_artifacts.py`) were delivered alongside this
  notebook.
- **Static notebook audit** (`scripts/check_notebook_syntax.py` — nbformat + ast + pyflakes, static
  only, nothing executed): 27 passed / 0 failed (exit
  code 0, all_passed=True)
- Full logs:
  `notebooks/bp3_complaint_escalation_prediction/artifacts/gate6_pytest_output.log`,
  `gate6_notebook_syntax_check_output.log`

## Change History
See `CHANGELOG.md` in this same folder.
