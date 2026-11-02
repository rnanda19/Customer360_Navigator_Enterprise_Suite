# Model Promotion and Rollback (Phase D)

**Status: real, locally verified, including a rollback independently re-verified by re-querying
the registry. Not yet committed or pushed.**

This document describes `src/mlops/promotion.py`'s real state machine and the real evidence that
promotion, rejection, and rollback all work as designed.

## The state machine

```
candidate --(register_model_version)--> [no alias]
    |
    v
evaluate_candidate()  -- runs governance.validate_candidate() AND
    |                     champion_challenger.evaluate_challenger(),
    |                     records BOTH outcomes to the audit log, pass or fail
    v
require_explicit_approval(approved, actor, reason)  -- raises ValueError if actor
    |                                                   or reason is empty
    v
promote_candidate()  -- raises PromotionError unless:
    |                     (1) governance_result.passed is True, AND
    |                     (2) challenger_verdict.overall_pass is True, AND
    |                     (3) approval.approved is True
    v
champion (alias moved; previous holder re-aliased "previous_champion")
    |
    v (if needed)
rollback()  -- moves "champion" back to "previous_champion" (or an explicit
               target_version), re-aliasing the demoted version
```

## Why "requiring explicit authorization" is enforced in code, not just policy

Phase D's binding instruction was: *"Model Approval and Promotion ... requiring explicit
authorization before production promotion."* This is not a documentation promise — it is three
real, independent checks inside `promote_candidate()` and `require_explicit_approval()`:

- `require_explicit_approval()` raises `ValueError` if `actor` or `reason` is empty — there is no
  way to construct an "approved" `ApprovalDecision` anonymously or without a stated reason.
- `promote_candidate()` raises `PromotionError` if `approval.approved` is not `True`.
- `promote_candidate()` also raises `PromotionError` if the governance check or the
  champion-challenger verdict failed — approval alone is never sufficient; a human cannot approve
  around a failing automated check through this code path.

`tests/mlops/test_promotion.py::TestRequireExplicitApproval` and
`TestPromoteCandidate::test_promote_raises_if_approval_not_approved` exercise exactly this.

## Real end-to-end demonstration (local, against BP1)

Run and verified during this phase (full transcript in `MLOPS_TEST_REPORT.md` §3):

1. **v1** (real BANKING77 refit, `held_out_test_accuracy=0.822403`) — governance passed, no prior
   champion to compare against, approved by `rnanda19`, promoted. `champion` alias → `1`.
2. **v3** (real refit on a deliberately data-starved 231-row subset,
   `held_out_test_accuracy=0.397078`) — governance **correctly rejected** it; the subsequent
   attempt to call `promote_candidate()` anyway raised `PromotionError` naming the exact failing
   metrics. **Not promoted.**
3. **v2** (real refit, `random_state=7`, `held_out_test_accuracy=0.822403` — identical to v1,
   since this is a convex optimization problem with a single global optimum) — governance and
   champion-challenger both passed; approved by `rnanda19`; promoted. `champion` alias → `2`,
   `previous_champion` alias → `1`.
4. **Rollback** — `promotion.rollback("bp1", actor="rnanda19", reason="...", target_version="1")`
   was called. The result was **not trusted on its own report**: the registry was re-queried
   independently afterward via `registry.get_version_by_alias("bp1", "champion")`, which returned
   version `1` — confirming the rollback actually took effect, not merely that the function
   claimed success.
5. **Real smoke prediction** — the rolled-back champion's own MLflow-logged artifact (not a
   locally cached file, downloaded fresh via `mlflow.artifacts.download_artifacts()`) was loaded
   and used to predict a real test sentence ("I have not received my new card yet, what should I
   do?"), returning `card_arrival` with confidence `0.5034` — a correct, sensible prediction,
   confirming the restored version is not just aliased correctly but is actually usable.

## The real audit trail this produced

Every step above is recorded in `governance/audit_log.jsonl` (7 real entries for `bp1` as of this
delivery) and every governance check in `governance/model_governance_log.jsonl` (3 real entries).
Both logs are append-only JSON Lines, human-readable, and intentionally committed (not
gitignored) as real evidence — see `src/mlops/audit_log.py` and `src/mlops/governance.py`.

## Automated test coverage (synthetic data, isolated per-test registry)

`tests/mlops/test_promotion.py` (16 tests) covers every branch of the state machine above against
a tiny real `LogisticRegression` fit on synthetic data in an isolated, temp-sqlite MLflow store
per test — including `test_rollback_actually_restores_the_previous_champion_verified_by_requery`,
which — like the real BP1 demonstration above — re-queries the registry rather than trusting
`rollback()`'s own return value.
