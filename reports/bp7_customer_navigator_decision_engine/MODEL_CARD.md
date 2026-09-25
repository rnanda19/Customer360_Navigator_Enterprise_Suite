# Model Card — BP7 Customer Navigator Decision Engine

*Generated 2026-09-25T06:49:02.757522+00:00 by
`bp7_customer_navigator_decision_engine_g6_productization_monitoring_governance.ipynb`,
deterministically, from real values recorded by BP7 Gates 1-5's own real runs on this machine plus
this gate's own real FastAPI self-test. No field below was authored freeform or by a generative
model (project zero-fabrication rule) - BP7 itself never calls a GenAI API at any gate.*

## Model Details
- **Nature of this BP**: a deterministic, transparent weighted-rule decision engine combining
  BP2/BP3/BP4's own already-computed, already-validated prediction fields into
  `priority_score`/`intervention_flag`/`recommended_action`/`reason_codes` for every real CFPB
  complaint - **not** a trained classifier and **not** a live model/API call at request time
  (contrast BP1-3's inference services and BP6's real Gemini call). Architecturally closer to BP4
  (read-only lookup over a real, persisted decision artifact) than to BP6.
- **Champion rule scheme** (Gate 3, independently reproduced at Gate 4, re-scored fresh on the
  full real population at Gate 5): `correlation_aware_plus_lr_diagnostic`, real
  normalized weights `{'bp2': 0.2227139837335739, 'bp3': 0.17077431022015202, 'bp4': 0.606511706046274}`, real intervention
  threshold 0.5.
- **Full real population scored**: 1,048,575 real CFPB complaints,
  100% coverage (every row receives a real priority_score or the honest
  `UNSCORED_MISSING_UPSTREAM_INPUT` sentinel - never a fabricated value for an unjoinable row).

