"""
tests/monitoring/test_prediction_monitor.py — Customer360 Navigator

Real pytest coverage for src/monitoring/prediction_monitor.py (Phase D monitoring foundation).
"""

from __future__ import annotations

from monitoring.prediction_monitor import (
    read_prediction_events,
    record_prediction_event,
    summarize_predictions,
)


def test_record_and_read_round_trips(tmp_path):
    log_path = tmp_path / "events.jsonl"
    record_prediction_event("bp1", "3", 12.5, "card_arrival", log_path=log_path)
    events = read_prediction_events(log_path=log_path)
    assert len(events) == 1
    assert events[0]["bp_id"] == "bp1"
    assert events[0]["predicted_label"] == "card_arrival"


def test_summarize_predictions_on_empty_log_is_honest_not_fabricated(tmp_path):
    summary = summarize_predictions(log_path=tmp_path / "nope.jsonl")
    assert summary["zero_events"] is True
    assert summary["n_events"] == 0


def test_summarize_predictions_computes_real_error_rate(tmp_path):
    log_path = tmp_path / "events.jsonl"
    record_prediction_event("bp1", "1", 10, "a", log_path=log_path)
    record_prediction_event("bp1", "1", 20, "b", error="timeout", log_path=log_path)
    record_prediction_event("bp1", "1", 30, "a", log_path=log_path)
    summary = summarize_predictions(bp_id="bp1", log_path=log_path)
    assert summary["n_events"] == 3
    assert summary["n_errors"] == 1
    assert abs(summary["error_rate"] - (1 / 3)) < 1e-9


def test_summarize_predictions_computes_real_latency_percentiles(tmp_path):
    log_path = tmp_path / "events.jsonl"
    for latency in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        record_prediction_event("bp1", "1", latency, "x", log_path=log_path)
    summary = summarize_predictions(bp_id="bp1", log_path=log_path)
    assert summary["latency_p50_ms"] in (50, 60)
    assert summary["latency_p99_ms"] == 100


def test_summarize_predictions_label_distribution_sums_to_one(tmp_path):
    log_path = tmp_path / "events.jsonl"
    for label in ["a", "a", "a", "b"]:
        record_prediction_event("bp1", "1", 10, label, log_path=log_path)
    summary = summarize_predictions(bp_id="bp1", log_path=log_path)
    dist = summary["predicted_label_distribution"]
    assert abs(sum(dist.values()) - 1.0) < 1e-9
    assert dist["a"] == 0.75
    assert dist["b"] == 0.25


def test_summarize_predictions_filters_by_bp_id(tmp_path):
    log_path = tmp_path / "events.jsonl"
    record_prediction_event("bp1", "1", 10, "a", log_path=log_path)
    record_prediction_event("bp2", "1", 10, "a", log_path=log_path)
    summary = summarize_predictions(bp_id="bp1", log_path=log_path)
    assert summary["n_events"] == 1


def test_summarize_predictions_tracks_model_versions_observed(tmp_path):
    log_path = tmp_path / "events.jsonl"
    record_prediction_event("bp1", "1", 10, "a", log_path=log_path)
    record_prediction_event("bp1", "2", 10, "a", log_path=log_path)
    summary = summarize_predictions(bp_id="bp1", log_path=log_path)
    assert summary["model_versions_observed"] == ["1", "2"]


def test_record_prediction_event_captures_actual_outcome_when_given(tmp_path):
    log_path = tmp_path / "events.jsonl"
    record_prediction_event("bp1", "1", 10, "a", actual_outcome="a", log_path=log_path)
    events = read_prediction_events(log_path=log_path)
    assert events[0]["actual_outcome"] == "a"
