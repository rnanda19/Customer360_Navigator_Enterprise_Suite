"""
tests/mlops/test_promotion.py — Customer360 Navigator

Real pytest coverage for src/mlops/promotion.py - the candidate -> evaluation -> approval ->
promotion workflow and rollback, against a real (isolated, temp) sqlite-backed MLflow registry.
Phase D's explicit requirement to "verify that rollback works" is covered by
test_rollback_actually_restores_the_previous_champion_verified_by_requery below: it re-queries
the registry after rollback() returns, rather than trusting rollback()'s own report.
"""

from __future__ import annotations

import pytest

from mlops import audit_log, champion_challenger, governance, promotion, registry

VALID_DOC = {
    "champion_model": "logistic_regression",
    "trained_on": "x",
    "evaluated_on": "y",
    "intended_use": "z",
}
THRESHOLDS = {"bp_test_promo": {"accuracy": 0.6}}


def _passing_verdict():
    return champion_challenger.evaluate_challenger(
        "bp_test_promo", "accuracy", {"accuracy": 0.8}, {"accuracy": 0.8}
    )


def _failing_verdict():
    return champion_challenger.evaluate_challenger(
        "bp_test_promo", "accuracy", {"accuracy": 0.8}, {"accuracy": 0.1}
    )


class TestRequireExplicitApproval:
    def test_raises_without_actor(self):
        with pytest.raises(ValueError):
            promotion.require_explicit_approval(approved=True, actor="", reason="looks fine")

    def test_raises_without_reason(self):
        with pytest.raises(ValueError):
            promotion.require_explicit_approval(approved=True, actor="alice", reason="")

    def test_returns_decision_when_both_given(self):
        decision = promotion.require_explicit_approval(approved=True, actor="alice", reason="looks fine")
        assert decision.approved is True
        assert decision.actor == "alice"


