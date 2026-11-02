"""
src/monitoring/prediction_monitor.py — Customer360 Navigator

PHASE D: Model Monitoring Foundation. This module extends this project's existing, real
monitoring package (drift_detection.py's PSI, fairness_monitor.py's Gate-4 readers,
alerting.py's threshold evaluator - all real and tested before Phase D) with the one piece
Phase D's gap analysis found genuinely missing: a real event-level record of what each inference
call actually did - prediction, model version, latency, and error status - and a real aggregator
over that log. This is a FOUNDATION (Phase D's own wording: "prepare for future drift monitoring")
- it does not claim a live, always-on monitoring loop or an external alerting channel; those
remain exactly as disclosed in MLOPS_OBSERVABILITY.md (no change made there by this module).

Design: plain JSON Lines on local disk (the same append-only pattern as
src/mlops/governance.py and src/mlops/audit_log.py) rather than a managed time-series/metrics
backend, consistent with this project's "no external managed service claimed" posture. A real
FastAPI service can call record_prediction_event() from any endpoint handler; none of the
existing BP1/BP2/BP7 inference services were modified to call it as part of this Phase D pass
(Step 3's "preserve existing functionality... do not alter existing business logic" constraint) -
wiring it into a specific endpoint is documented as a follow-up in MLOPS_ARCHITECTURE.md, not
silently claimed as done here.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PREDICTION_LOG_PATH = Path(__file__).resolve().parents[2] / "governance" / "prediction_events.jsonl"


@dataclass
class PredictionEvent:
    bp_id: str
    model_version: str
    latency_ms: float
    predicted_label: Any
    error: str | None = None
    actual_outcome: Any | None = None
    recorded_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "bp_id": self.bp_id,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "predicted_label": self.predicted_label,
            "error": self.error,
            "actual_outcome": self.actual_outcome,
            "recorded_at_utc": self.recorded_at_utc,
        }


def record_prediction_event(
    bp_id: str,
    model_version: str,
    latency_ms: float,
    predicted_label: Any,
    *,
    error: str | None = None,
    actual_outcome: Any | None = None,
    log_path: Path = PREDICTION_LOG_PATH,
) -> PredictionEvent:
    """Append one real prediction event. Called once per real inference request by a service
    that chooses to wire it in (see module docstring - none of this project's existing services
    were modified to call this automatically as part of Phase D)."""
    event = PredictionEvent(
        bp_id=bp_id,
        model_version=model_version,
        latency_ms=latency_ms,
        predicted_label=predicted_label,
        error=error,
        actual_outcome=actual_outcome,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event.to_dict(), sort_keys=True, default=str) + "\n")
    return event


def read_prediction_events(
    bp_id: str | None = None, log_path: Path = PREDICTION_LOG_PATH
) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    events = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if bp_id is None or entry.get("bp_id") == bp_id:
                events.append(entry)
    return events


def summarize_predictions(bp_id: str | None = None, log_path: Path = PREDICTION_LOG_PATH) -> dict[str, Any]:
    """Real aggregation over the real recorded events: total count, error rate, latency
    percentiles (p50/p95/p99, computed by sorting - no library dependency beyond stdlib), the
    real prediction-label distribution (feeds drift_detection.population_stability_index() when a
    caller wants to compare two summarize_predictions() windows), and which model versions served
    traffic in the window. Returns a result with zero_events=True (never a fabricated "healthy"
    summary) when there is nothing real to summarize."""
    events = read_prediction_events(bp_id=bp_id, log_path=log_path)
    if not events:
        return {"bp_id": bp_id, "zero_events": True, "n_events": 0}

    n_events = len(events)
    n_errors = sum(1 for e in events if e.get("error"))
    latencies = sorted(e["latency_ms"] for e in events if e.get("latency_ms") is not None)

    def _percentile(sorted_values: list[float], pct: float) -> float | None:
        if not sorted_values:
            return None
        idx = min(len(sorted_values) - 1, int(round(pct / 100 * (len(sorted_values) - 1))))
        return sorted_values[idx]

    label_counts = Counter(str(e.get("predicted_label")) for e in events)
    total_labels = sum(label_counts.values())
    label_distribution = {k: v / total_labels for k, v in label_counts.items()} if total_labels else {}
    model_versions = sorted({str(e.get("model_version")) for e in events})

    return {
        "bp_id": bp_id,
        "zero_events": False,
        "n_events": n_events,
        "n_errors": n_errors,
        "error_rate": n_errors / n_events,
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "latency_p99_ms": _percentile(latencies, 99),
        "predicted_label_distribution": label_distribution,
        "model_versions_observed": model_versions,
    }