## Intended Use
- Computes a transparent, auditable priority/intervention/action decision for every real customer
  complaint, keyed by `Complaint ID`, for downstream review-queue routing - never a black-box
  score passed through unmodified, and `recommended_action` is always a deterministic,
  reason-code-keyed lookup, never GenAI-generated text (Gate 1's own policy.json, re-verified live
  by this gate's own Section 4).
- Out of scope: BP7 makes no prediction of its own and calls no external API at any gate - it
  only recombines BP1-BP5's own already-validated outputs under a documented, auditable formula.

## Evaluation Data & Results (Gate 3/4/5, re-verified live by this gate's own Section 4)
- **Real intervention_flag_rate**: 0.768415 (Gate 4's own
  real bootstrap 95% CI: [0.767609, 0.769243])
- **Real bp3_agreement_rate** (coherence sanity check against BP3's own already-validated
  prediction, never an accuracy claim - `customer360_priority_decision` has no labeled ground
  truth): 0.285865
- **Real contribution-decomposition reconstruction**: exact within floating-point tolerance
  (`contribution_bp2 + contribution_bp3 + contribution_bp4` reconstructs `priority_score` exactly
  for every real scored row - re-verified live on the currently saved artifact by this gate).
- **Real disparate-impact audit** (ECOA/Reg B monitoring signal, not a legal determination):
  adverse_impact_ratio=0.908127,
  flagged_four_fifths_rule=False (re-verified live by
  this gate's own Section 4 as a hard regression guard - Gate 6 refuses to certify if this ever
  flips to True on the currently saved artifact).

## Governance — Master Plan Paragraph 205 (BP6/BP7-specific requirement)
- **MODEL_CARD.md / CHANGELOG.md**: this file and its sibling, generated deterministically by this
  gate from Gates 1-5's own real recorded values.
- **Runnable FastAPI service**: `src/services/bp7_decision_engine_service.py` (`/`, `/health`,
  `/decide/{complaint_id}`, `/decide/self-test`) - Docker packaging at
  `src/services/docker/bp7_decision_engine_service/`.
- **Live self-test proving API output matches direct computation**: run for real by this gate
  (Section 9) - adapted for BP7's no-external-API nature: a real internal-consistency check over
  100 real, already-scored rows (contribution reconstruction,
  threshold-consistency, recommended_action vocabulary/structural consistency, and dual
  independent-read identity), all local, zero external network calls:
  `all_checks_passed=True`. See the service module's own
  docstring for why this - not a network-mocked replay of BP6's own Gemini-call pattern - is the
  honest proof for a BP that calls no external API anywhere.

## Ethical Considerations & Governance
- **ECOA/Reg B**: applicable (Master Plan Section 9). Gate 5's own real, full-population
  disparate-impact audit, re-verified live by this gate:
  adverse_impact_ratio=0.908127,
  flagged_four_fifths_rule=False - a monitoring signal
  for a human reviewer, never a legal determination of compliance (the identical limitation every
  upstream BP's own Gate 4/5 stated, not softened here).
- **UDAAP / NIST AI RMF**: Not Applicable to BP7 (Gate 1's own policy.json) -
  `recommended_action` is a deterministic, reason-code-keyed lookup, never GenAI-generated
  customer-facing text. Real GenAI-drafted text stays scoped to BP6 per the Master Plan.
- **No barred field used**: BP7's own real, live leakage re-check (Gate 4, re-verified live by
  this gate's own Section 4) confirms `leakage_reconfirmed_clean=True`.

## Known Limitations (detected LIVE from real Gate 3/4/5 artifacts, not from memory)
- **Real bugs found and fixed during this Gate 6 deliverable's own pre-delivery sandbox testing**
  (never run against the real device, per this project's standing execution-boundary rule - a
  synthetic, real-schema fixture only): (1) FastAPI route registration order - `/decide/{complaint_id}`
  was initially registered before `/decide/self-test`, which caused Starlette to attempt to
  int-parse the literal string `"self-test"` and return 422 instead of reaching the self-test
  endpoint; fixed by registering `/decide/self-test` first. (2) The self-test's per-row
  contribution-reconstruction check initially reported `False` for a real, structurally-honest
  unscored row (null `priority_score`, `UNSCORED_MISSING_UPSTREAM_INPUT`) - there is nothing to
  reconstruct for such a row, so this was a false-positive failure, not a real defect; fixed to
  treat a null-`priority_score` row as vacuously consistent, matching
  `summarize_contribution_decomposition()`'s own aggregate semantics exactly.
- **BP4 join coverage is not 100%**: 0.024632 real fraction of rows carry
  `bp4_join_status=UNSCORED_MISSING_UPSTREAM_INPUT` (Gate 2's own real join coverage finding,
  carried forward - never silently defaulted to a fabricated BP4 tier).
- **BP1's optional context coverage is low**: 6.5527%
  of real rows have a real BANKING77-taxonomy-crosswalk context available (Gate 1's own
  `OPTIONAL_CONTEXT_ONLY` scoping - BP1 is never a CORE_INPUT to `priority_score` itself).
- **This service's own real dependency footprint is heavier than BP4's** (contrast BP4's minimal
  fastapi/pydantic/polars list): `/decide/self-test` reuses Gate 4/5's own real
  `summarize_contribution_decomposition()` function rather than reimplementing its arithmetic
  inline, which transitively pulls in the shared BP2/BP3/BP4 feature-module chain
  (scikit-learn/scipy/joblib/PyYAML) - a disclosed, deliberate reuse-over-minimalism trade-off,
  documented in the service's own Dockerfile header.

## Testing & Reproducibility (this Gate 6 run)
- **Full project pytest suite**: `[33m================ [32m410 passed[0m, [33m[1m3 skipped[0m, [33m[1m182 warnings[0m[33m in 13.74s[0m[33m ================[0m` (all passed: True)
- **Static notebook-syntax audit**: returncode=0 (all passed: True)
- **Real FastAPI self-test**: all_checks_passed=True over
  100 real rows, zero external network calls
- BP7's own first-ever dedicated test coverage, delivered alongside this gate:
  `tests/services/test_bp7_decision_engine_service.py` (the FastAPI service's own CI-safe suite -
  no network call anywhere, so nothing to mock, unlike BP6's own Gemini-boundary mocks) and
  `tests/bp7_customer_navigator_decision_engine/test_gate_artifacts.py` (schema/cross-artifact
  consistency checks for Gates 1-6's real saved output).

## [Gate 1] Business Understanding & Policy — 2026-09-25T06:12:08.692639+00:00
- BP7 scope, output-field definitions, and leakage rules defined; `recommended_action` is a
  deterministic, reason-code-keyed lookup, never GenAI - re-confirmed live by this gate.
