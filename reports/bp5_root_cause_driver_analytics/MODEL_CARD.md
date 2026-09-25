# Model Card — BP5 Root-Cause & Driver Analytics

*Generated 2026-09-24T11:15:03.634508+00:00 by `bp5_root_cause_driver_analytics_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP5 Gates 1-5's own real runs on this machine. No field
below was authored freeform or by a generative model (project zero-fabrication rule).*

## Model Details
- **Nature of this BP**: population-level statistical ASSOCIATION analytics across two real CFPB
  outcome fields — **not** a per-instance deployed classifier. BP5's own real `methodology_policy`
  (Gate 1) names only logistic regression (no multi-model benchmark, a real disclosed scope
  difference from BP1-3's Gate 3). Accordingly this BP has **no persisted model bundle and no
  inference service** — "productization" here means the reporting, testing, and governance
  artifacts below, not deployment infrastructure.
- **Two real champions, one per outcome** (both `sklearn.LogisticRegression`,
  `class_weight="balanced"`, `random_state=42`, 5 one-hot categorical
  fields + `Company_freq` z-scored — `src/models/bp5_driver_association.py::build_champion_model()`):
  - `outcome_1_intervention_required`: held-out ROC-AUC 0.9705, PR-AUC
    0.2533 (n_test=163,091)
  - `outcome_2_timely_response_failure`: held-out ROC-AUC 0.9526, PR-AUC
    0.0703 (n_test=209,715)
- **Gate 4 re-derivation check**: Gate 3's recorded held-out ROC-AUC falls inside Gate 4's own real
  bootstrap 95% CI (± the disclosed `GATE4_AUC_TOLERANCE=0.01` floating-point
  solver tolerance) for both outcomes: **True**.

## Intended Use
- **Two real, distinct outcomes, never combined into one joint target**:
  - `outcome_1_intervention_required`: Reused verbatim from BP3 Gate 1's own real definition on 'Company response to consumer'. Binary: 1 if 'Closed with monetary relief'; 0 if 'Closed with explanation' or 'Closed with non-monetary relief'. 'In progress', 'Untimely response', and null-response rows excluded from the trainable set.
  - `outcome_2_timely_response_failure`: New to BP5. Binary: 1 if real 'Timely response?' == 'No'; 0 if 'Yes'. Computed over the full real population, independent of 'Company response to consumer'. Null 'Timely response?' rows excluded from the trainable set.
- **Candidate driver fields**: Product, Sub-product, Issue, Sub-issue
  (product/issue) + Submitted via, Company (process).
  `State - geographic control only, never a named primary driver.`
- **Out of scope**: every finding is a statistical **association**, never a causal claim
  (Every BP5 finding at every later gate is reported as a statistical ASSOCIATION between a real candidate driver field and a real outcome field - never a causal claim (Master Plan Section 5.1/7 and Section 9 UDAAP mapping for BP5).). Not intended for individual-level
  decisioning — BP5 is a population-level root-cause/driver analytics BP (see BP7 for the
  downstream, per-complaint decision-engine layer that consumes this BP's own Gate 5/6 output).

## Training Data
- **Source**: real CFPB complaints extract (no BANKING77 — Master Plan BP table: Integrates
  BANKING77? = NO), the same real structured fields already in scope for BP1-BP4.
- **Gold layer** (`data/processed/cfpb_root_cause_driver_gold.parquet`, live-read row count
  1048575, file
  mtime 2026-09-24T07:35:10.988222+00:00):
  - `outcome_1_intervention_required`: 815,453 trainable rows,
    10,511 positive (1.2890%)
  - `outcome_2_timely_response_failure`: 1,048,575 trainable rows,
    3,227 positive (0.3078%)
- **Leakage rules enforced** (Gate 1, re-verified live at every later gate — never relaxed):
  - 'Company response to consumer' defines outcome_1 and must never be a candidate driver for outcome_1; 'Timely response?' defines outcome_2 and must never be a candidate driver for outcome_2.
  - 'Company response to consumer' (outcome_1) barred as a candidate driver for outcome_2, and 'Timely response?' (outcome_2) barred as a candidate driver for outcome_1 - an outcome-echo risk, live-quantified in Section 6's overlap check, not classic leakage.
  - 'Date received' and 'Date sent to company' barred from the candidate driver set for BOTH outcomes as a conservative default - a computed response-time duration leaked BP2's own target on this identical data (BP2 Gate 3 finding), and outcome_2 is itself a timeliness judgment on these same two dates. Deferred to Gate 3 for an explicit test.
  - 'Tags' barred for both outcomes - live-re-checked (not assumed) and found to contain demographic-adjacent values, matching BP2/BP3/BP4's own real findings.
  - 'Company public response' excluded from the candidate driver set - real, live-verified null rate and outcome-adjacent content (see policy.json for the exact figures).
  - 'Complaint ID' and 'ZIP code' barred as identifier / quasi-identifier, matching BP2/BP3/BP4's own BARRED_COLUMNS precedent.
  - No BANKING77 data used at all for BP5 (Master Plan BP table: Integrates BANKING77? = NO).
  - Every BP5 finding at every later gate is reported as an ASSOCIATION, never a causal claim.

## Evaluation Data & Results
- **Held-out test set**: fresh stratified 80/20 split per outcome (CFPB ships no provided split),
  evaluated once per champion.
- **Bootstrap 95% CI** (1,000 resamples, Gate 4):
  - `outcome_1_intervention_required` ROC-AUC [0.9690,
    0.9720], PR-AUC
    [0.2376,
    0.2702]
  - `outcome_2_timely_response_failure` ROC-AUC [0.9474,
    0.9572], PR-AUC
    [0.0578,
    0.0880]
- **Calibration (Brier score, Gate 4)**: `outcome_1_intervention_required`=0.072676,
  `outcome_2_timely_response_failure`=0.099226
- **Confusion matrix @0.5 (Gate 4, diagnostic only — never a deployment threshold)**:
  - `outcome_1_intervention_required`: recall=0.9486, precision=
    0.1153
  - `outcome_2_timely_response_failure`: recall=0.9752, precision=
    0.0191

## Top Real Findings (Gate 5's own prioritized root-cause report — full detail and citations in
`notebooks/bp5_root_cause_driver_analytics/artifacts/gate5_prioritized_root_cause_report_outcome_1_intervention_required.json` /
`notebooks/bp5_root_cause_driver_analytics/artifacts/gate5_prioritized_root_cause_report_outcome_2_timely_response_failure.json`)

**`outcome_1_intervention_required`:**
  1. Field `Sub-issue` — Cramer's V=0.4156 (moderate, p=0)
  1. Field `Issue` — Cramer's V=0.4037 (moderate, p=0)
  1. Field `Sub-product` — Cramer's V=0.3523 (moderate, p=0)
  1. SHAP feature `Company_freq_zscored` — mean |SHAP|=1.6236
  1. SHAP feature `Issue_Incorrect information on your report` — mean |SHAP|=0.6490
  1. SHAP feature `Issue_Improper use of your report` — mean |SHAP|=0.5993

**`outcome_2_timely_response_failure`:**
  1. Field `Sub-product` — Cramer's V=0.1645 (weak, p=0)
  1. Field `Sub-issue` — Cramer's V=0.1514 (weak, p=0)
  1. Field `Issue` — Cramer's V=0.1489 (weak, p=0)
  1. SHAP feature `Company_freq_zscored` — mean |SHAP|=2.0926
  1. SHAP feature `Product_Credit reporting, credit repair services, or other personal consumer reports` — mean |SHAP|=0.3488
  1. SHAP feature `Issue_Incorrect information on your report` — mean |SHAP|=0.2618

## Ethical Considerations & Governance
- **UDAAP** is BP5's real, applicable compliance touchpoint (Master Plan Section 9). Gate 5's own
  mechanical language check on every generated narrative sentence passed:
  `udaap_language_check_passed=True`
  (76 sentences scanned).
- **ECOA/Reg B: Not Applicable to BP5** — Master Plan Section 9's Regulatory Frameworks table maps ECOA / Regulation B to BP1, BP2, BP3, and BP7 only - BP5 is explicitly NOT listed (re-verified against the full Master Plan document text, not the excerpt alone). Stated honestly as Not Applicable for BP5's own compliance touchpoint, rather than silently reusing BP3's ECOA/Reg B statement. 'Tags' is still barred from BP5's candidate driver set anyway, as a conservative scope decision (see leakage_rules), HYPER-consistent with BP3/BP4 Gate 1's own precedent of barring 'Tags' even where ECOA/Reg B does not map to the BP in question (BP4).
- **Barred-field diagnostics** (Gate 3's own real, disclosed diagnostic tests of fields Gate 1
  barred as a conservative default — these tests report real numbers for human governance review
  and NEVER relax the bar):
- `Timely response?` vs `outcome_1`: real diagnostic log-odds-ratio computed at Gate 3 (category 'No' vs reference 'Yes') — reported for human governance review only; the Gate 1 bar on this field as an outcome_1 driver is NOT relaxed.
- `_response_duration_days` (derived from `Date received`/`Date sent to company`) vs BOTH outcomes: real diagnostic univariate logistic association computed at Gate 3 — the Gate 1 bar on both date fields as candidate drivers is NOT relaxed.
- `Company response to consumer` vs `outcome_2`: real diagnostic chi-square/Cramer's V (strength: strong) computed at Gate 3 — an outcome-echo risk; the bar on this field as an outcome_2 driver is NOT relaxed.
- `bar_relaxed_by_this_notebook` (Gate 3's own recorded field): **False** — must be `False`; Section 4 above raises a RuntimeError rather than proceeding if it were ever `True`.
- **Association, never causation**: every finding at every gate carries
  `association_not_causation_disclaimer` verbatim — reproduced at the top of every saved artifact.

## Known Limitations (detected LIVE from real Gate 3/Gate 4 artifacts, not from memory)
### Negligible-strength candidate fields
- **`Submitted via` vs `outcome_1_intervention_required`**: real Cramer's V 0.0911 — negligible strength (p=0, n=815,453). A real, disclosed weak-signal finding, not an error - this field remains a tested candidate, never silently dropped.
- **`Submitted via` vs `outcome_2_timely_response_failure`**: real Cramer's V 0.0127 — negligible strength (p=2.772e-36, n=1,048,575). A real, disclosed weak-signal finding, not an error - this field remains a tested candidate, never silently dropped.

### Near-zero precision at the default 0.5 threshold
- **`outcome_2_timely_response_failure`**: real precision at the default 0.5 threshold is 0.0191 (< 0.05) despite real recall 0.9752 — both champions use `class_weight="balanced"` and this outcome's real, extreme class imbalance (0.3078% positive) means the 0.5 threshold selects a real high-recall/low-precision operating point (Gate 4's own disclosed diagnostic-threshold caveat - never tuned or presented as a deployment decision).

### Structural scope limitations (real, disclosed, unchanged from Gates 1-5)
- BP5 has **no persisted model bundle and no inference service** — it is an association-analytics
  BP, not a deployed-classifier BP (see Model Details above).
- BP5's own `methodology_policy` names only logistic regression — no multi-model CV benchmark the
  way BP1-3's Gate 3 runs one; there is no runner-up model and no paired significance test.
- `Company public response` was excluded from the candidate driver set entirely at Gate 1 given
  its real, live-verified null rate and outcome-adjacent content — not proven necessary, open to
  future review.

## Testing & Reproducibility (this Gate 6 run)
- **Full project pytest suite**: `[33m================ [32m325 passed[0m, [33m[1m3 skipped[0m, [33m[1m182 warnings[0m[33m in 9.51s[0m[33m =================[0m` (all passed: True)
- **Static notebook-syntax audit**: 51/51
  notebooks passed (all passed: True)
- BP5's own first-ever test coverage, delivered alongside this gate:
  `tests/bp5_root_cause_driver_analytics/test_bp5_driver_association.py` (unit coverage of every
  real function in `src/models/bp5_driver_association.py`) and
  `tests/bp5_root_cause_driver_analytics/test_gate_artifacts.py` (schema/cross-artifact
  consistency checks for Gates 1-6's real saved output).

## [Gate 1] Business Understanding & Policy — 2026-09-24T07:16:13.829757+00:00
- Live-verified real CFPB rows: 1,048,575
