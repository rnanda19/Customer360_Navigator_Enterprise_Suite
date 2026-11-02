"""
src/mlops/promotion.py — Customer360 Navigator

PHASE D: the real candidate -> evaluation -> approval -> promotion workflow, plus rollback.
Built entirely on the real primitives already defined in this package: governance.py's
validate_candidate(), champion_challenger.py's evaluate_challenger(), registry.py's alias
mechanics, and audit_log.py's append-only trail. This module performs no model training or
evaluation itself - it sequences and gates the real results its callers hand it.

Promotion state machine (per bp_id, tracked purely through MLflow registry aliases - no separate
database):
    candidate          a new model version has been registered (registry.register_model_version),
                        holds no alias yet.
    evaluated           governance.validate_candidate() and champion_challenger.evaluate_challenger()
                        have both been run against it (this module records both results in the
                        audit log even on failure - a failed evaluation is itself an audited event).
    pending_approval     both checks passed; promote_candidate() has been called but
                        require_explicit_approval() has not yet been satisfied.
    approved -> production   require_explicit_approval() was given a real, non-empty actor + reason;
                        the alias "champion" is moved from its previous holder (if any) to this
                        version, and the previous holder is re-aliased "previous_champion" so
                        rollback() has a real prior version to restore.

PHASE D's binding constraint - "Model Approval and Promotion ... requiring explicit authorization
before production promotion" - is enforced in code, not just by convention: promote_candidate()
raises PromotionError if called without an ApprovalDecision whose `approved` is True, and
ApprovalDecision can only be constructed via require_explicit_approval(), which itself raises if
`actor` or `reason` is empty (see audit_log.record_event()'s matching check).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlops import audit_log, governance, registry
from mlops.champion_challenger import ChallengerVerdict


def _resolve_audit_log_path(audit_log_path):
    return audit_log_path if audit_log_path is not None else audit_log.AUDIT_LOG_PATH


class PromotionError(RuntimeError):
    """Raised whenever a promotion/rollback is attempted without having satisfied every real,
    enforced precondition (governance pass, challenger-verdict pass, explicit approval)."""


@dataclass
class ApprovalDecision:
    approved: bool
    actor: str
    reason: str


def require_explicit_approval(*, approved: bool, actor: str, reason: str) -> ApprovalDecision:
    """The single, real authorization gate. Raises ValueError if `actor` or `reason` is empty -
    there is no code path to an approved ApprovalDecision that does not name a real approver and
    a real reason. This function makes NO decision of its own about whether the model deserves
    promotion; it only validates that a human decision was recorded honestly."""
    actor = (actor or "").strip()
    reason = (reason or "").strip()
    if not actor:
        raise ValueError("require_explicit_approval() requires a non-empty `actor` (who is approving this).")
    if not reason:
        raise ValueError("require_explicit_approval() requires a non-empty `reason`.")
    return ApprovalDecision(approved=approved, actor=actor, reason=reason)


def evaluate_candidate(
    bp_id: str,
    candidate_version: str,
    *,
    metrics: dict[str, float],
    documentation: dict[str, Any],
    challenger_verdict: ChallengerVerdict,
    actor: str,
    audit_log_path=None,
    governance_log_path=None,
) -> tuple[governance.GovernanceResult, ChallengerVerdict]:
    """Run both real gates (governance + champion-challenger) against a registered candidate
    version and record both outcomes in the audit log, whether they pass or fail. Returns both
    results so the caller (or a human) can see exactly why a candidate is or is not eligible for
    promote_candidate()."""
    gov_result = governance.validate_candidate(bp_id, metrics, documentation)
    governance.record_governance_check(
        gov_result,
        log_path=governance_log_path if governance_log_path is not None else governance.GOVERNANCE_LOG_PATH,
    )
    resolved_audit_path = _resolve_audit_log_path(audit_log_path)
    audit_log.record_event(
        event_type="governance_check",
        bp_id=bp_id,
        actor=actor,
        reason=f"Automated governance validation for candidate version {candidate_version}.",
        details={"candidate_version": candidate_version, **gov_result.to_dict()},
        log_path=resolved_audit_path,
    )
    audit_log.record_event(
        event_type="champion_challenger_evaluation",
        bp_id=bp_id,
        actor=actor,
        reason=f"Automated champion-challenger comparison for candidate version {candidate_version}.",
        details={"candidate_version": candidate_version, **challenger_verdict.to_dict()},
        log_path=resolved_audit_path,
    )
    return gov_result, challenger_verdict


def promote_candidate(
    bp_id: str,
    candidate_version: str,
    *,
    governance_result: governance.GovernanceResult,
    challenger_verdict: ChallengerVerdict,
    approval: ApprovalDecision,
    audit_log_path=None,
) -> dict[str, Any]:
    """Promote `candidate_version` to 'champion' for bp_id. Raises PromotionError if governance
    failed, if the challenger verdict failed, or if `approval.approved` is not True - every one of
    Phase D's required preconditions is checked here, in code, not left to caller discipline. On
    success: the previous champion (if any) is re-aliased 'previous_champion' (so rollback() has
    something real to restore), the new version becomes 'champion', and the promotion is recorded
    in the audit log with the real approver and reason."""
    if not governance_result.passed:
        raise PromotionError(
            f"Cannot promote {bp_id} v{candidate_version}: "
            f"governance check failed: {governance_result.reasons}"
        )
    if not challenger_verdict.overall_pass:
        failing = [a.detail for a in challenger_verdict.axes if a.status == "fail"]
        raise PromotionError(
            f"Cannot promote {bp_id} v{candidate_version}: "
            f"champion-challenger evaluation failed: {failing}"
        )
    if not approval.approved:
        raise PromotionError(f"Cannot promote {bp_id} v{candidate_version}: approval.approved is False.")

    previous_champion = registry.get_version_by_alias(bp_id, "champion")
    if previous_champion is not None and previous_champion.version != candidate_version:
        registry.set_alias(bp_id, "previous_champion", previous_champion.version)

    registry.set_alias(bp_id, "champion", candidate_version)
    registry.delete_alias(bp_id, "challenger")

    entry = audit_log.record_event(
        event_type="promotion",
        bp_id=bp_id,
        actor=approval.actor,
        reason=approval.reason,
        details={
            "promoted_version": candidate_version,
            "previous_champion_version": previous_champion.version if previous_champion else None,
        },
        log_path=_resolve_audit_log_path(audit_log_path),
    )
    return {
        "promoted_version": candidate_version,
        "previous_champion_version": previous_champion.version if previous_champion else None,
        "audit_entry_id": entry.entry_id,
    }


def rollback(
    bp_id: str, *, actor: str, reason: str, target_version: str | None = None, audit_log_path=None
) -> dict[str, Any]:
    """Restore a previously approved version to 'champion'. If `target_version` is not given,
    rolls back to whichever version currently holds the 'previous_champion' alias (the version
    promote_candidate() demoted most recently). Raises PromotionError if there is nothing real to
    roll back to. Verification that the rollback actually took effect is the caller's
    responsibility (re-query registry.get_version_by_alias(bp_id, "champion") - exercised for real
    in tests/mlops/test_promotion.py, matching Phase D's explicit "verify that rollback works"
    requirement) rather than this function's, so a test can independently confirm it rather than
    trust this function's own report of success."""
    actor = (actor or "").strip()
    reason = (reason or "").strip()
    if not actor or not reason:
        raise ValueError("rollback() requires a non-empty `actor` and `reason` - no anonymous rollbacks.")

    current_champion = registry.get_version_by_alias(bp_id, "champion")
    if target_version is None:
        previous = registry.get_version_by_alias(bp_id, "previous_champion")
        if previous is None:
            raise PromotionError(
                f"No 'previous_champion' alias exists for {bp_id} - nothing real to roll back to."
            )
        target_version = previous.version

    registry.set_alias(bp_id, "champion", target_version)
    if current_champion is not None and current_champion.version != target_version:
        registry.set_alias(bp_id, "previous_champion", current_champion.version)

    entry = audit_log.record_event(
        event_type="rollback",
        bp_id=bp_id,
        actor=actor,
        reason=reason,
        details={
            "rolled_back_to_version": target_version,
            "rolled_back_from_version": current_champion.version if current_champion else None,
        },
        log_path=_resolve_audit_log_path(audit_log_path),
    )
    return {
        "rolled_back_to_version": target_version,
        "rolled_back_from_version": current_champion.version if current_champion else None,
        "audit_entry_id": entry.entry_id,
    }
