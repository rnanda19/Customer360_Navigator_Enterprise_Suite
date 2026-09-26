"""
tests/monitoring/test_alerting.py — Customer360 Navigator

Real pytest coverage for src/monitoring/alerting.py's pure threshold-evaluation logic.
"""

from __future__ import annotations

import pytest

from monitoring.alerting import Severity, evaluate_alert


def test_below_warning_threshold_is_ok():
    event = evaluate_alert("api_error_rate_pct", 0.1)
    assert event.severity == Severity.OK


def test_at_warning_threshold_is_warning():
    event = evaluate_alert("api_error_rate_pct", 1.0)
    assert event.severity == Severity.WARNING


def test_at_critical_threshold_is_critical():
    event = evaluate_alert("api_error_rate_pct", 5.0)
    assert event.severity == Severity.CRITICAL


def test_above_critical_threshold_is_critical():
    event = evaluate_alert("api_error_rate_pct", 50.0)
    assert event.severity == Severity.CRITICAL


def test_lower_is_worse_metric_flags_correctly():
    """adverse_impact_ratio: LOWER is worse - 0.139 (BP3's real number) must be CRITICAL."""
    event = evaluate_alert("adverse_impact_ratio", 0.139)
    assert event.severity == Severity.CRITICAL


def test_lower_is_worse_metric_passes_when_high():
    """BP7's real adverse_impact_ratio (0.908127) must be OK."""
    event = evaluate_alert("adverse_impact_ratio", 0.908127)
    assert event.severity == Severity.OK


def test_unknown_metric_raises_key_error():
    with pytest.raises(KeyError):
        evaluate_alert("totally_unconfigured_metric", 1.0)


def test_message_names_the_metric_value_and_thresholds():
    event = evaluate_alert("api_error_rate_pct", 5.0)
    assert "api_error_rate_pct" in event.message
    assert "5.0" in event.message
