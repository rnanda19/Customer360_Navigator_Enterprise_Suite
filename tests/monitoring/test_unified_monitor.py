"""
tests/monitoring/test_unified_monitor.py — Customer360 Navigator

Real pytest coverage for src/monitoring/unified_monitor.py (Master Engineering Directive,
Phase G). Every test uses real tmp_path-isolated JSONL logs for anything written to disk -
never this project's real governance/ files - except the two fairness tests, which deliberately
read this project's real, already-committed BP3/BP7 Gate 4 JSON artifacts (the same files
fairness_monitor.py's own existing tests already read), since that is real repository evidence,
not a fixture to fabricate.
"""

from __future__ import annotations

from monitoring import prediction_monitor as pm
from monitoring import unified_monitor as um
from monitoring.alerting import Severity

# ---- validate_input_schema ----------------------------------------------------------------


def test_validate_input_schema_rejects_empty_batch():
    result = um.validate_input_schema([], bp_id="bp_x", required_columns=("a",))
    assert result.n_records == 0
    assert result.schema_valid is False
    assert "No records supplied." in result.reasons


def test_validate_input_schema_detects_missing_required_column():
    records = [{"a": 1}, {"a": 2}]
    result = um.validate_input_schema(records, bp_id="bp_x", required_columns=("a", "b"))
    assert result.schema_valid is False
    assert result.missing_required_columns == ["b"]


def test_validate_input_schema_computes_real_missing_value_rates():
    records = [{"a": 1, "b": None}, {"a": 2, "b": 5}, {"a": None, "b": 7}]
    result = um.validate_input_schema(records, bp_id="bp_x", required_columns=("a", "b"))
    assert result.schema_valid is True
    assert result.missing_value_rates == {"a": 1 / 3, "b": 1 / 3}


def test_validate_input_schema_detects_real_duplicates():
    records = [{"a": 1}, {"a": 1}, {"a": 2}]
    result = um.validate_input_schema(records, bp_id="bp_x", required_columns=("a",))
    assert result.duplicate_row_count == 1
    assert any("duplicate" in r for r in result.reasons)


# ---- compute_prediction_drift ---------------------------------------------------------------


def test_drift_insufficient_data_when_either_window_empty(tmp_path):
    cur = tmp_path / "cur.jsonl"
    ref = tmp_path / "ref.jsonl"
    pm.record_prediction_event("bp_x", "v1", 10.0, "A", log_path=cur)
    result = um.compute_prediction_drift("bp_x", reference_log_path=ref, current_log_path=cur)
    assert result["status"] == "insufficient_data"


def test_drift_insufficient_data_below_min_events(tmp_path):
    cur = tmp_path / "cur.jsonl"
    ref = tmp_path / "ref.jsonl"
    for _ in range(2):
        pm.record_prediction_event("bp_x", "v1", 10.0, "A", log_path=cur)
        pm.record_prediction_event("bp_x", "v1", 10.0, "A", log_path=ref)
    result = um.compute_prediction_drift("bp_x", reference_log_path=ref, current_log_path=cur, min_events=5)
    assert result["status"] == "insufficient_data"


def test_drift_computed_real_psi_above_min_events(tmp_path):
    cur = tmp_path / "cur.jsonl"
    ref = tmp_path / "ref.jsonl"
    for i in range(10):
        pm.record_prediction_event("bp_x", "v1", 10.0, "A", log_path=ref)
        pm.record_prediction_event("bp_x", "v1", 10.0, "A" if i < 5 else "B", log_path=cur)
    result = um.compute_prediction_drift("bp_x", reference_log_path=ref, current_log_path=cur)
    assert result["status"] == "computed"
    assert result["population_stability_index"] > 0
    assert result["reference_n_events"] == 10
    assert result["current_n_events"] == 10


# ---- model_performance_status ----------------------------------------------------------------


def test_model_performance_awaiting_ground_truth_with_no_events(tmp_path):
    result = um.model_performance_status("bp_x", log_path=tmp_path / "empty.jsonl")
    assert result["status"] == "awaiting_ground_truth"


def test_model_performance_awaiting_ground_truth_when_no_outcome_logged(tmp_path):
    log_path = tmp_path / "events.jsonl"
    pm.record_prediction_event("bp_x", "v1", 10.0, "A", log_path=log_path)
    result = um.model_performance_status("bp_x", log_path=log_path)
    assert result["status"] == "awaiting_ground_truth"
    assert result["n_events"] == 1


def test_model_performance_computed_real_accuracy_on_labeled_subset(tmp_path):
    log_path = tmp_path / "events.jsonl"
    pm.record_prediction_event("bp_x", "v1", 10.0, "A", actual_outcome="A", log_path=log_path)
    pm.record_prediction_event("bp_x", "v1", 10.0, "B", actual_outcome="A", log_path=log_path)
    pm.record_prediction_event("bp_x", "v1", 10.0, "C", log_path=log_path)  # no ground truth
    result = um.model_performance_status("bp_x", log_path=log_path)
    assert result["status"] == "computed"
    assert result["n_events_with_ground_truth"] == 2
    assert result["accuracy_on_labeled_subset"] == 0.5


# ---- fairness_status (real repository evidence - BP3/BP7 only) ------------------------------


def test_fairness_not_applicable_for_a_bp_with_no_real_check():
    result = um.fairness_status("bp1")
    assert result["status"] == "not_applicable"


