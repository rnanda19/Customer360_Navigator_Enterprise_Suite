# Model Governance Policy (Phase D)

**Status: real, locally verified. Not yet committed or pushed.**

This policy is enforced in code by `src/mlops/governance.py`, not merely described here. Every
check this document describes is a real function call this project's test suite
(`tests/mlops/test_governance.py`) exercises against both passing and failing real inputs.

## What "governed" means for this project

A candidate model version is **governed** when, before it can be proposed for production
promotion (`src/mlops/promotion.py::promote_candidate()`), it has been checked against:

1. **A real performance threshold**, derived from that BP's own historically recorded metric
   (never an arbitrary round number with no anchor — see `MLOPS_ARCHITECTURE.md` §4).
2. **Required documentation fields** — `champion_model`, `trained_on`, `evaluated_on`,
   `intended_use` — each must be present and non-empty.

Both checks are run by `governance.validate_candidate(bp_id, metrics, documentation)`, which
returns a `GovernanceResult` whose `passed` field is `True` **only** when `reasons` is empty.
There is no code path to a silently-passing result: a BP with no threshold defined fails loudly
(`"No governance threshold set is defined for bp_id=..."`) rather than defaulting to a pass.

## Current real thresholds

| bp_id | Metric | Minimum | Real historical value it is anchored to |
|---|---|---|---|
| `bp1` | `held_out_test_accuracy` | 0.80 | 0.8224 (configs/bp1_customer_intent_classification.yaml, Gate 3/4/5) |
| `bp1` | `held_out_test_f1_macro` | 0.78 | 0.8221 |

**Only BP1 has a defined threshold set as of this delivery.** BP2's real champion (`xgboost`) has
no single scalar accuracy metric confirmed against its full config during this phase's gap
analysis (the config snippet inspected showed `champion_model` entries but not a directly
comparable scalar) — defining a threshold without first confirming the exact metric key against
the full config would risk anchoring to the wrong number, which this project's zero-fabrication
standard does not permit. This is tracked as a named follow-up, not silently skipped.

## Real rejection evidence

During this phase's local verification, a genuinely weaker BP1 candidate (a real refit on a
stratified 3-rows-per-class, 231-row subset of the real BANKING77 training data — not a
fabricated metric) scored a real `held_out_test_accuracy` of `0.397078`. Governance correctly
rejected it:

```
reasons: [
  "Metric 'held_out_test_accuracy'=0.397... is below the governance minimum of 0.8.",
  "Metric 'held_out_test_f1_macro'=0.391... is below the governance minimum of 0.78.",
]
```

Attempting to promote that candidate anyway raised `PromotionError`, exactly as designed — see
`MLOPS_TEST_REPORT.md` §3 for the full transcript.

## Every check is recorded, pass or fail

`governance.record_governance_check()` appends every check (not just passes) to
`governance/model_governance_log.jsonl`, append-only, never rewritten. This is separate from, and
complements, `src/mlops/audit_log.py`'s promotion/rollback trail — the governance log is the
record of what was *checked*; the audit log is the record of what was *decided and by whom*.

## Extending governance to another BP

Add an entry to `governance.MODEL_PERFORMANCE_THRESHOLDS` keyed by that BP's `bp_id`, anchored to
a real metric already recorded in that BP's `configs/*.yaml`. No other code change is required —
`validate_candidate()` is already generic across `bp_id`.
