"""
tests/monitoring/test_fairness_monitor.py — Customer360 Navigator

Real pytest coverage for src/monitoring/fairness_monitor.py. Asserts against the exact real
numbers already committed in BP3's and BP7's own Gate 4 artifacts - this module only aggregates
them, so these tests are really re-confirming that aggregation didn't misread the source files.
"""

from __future__ import annotations

from monitoring.fairness_monitor import (
    FOUR_FIFTHS_THRESHOLD,
    consolidated_fairness_report,
    read_bp3_fairness_status,
    read_bp7_fairness_status,
)


def test_bp3_real_disparate_impact_status_is_flagged():
    status = read_bp3_fairness_status()
    assert status["adverse_impact_ratio"] == 0.139
    assert status["flagged"] is True
    assert status["passes_four_fifths_rule"] is False
    assert status["champion_model"] == "xgboost"


def test_bp7_real_disparate_impact_status_is_not_flagged():
    status = read_bp7_fairness_status()
    assert status["adverse_impact_ratio"] == 0.908127
    assert status["flagged"] is False
    assert status["passes_four_fifths_rule"] is True


def test_consolidated_report_surfaces_the_real_bp3_flag():
    report = consolidated_fairness_report()
    assert report["four_fifths_threshold"] == FOUR_FIFTHS_THRESHOLD == 0.8
    assert len(report["checks"]) == 2
    assert report["any_check_flagged"] is True
    assert "GOVERNANCE REVIEW REQUIRED" in report["overall_status"]
