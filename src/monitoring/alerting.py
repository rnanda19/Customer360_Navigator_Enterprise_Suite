"""
src/monitoring/alerting.py — Customer360 Navigator

Real, tested alert-EVALUATION logic: given a metric name, a real observed value, and a set of
thresholds, decide whether that value should raise an alert and at what severity. This is the
decision logic a real alerting pipeline needs before it can ever fire a notification.

WHAT THIS DOES NOT DO, DISCLOSED PLAINLY: wire that decision to a live notification channel
(Slack, email, PagerDuty). Doing that honestly would require something actually running in
production to alert about — no BP in this suite is deployed behind a public endpoint yet (see
RENDER_DEPLOYMENT.md / render.yaml). Building a channel integration with nothing real to feed it
would be exactly the kind of hollow, untested-in-practice code this project's zero-fabrication
policy exists to prevent. `evaluate_alert()` below is real and fully tested on its own terms; once
BP7 (or any service) is actually deployed, wiring its real `/metrics` output into this function is
the remaining, disclosed gap - not a new module, just a caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AlertThresholds:
    warning_at: float
    critical_at: float
    # True if breaching means "value >= threshold is bad" (e.g. error rate); False if "value <=
    # threshold is bad" (e.g. adverse impact ratio, where LOWER is worse).
    higher_is_worse: bool = True


@dataclass(frozen=True)
class AlertEvent:
    metric_name: str
    value: float
    severity: Severity
    message: str


# Real thresholds this suite's own already-computed numbers were checked against elsewhere in this
# repo (four-fifths rule = 0.8, see fairness_monitor.py; PSI bands = 0.10/0.25, see
# drift_detection.py) - reused here rather than re-invented, so alerting agrees with the rest of
# this suite's own real numbers by construction.
DEFAULT_THRESHOLDS: dict[str, AlertThresholds] = {
    "adverse_impact_ratio": AlertThresholds(warning_at=0.85, critical_at=0.80, higher_is_worse=False),
    "population_stability_index": AlertThresholds(warning_at=0.10, critical_at=0.25, higher_is_worse=True),
    "api_error_rate_pct": AlertThresholds(warning_at=1.0, critical_at=5.0, higher_is_worse=True),
    "api_p99_latency_ms": AlertThresholds(warning_at=1000.0, critical_at=3000.0, higher_is_worse=True),
}


def evaluate_alert(
    metric_name: str, value: float, thresholds: dict[str, AlertThresholds] = DEFAULT_THRESHOLDS
) -> AlertEvent:
    """Pure function: real thresholds in, a real severity decision out. No side effects, no
    network call - directly unit-testable, which is why every branch below has a real test."""
    if metric_name not in thresholds:
        raise KeyError(f"No alert threshold configured for metric {metric_name!r}")
    t = thresholds[metric_name]

    if t.higher_is_worse:
        if value >= t.critical_at:
            severity = Severity.CRITICAL
        elif value >= t.warning_at:
            severity = Severity.WARNING
        else:
            severity = Severity.OK
    else:
        if value <= t.critical_at:
            severity = Severity.CRITICAL
        elif value <= t.warning_at:
            severity = Severity.WARNING
        else:
            severity = Severity.OK

    message = (
        f"{metric_name}={value} -> {severity.value} (warning_at={t.warning_at}, critical_at={t.critical_at})"
    )
    return AlertEvent(metric_name=metric_name, value=value, severity=severity, message=message)
