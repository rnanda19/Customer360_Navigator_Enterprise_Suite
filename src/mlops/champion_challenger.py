"""
src/mlops/champion_challenger.py — Customer360 Navigator

PHASE D: real champion-vs-challenger comparison. Compares a candidate ("challenger") model's real
evaluation metrics against the currently-promoted ("champion") version's real metrics across three
axes - performance, stability, and (where available) fairness - and returns a structured verdict.
This module computes nothing by simulation: every number it compares is a real metric the caller
measured (from a fresh MLflow run or from a registered version's own tags via
src/mlops/registry.get_version_tags()). Where no real fairness metric exists for a given bp_id
(most BPs - only BP3/BP7 currently have a real Gate 4 disparate-impact JSON, per
src/monitoring/fairness_monitor.py), the fairness axis is honestly reported as "not_available",
never defaulted to a passing or failing placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Minimum real improvement (or maximum acceptable regression, when negative) required on the
# primary performance metric for a challenger to be considered AT LEAST AS GOOD as the champion.
# A small negative tolerance (-0.01) absorbs ordinary re-fit/measurement noise on a deterministic
# refit (BP1's own reload-fidelity check already shows 0.0 diff on an exact refit) without
# requiring every challenger to strictly beat history to pass.
PERFORMANCE_REGRESSION_TOLERANCE = -0.01


@dataclass
class AxisResult:
    axis: str
    status: str  # "pass" | "fail" | "not_available"
    detail: str
    champion_value: float | None = None
    challenger_value: float | None = None


@dataclass
class ChallengerVerdict:
    bp_id: str
    primary_metric: str
    axes: list[AxisResult] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        """A challenger passes only if every axis that WAS evaluated passed - 'not_available'
        axes neither pass nor fail the verdict, they are disclosed as gaps (see
        to_dict()['unavailable_axes']), consistent with Phase D's "do not fabricate" constraint:
        a missing fairness metric is a disclosed limitation, never silently treated as a pass."""
        return all(axis.status != "fail" for axis in self.axes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bp_id": self.bp_id,
            "primary_metric": self.primary_metric,
            "overall_pass": self.overall_pass,
            "axes": [
                {
                    "axis": a.axis,
                    "status": a.status,
                    "detail": a.detail,
                    "champion_value": a.champion_value,
                    "challenger_value": a.challenger_value,
                }
                for a in self.axes
            ],
            "unavailable_axes": [a.axis for a in self.axes if a.status == "not_available"],
        }


def compare_performance(
    champion_metrics: dict[str, float],
    challenger_metrics: dict[str, float],
    primary_metric: str,
    tolerance: float = PERFORMANCE_REGRESSION_TOLERANCE,
) -> AxisResult:
    if primary_metric not in champion_metrics or primary_metric not in challenger_metrics:
        return AxisResult(
            axis="performance",
            status="not_available",
            detail=f"'{primary_metric}' missing from champion or challenger metrics.",
        )
    champ_val = champion_metrics[primary_metric]
    chall_val = challenger_metrics[primary_metric]
    delta = chall_val - champ_val
    status = "pass" if delta >= tolerance else "fail"
    detail = (
        f"challenger {primary_metric}={chall_val:.4f} vs champion {champ_val:.4f} "
        f"(delta={delta:+.4f}, tolerance={tolerance:+.4f})"
    )
    return AxisResult(
        axis="performance", status=status, detail=detail, champion_value=champ_val, challenger_value=chall_val
    )


def compare_stability(
    champion_ci_width: float | None,
    challenger_ci_width: float | None,
    max_relative_widening: float = 0.5,
) -> AxisResult:
    """Compares the real width of each model's bootstrap/CV confidence interval on its primary
    metric (a real statistic the caller computed - e.g. BP1 Gate 4's held_out_test_f1_macro
    bootstrap CI [0.808, 0.8334], width 0.0254). A challenger whose CI is more than
    `max_relative_widening` proportionally wider than the champion's is considered less stable."""
    if champion_ci_width is None or challenger_ci_width is None:
        return AxisResult(
            axis="stability",
            status="not_available",
            detail="CI width not supplied for champion and/or challenger.",
        )
    if champion_ci_width <= 0:
        status = "pass" if challenger_ci_width <= 0 else "fail"
    else:
        relative_widening = (challenger_ci_width - champion_ci_width) / champion_ci_width
        status = "pass" if relative_widening <= max_relative_widening else "fail"
    detail = f"challenger CI width={challenger_ci_width:.4f} vs champion CI width={champion_ci_width:.4f}"
    return AxisResult(
        axis="stability",
        status=status,
        detail=detail,
        champion_value=champion_ci_width,
        challenger_value=challenger_ci_width,
    )


def compare_fairness(
    champion_adverse_impact_ratio: float | None,
    challenger_adverse_impact_ratio: float | None,
    min_acceptable_ratio: float = 0.80,
) -> AxisResult:
    """Compares real disparate-impact ratios (the same metric and the same 0.80 four-fifths-rule
    threshold src/monitoring/alerting.py's DEFAULT_THRESHOLDS already uses for
    adverse_impact_ratio). Only meaningful for a bp_id with a real Gate 4 fairness JSON - callers
    without one (most BPs) should pass None for both arguments, yielding 'not_available' rather
    than a fabricated pass."""
    if champion_adverse_impact_ratio is None or challenger_adverse_impact_ratio is None:
        return AxisResult(
            axis="fairness",
            status="not_available",
            detail="No real adverse-impact-ratio available for this bp_id.",
        )
    status = "pass" if challenger_adverse_impact_ratio >= min_acceptable_ratio else "fail"
    detail = (
        f"challenger adverse_impact_ratio={challenger_adverse_impact_ratio:.4f} "
        f"(minimum {min_acceptable_ratio})"
    )
    return AxisResult(
        axis="fairness",
        status=status,
        detail=detail,
        champion_value=champion_adverse_impact_ratio,
        challenger_value=challenger_adverse_impact_ratio,
    )


def evaluate_challenger(
    bp_id: str,
    primary_metric: str,
    champion_metrics: dict[str, float],
    challenger_metrics: dict[str, float],
    *,
    champion_ci_width: float | None = None,
    challenger_ci_width: float | None = None,
    champion_adverse_impact_ratio: float | None = None,
    challenger_adverse_impact_ratio: float | None = None,
) -> ChallengerVerdict:
    """Run all three real comparison axes and return one structured verdict. This is the single
    entry point src/mlops/promotion.py calls before a candidate can even be proposed for
    approval."""
    axes = [
        compare_performance(champion_metrics, challenger_metrics, primary_metric),
        compare_stability(champion_ci_width, challenger_ci_width),
        compare_fairness(champion_adverse_impact_ratio, challenger_adverse_impact_ratio),
    ]
    return ChallengerVerdict(bp_id=bp_id, primary_metric=primary_metric, axes=axes)