def test_fairness_computed_for_bp3_from_real_committed_gate4_artifact():
    result = um.fairness_status("bp3")
    assert result["status"] == "computed"
    assert result["check"]["bp"] == "BP3"
    assert "adverse_impact_ratio" in result["check"]


def test_fairness_computed_for_bp7_from_real_committed_gate4_artifact():
    result = um.fairness_status("bp7")
    assert result["status"] == "computed"
    assert result["check"]["bp"] == "BP7"


# ---- evaluate_real_alerts / alert audit trail ------------------------------------------------


def test_evaluate_real_alerts_skips_metrics_not_supplied():
    events = um.evaluate_real_alerts(error_rate=0.5)
    assert len(events) == 1
    assert events[0].metric_name == "api_error_rate_pct"


def test_evaluate_real_alerts_raises_real_severity_from_real_value():
    events = um.evaluate_real_alerts(adverse_impact_ratio=0.5)
    assert events[0].severity == Severity.CRITICAL


def test_record_and_read_alert_audit_log_round_trips(tmp_path):
    log_path = tmp_path / "alerts.jsonl"
    events = um.evaluate_real_alerts(error_rate=10.0)
    um.record_alert_events(events, bp_id="bp_x", log_path=log_path)
    entries = um.read_alert_audit_log(bp_id="bp_x", log_path=log_path)
    assert len(entries) == 1
    assert entries[0]["severity"] == "CRITICAL"


def test_read_alert_audit_log_filters_by_bp_id(tmp_path):
    log_path = tmp_path / "alerts.jsonl"
    um.record_alert_events(um.evaluate_real_alerts(error_rate=0.1), bp_id="bp_a", log_path=log_path)
    um.record_alert_events(um.evaluate_real_alerts(error_rate=0.1), bp_id="bp_b", log_path=log_path)
    assert len(um.read_alert_audit_log(bp_id="bp_a", log_path=log_path)) == 1
    assert len(um.read_alert_audit_log(log_path=log_path)) == 2


# ---- run_monitoring_cycle: full real composition ----------------------------------------------


def test_run_monitoring_cycle_full_composition_writes_one_structured_event(tmp_path):
    cur = tmp_path / "cur.jsonl"
    ref = tmp_path / "ref.jsonl"
    events_log = tmp_path / "events.jsonl"
    alert_log = tmp_path / "alerts.jsonl"

    for i in range(10):
        pm.record_prediction_event("bp_cycle", "v1", 50.0, "A" if i < 8 else "B", log_path=cur)
    for _ in range(10):
        pm.record_prediction_event("bp_cycle", "v1", 50.0, "A", log_path=ref)

    result = um.run_monitoring_cycle(
        "bp_cycle",
        current_log_path=cur,
        reference_log_path=ref,
        input_records=[{"x": 1}],
        required_columns=("x", "y"),
        events_log_path=events_log,
        alert_log_path=alert_log,
    )

    assert result.bp_id == "bp_cycle"
    assert result.prediction_summary["n_events"] == 10
    assert result.data_quality["schema_valid"] is False
    assert result.drift["status"] == "computed"
    assert result.fairness["status"] == "not_applicable"
    assert result.model_performance["status"] == "awaiting_ground_truth"
    assert len(result.alerts) >= 1

    written = events_log.read_text().strip().splitlines()
    assert len(written) == 1
    import json

    on_disk = json.loads(written[0])
    assert on_disk["bp_id"] == "bp_cycle"

    assert len(um.read_alert_audit_log(bp_id="bp_cycle", log_path=alert_log)) == len(result.alerts)


def test_run_monitoring_cycle_without_reference_window_skips_drift(tmp_path):
    cur = tmp_path / "cur.jsonl"
    events_log = tmp_path / "events.jsonl"
    alert_log = tmp_path / "alerts.jsonl"
    pm.record_prediction_event("bp_no_drift", "v1", 10.0, "A", log_path=cur)

    result = um.run_monitoring_cycle(
        "bp_no_drift", current_log_path=cur, events_log_path=events_log, alert_log_path=alert_log
    )
    assert result.drift is None
    assert result.data_quality is None


def test_run_monitoring_cycle_defaults_to_the_real_prediction_monitor_log_path(tmp_path, monkeypatch):
    """Proves the None-default-resolved-dynamically convention actually works inside
    unified_monitor.py itself: monkeypatching prediction_monitor.PREDICTION_LOG_PATH changes what
    run_monitoring_cycle reads from when no explicit current_log_path is passed - exactly the fix
    applied after Phase D/E hit the opposite (broken) pattern twice.

    Note: prediction_monitor.record_prediction_event's own log_path parameter still uses the
    OLD (signature-default-bound-at-import-time) pattern - that module is pre-existing Phase D
    code, not touched by this unified_monitor.py change - so monkeypatching
    pm.PREDICTION_LOG_PATH does NOT change record_prediction_event's own default. We pass
    log_path=fake_log explicitly here to populate the fake log, which isolates the assertion to
    what this test actually targets: run_monitoring_cycle's OWN dynamic-default resolution."""
    fake_log = tmp_path / "default_location.jsonl"
    monkeypatch.setattr(pm, "PREDICTION_LOG_PATH", fake_log)
    pm.record_prediction_event("bp_default", "v1", 10.0, "A", log_path=fake_log)

    events_log = tmp_path / "events.jsonl"
    alert_log = tmp_path / "alerts.jsonl"
    result = um.run_monitoring_cycle("bp_default", events_log_path=events_log, alert_log_path=alert_log)
    assert result.prediction_summary["n_events"] == 1
