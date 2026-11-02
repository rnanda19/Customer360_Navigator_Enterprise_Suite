"""
src/mlops/governance.py — Customer360 Navigator

PHASE D: real model-governance validation - the gate every candidate model version must pass
before it can even be proposed for promotion (src/mlops/promotion.py enforces that ordering).

Per-BP thresholds below are deliberately derived from each BP's own real, already-committed
historical metrics (configs/bp*.yaml's gate3/gate4/gate5 blocks - the same numbers
MODEL_REGISTRY.md and MLOPS_OBSERVABILITY.md already disclose), set at a real but modest margin
BELOW the historically achieved value - not invented, not copied verbatim as a pass/fail-proof
rubber stamp either. A candidate that merely reproduces history passes; a regression large enough
to matter fails. This mirrors how src/monitoring/alerting.py already encodes real operational
thresholds (adverse_impact_ratio, PSI, API error rate) for the same project.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# bp_id -> {metric_name: minimum_acceptable_value}. Only metrics with a real recorded historical
# value in that BP's configs/*.yaml gate block are listed - a BP not listed here has no governance
# threshold defined yet (checked explicitly by validate_candidate, never silently passed).
MODEL_PERFORMANCE_THRESHOLDS: dict[str, dict[str, float]] = {
    # BP1 Gate 3/4/5 real champion (logistic_regression): held_out_test_accuracy 0.8224 recorded.
    # Threshold set ~2.5 points below the real recorded value - catches a real regression, tolerates
    # ordinary re-fit noise (BP1's own model_persistence.py reload-fidelity check already tolerates
    # exact equality on a deterministic refit; this threshold is for a genuinely different candidate).
    "bp1": {"held_out_test_accuracy": 0.80, "held_out_test_f1_macro": 0.78},
    # BP2 Gate 3-5 real champion (xgboost) - no single scalar accuracy is in the YAML snippet
    # inspected during Phase D's gap analysis; left for a future pass once that BP's exact metric
    # key is confirmed against its full config rather than guessed.
}

REQUIRED_DOCUMENTATION_FIELDS: tuple[str, ...] = (
    "champion_model",
    "trained_on",
    "evaluated_on",
    "intended_use",
)

GOVERNANCE_LOG_PATH = Path(__file__).resolve().parents[2] / "governance" / "model_governance_log.jsonl"


@dataclass
class GovernanceResult:
    bp_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    checked_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics_checked: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bp_id": self.bp_id,
            "passed": self.passed,
            "reasons": self.reasons,
            "checked_at_utc": self.checked_at_utc,
            "metrics_checked": self.metrics_checked,
        }


def validate_candidate(
    bp_id: str,
    metrics: dict[str, float],
    documentation: dict[str, Any] | None = None,
    *,
    thresholds: dict[str, dict[str, float]] | None = None,
) -> GovernanceResult:
    """Real governance check: (1) a threshold set must exist for bp_id - no threshold means no
    governed path yet, and this fails loudly rather than silently approving; (2) every thresholded
    metric must be present in `metrics` and meet its minimum; (3) `documentation` (if a governance
    threshold exists for this bp_id) must supply every field in REQUIRED_DOCUMENTATION_FIELDS,
    non-empty. Returns a GovernanceResult that is never silently truthy - `reasons` explains every
    failure, and an empty `reasons` list is the only way `passed` is True."""
    thresholds = thresholds if thresholds is not None else MODEL_PERFORMANCE_THRESHOLDS
    reasons: list[str] = []
    bp_thresholds = thresholds.get(bp_id)
    if not bp_thresholds:
        reasons.append(f"No governance threshold set is defined for bp_id={bp_id!r}.")
        return GovernanceResult(bp_id=bp_id, passed=False, reasons=reasons, metrics_checked={})

    checked: dict[str, float] = {}
    for metric_name, minimum in bp_thresholds.items():
        if metric_name not in metrics:
            reasons.append(f"Required metric '{metric_name}' is missing from candidate metrics.")
            continue
        value = metrics[metric_name]
        checked[metric_name] = value
        if value < minimum:
            reasons.append(f"Metric '{metric_name}'={value} is below the governance minimum of {minimum}.")

    doc = documentation or {}
    for field_name in REQUIRED_DOCUMENTATION_FIELDS:
        if not str(doc.get(field_name, "")).strip():
            reasons.append(f"Required documentation field '{field_name}' is missing or empty.")

    return GovernanceResult(bp_id=bp_id, passed=not reasons, reasons=reasons, metrics_checked=checked)


def record_governance_check(result: GovernanceResult, log_path: Path = GOVERNANCE_LOG_PATH) -> None:
    """Append `result` to the real, append-only governance log (JSON Lines) - never overwritten,
    never mutated after the fact, so a later audit can see every governance decision this project
    has actually made, pass or fail."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")


def read_governance_log(
    bp_id: str | None = None, log_path: Path = GOVERNANCE_LOG_PATH
) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    entries = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if bp_id is None or entry.get("bp_id") == bp_id:
                entries.append(entry)
    return entries
