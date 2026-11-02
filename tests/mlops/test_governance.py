"""
tests/mlops/test_governance.py — Customer360 Navigator

Real pytest coverage for src/mlops/governance.py.
"""

from __future__ import annotations

from mlops import governance

VALID_DOC = {
    "champion_model": "logistic_regression",
    "trained_on": "real BANKING77 train split",
    "evaluated_on": "real BANKING77 test split",
    "intended_use": "BP1 intent classification",
}


def test_candidate_meeting_every_threshold_and_doc_field_passes():
    result = governance.validate_candidate(
        "bp1", {"held_out_test_accuracy": 0.90, "held_out_test_f1_macro": 0.85}, VALID_DOC
    )
    assert result.passed is True
    assert result.reasons == []


def test_candidate_below_threshold_fails_with_a_specific_reason():
    result = governance.validate_candidate(
        "bp1", {"held_out_test_accuracy": 0.10, "held_out_test_f1_macro": 0.85}, VALID_DOC
    )
    assert result.passed is False
    assert any("held_out_test_accuracy" in r for r in result.reasons)


def test_candidate_missing_a_required_metric_fails():
    result = governance.validate_candidate("bp1", {"held_out_test_f1_macro": 0.85}, VALID_DOC)
    assert result.passed is False
    assert any("held_out_test_accuracy" in r and "missing" in r for r in result.reasons)


def test_candidate_missing_documentation_fields_fails():
    result = governance.validate_candidate(
        "bp1", {"held_out_test_accuracy": 0.90, "held_out_test_f1_macro": 0.85}, {"champion_model": "x"}
    )
    assert result.passed is False
    assert any("intended_use" in r for r in result.reasons)


def test_bp_id_with_no_threshold_defined_fails_loudly_not_silently():
    result = governance.validate_candidate("bp_with_no_threshold", {"anything": 1.0}, VALID_DOC)
    assert result.passed is False
    assert "No governance threshold" in result.reasons[0]


def test_custom_thresholds_override_default():
    custom = {"bp1": {"held_out_test_accuracy": 0.99}}
    result = governance.validate_candidate(
        "bp1", {"held_out_test_accuracy": 0.95}, VALID_DOC, thresholds=custom
    )
    assert result.passed is False


def test_record_and_read_governance_log_round_trips(tmp_path):
    log_path = tmp_path / "gov.jsonl"
    result = governance.validate_candidate(
        "bp1", {"held_out_test_accuracy": 0.90, "held_out_test_f1_macro": 0.85}, VALID_DOC
    )
    governance.record_governance_check(result, log_path=log_path)
    entries = governance.read_governance_log(log_path=log_path)
    assert len(entries) == 1
    assert entries[0]["bp_id"] == "bp1"
    assert entries[0]["passed"] is True


def test_read_governance_log_filters_by_bp_id(tmp_path):
    log_path = tmp_path / "gov.jsonl"
    r1 = governance.validate_candidate(
        "bp1", {"held_out_test_accuracy": 0.9, "held_out_test_f1_macro": 0.85}, VALID_DOC
    )
    governance.record_governance_check(r1, log_path=log_path)
    r2 = governance.GovernanceResult(bp_id="bp2", passed=False, reasons=["no threshold"])
    governance.record_governance_check(r2, log_path=log_path)
    bp1_entries = governance.read_governance_log(bp_id="bp1", log_path=log_path)
    assert len(bp1_entries) == 1
    assert bp1_entries[0]["bp_id"] == "bp1"


def test_read_governance_log_on_missing_file_returns_empty_list(tmp_path):
    assert governance.read_governance_log(log_path=tmp_path / "does_not_exist.jsonl") == []