class TestPromoteCandidate:
    def test_promote_raises_if_governance_failed(self, logged_run, monkeypatch, tmp_path):
        run_id, artifact_subpath = logged_run
        info = registry.register_model_version(
            bp_id="bp_test_promo",
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        gov_fail = governance.GovernanceResult(bp_id="bp_test_promo", passed=False, reasons=["too low"])
        approval = promotion.require_explicit_approval(approved=True, actor="alice", reason="r")
        with pytest.raises(promotion.PromotionError, match="governance"):
            promotion.promote_candidate(
                "bp_test_promo",
                info.version,
                governance_result=gov_fail,
                challenger_verdict=_passing_verdict(),
                approval=approval,
            )

    def test_promote_raises_if_challenger_verdict_failed(self, logged_run):
        run_id, artifact_subpath = logged_run
        info = registry.register_model_version(
            bp_id="bp_test_promo",
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        gov_pass = governance.GovernanceResult(bp_id="bp_test_promo", passed=True, reasons=[])
        approval = promotion.require_explicit_approval(approved=True, actor="alice", reason="r")
        with pytest.raises(promotion.PromotionError, match="champion-challenger"):
            promotion.promote_candidate(
                "bp_test_promo",
                info.version,
                governance_result=gov_pass,
                challenger_verdict=_failing_verdict(),
                approval=approval,
            )

    def test_promote_raises_if_approval_not_approved(self, logged_run):
        run_id, artifact_subpath = logged_run
        info = registry.register_model_version(
            bp_id="bp_test_promo",
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        gov_pass = governance.GovernanceResult(bp_id="bp_test_promo", passed=True, reasons=[])
        approval = promotion.require_explicit_approval(approved=False, actor="alice", reason="rejecting")
        with pytest.raises(promotion.PromotionError, match="approval"):
            promotion.promote_candidate(
                "bp_test_promo",
                info.version,
                governance_result=gov_pass,
                challenger_verdict=_passing_verdict(),
                approval=approval,
            )

    def test_successful_promotion_sets_champion_alias_and_records_audit_entry(
        self, logged_run, tmp_path, monkeypatch
    ):
        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setattr(audit_log, "AUDIT_LOG_PATH", audit_path)
        run_id, artifact_subpath = logged_run
        info = registry.register_model_version(
            bp_id="bp_test_promo_ok",
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        gov_pass = governance.GovernanceResult(bp_id="bp_test_promo_ok", passed=True, reasons=[])
        approval = promotion.require_explicit_approval(approved=True, actor="alice", reason="first promotion")
        verdict = champion_challenger.evaluate_challenger(
            "bp_test_promo_ok", "accuracy", {"accuracy": 0.8}, {"accuracy": 0.8}
        )
        result = promotion.promote_candidate(
            "bp_test_promo_ok",
            info.version,
            governance_result=gov_pass,
            challenger_verdict=verdict,
            approval=approval,
        )
        assert result["promoted_version"] == info.version
        champion = registry.get_version_by_alias("bp_test_promo_ok", "champion")
        assert champion.version == info.version
        entries = audit_log.read_log(bp_id="bp_test_promo_ok", log_path=audit_path)
        assert any(e["event_type"] == "promotion" and e["actor"] == "alice" for e in entries)

    def test_second_promotion_demotes_prior_champion_to_previous_champion(
        self, logged_run, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
        run_id, artifact_subpath = logged_run
        bp_id = "bp_test_promo_demote"
        v1 = registry.register_model_version(
            bp_id=bp_id,
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        v2 = registry.register_model_version(
            bp_id=bp_id,
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.85},
        )
        gov_pass = governance.GovernanceResult(bp_id=bp_id, passed=True, reasons=[])
        verdict = champion_challenger.evaluate_challenger(
            bp_id, "accuracy", {"accuracy": 0.8}, {"accuracy": 0.8}
        )
        approval = promotion.require_explicit_approval(approved=True, actor="alice", reason="v1")
        promotion.promote_candidate(
            bp_id, v1.version, governance_result=gov_pass, challenger_verdict=verdict, approval=approval
        )

        approval2 = promotion.require_explicit_approval(approved=True, actor="bob", reason="v2 beats v1")
        promotion.promote_candidate(
            bp_id, v2.version, governance_result=gov_pass, challenger_verdict=verdict, approval=approval2
        )

        assert registry.get_version_by_alias(bp_id, "champion").version == v2.version
        assert registry.get_version_by_alias(bp_id, "previous_champion").version == v1.version


class TestRollback:
    def test_rollback_raises_if_nothing_to_roll_back_to(self, mlflow_tracking_uri):
        registry.ensure_registered_model("bp_test_rollback_empty")
        with pytest.raises(promotion.PromotionError, match="nothing real to roll back to"):
            promotion.rollback("bp_test_rollback_empty", actor="alice", reason="trying anyway")

    def test_rollback_requires_actor_and_reason(self, mlflow_tracking_uri):
        with pytest.raises(ValueError):
            promotion.rollback("bp_test_rollback_noauth", actor="", reason="r")

    def test_rollback_actually_restores_the_previous_champion_verified_by_requery(
        self, logged_run, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
        run_id, artifact_subpath = logged_run
        bp_id = "bp_test_rollback_real"
        v1 = registry.register_model_version(
            bp_id=bp_id,
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        v2 = registry.register_model_version(
            bp_id=bp_id,
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.85},
        )
        gov_pass = governance.GovernanceResult(bp_id=bp_id, passed=True, reasons=[])
        verdict = champion_challenger.evaluate_challenger(
            bp_id, "accuracy", {"accuracy": 0.8}, {"accuracy": 0.8}
        )

        promotion.promote_candidate(
            bp_id,
            v1.version,
            governance_result=gov_pass,
            challenger_verdict=verdict,
            approval=promotion.require_explicit_approval(approved=True, actor="a", reason="r1"),
        )
        promotion.promote_candidate(
            bp_id,
            v2.version,
            governance_result=gov_pass,
            challenger_verdict=verdict,
            approval=promotion.require_explicit_approval(approved=True, actor="a", reason="r2"),
        )

        assert registry.get_version_by_alias(bp_id, "champion").version == v2.version

        rb = promotion.rollback(bp_id, actor="oncall_alice", reason="v2 regressed in production, reverting.")

        # Independent re-query, not trusting rollback()'s own return value:
        current_champion = registry.get_version_by_alias(bp_id, "champion")
        assert current_champion.version == v1.version
        assert rb["rolled_back_to_version"] == v1.version

        entries = audit_log.read_log(bp_id=bp_id, event_type="rollback", log_path=tmp_path / "audit.jsonl")
        assert len(entries) == 1
        assert entries[0]["actor"] == "oncall_alice"

    def test_rollback_to_explicit_target_version(self, logged_run, tmp_path, monkeypatch):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
        run_id, artifact_subpath = logged_run
        bp_id = "bp_test_rollback_explicit"
        v1 = registry.register_model_version(
            bp_id=bp_id,
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": 0.8},
        )
        registry.set_alias(bp_id, "champion", v1.version)
        rb = promotion.rollback(bp_id, actor="alice", reason="explicit target", target_version=v1.version)
        assert rb["rolled_back_to_version"] == v1.version
        assert registry.get_version_by_alias(bp_id, "champion").version == v1.version
