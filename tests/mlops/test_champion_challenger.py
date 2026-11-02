"""
tests/mlops/test_champion_challenger.py — Customer360 Navigator

Real pytest coverage for src/mlops/champion_challenger.py.
"""

from __future__ import annotations

from mlops import champion_challenger as cc


def test_challenger_matching_champion_exactly_passes_performance_axis():
    result = cc.compare_performance({"acc": 0.80}, {"acc": 0.80}, "acc")
    assert result.status == "pass"


def test_challenger_beating_champion_passes():
    result = cc.compare_performance({"acc": 0.80}, {"acc": 0.85}, "acc")
    assert result.status == "pass"


def test_challenger_within_tolerance_below_champion_still_passes():
    result = cc.compare_performance({"acc": 0.80}, {"acc": 0.795}, "acc", tolerance=-0.01)
    assert result.status == "pass"


def test_challenger_beyond_tolerance_below_champion_fails():
    result = cc.compare_performance({"acc": 0.80}, {"acc": 0.50}, "acc", tolerance=-0.01)
    assert result.status == "fail"


def test_performance_axis_not_available_when_metric_missing():
    result = cc.compare_performance({"acc": 0.80}, {}, "acc")
    assert result.status == "not_available"


def test_stability_axis_not_available_when_ci_width_not_supplied():
    result = cc.compare_stability(None, None)
    assert result.status == "not_available"


def test_stability_axis_passes_when_challenger_ci_is_tighter_or_similar():
    result = cc.compare_stability(0.05, 0.05)
    assert result.status == "pass"


def test_stability_axis_fails_when_challenger_ci_much_wider():
    result = cc.compare_stability(0.02, 0.20)
    assert result.status == "fail"


def test_fairness_axis_not_available_when_no_real_metric_supplied():
    result = cc.compare_fairness(None, None)
    assert result.status == "not_available"


def test_fairness_axis_passes_above_four_fifths_rule():
    result = cc.compare_fairness(0.85, 0.90)
    assert result.status == "pass"


def test_fairness_axis_fails_below_four_fifths_rule():
    result = cc.compare_fairness(0.85, 0.50)
    assert result.status == "fail"


def test_evaluate_challenger_overall_pass_requires_all_evaluated_axes_to_pass():
    verdict = cc.evaluate_challenger(
        "bp1",
        "acc",
        {"acc": 0.80},
        {"acc": 0.80},
        champion_ci_width=0.05,
        challenger_ci_width=0.05,
    )
    assert verdict.overall_pass is True
    assert verdict.to_dict()["unavailable_axes"] == ["fairness"]


def test_evaluate_challenger_overall_pass_false_if_any_evaluated_axis_fails():
    verdict = cc.evaluate_challenger(
        "bp1",
        "acc",
        {"acc": 0.80},
        {"acc": 0.10},
    )
    assert verdict.overall_pass is False


def test_not_available_axes_never_cause_a_fail_on_their_own():
    verdict = cc.evaluate_challenger("bp1", "acc", {"acc": 0.80}, {"acc": 0.80})
    assert verdict.overall_pass is True
    assert set(verdict.to_dict()["unavailable_axes"]) == {"stability", "fairness"}
