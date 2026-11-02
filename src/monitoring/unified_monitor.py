"""
src/monitoring/unified_monitor.py — Customer360 Navigator

PHASE F/G (Master Engineering Directive): real composition of this project's four already-real,
independently-tested monitoring primitives - prediction_monitor.py (event logging + summary),
drift_detection.py (PSI), fairness_monitor.py (four-fifths rule aggregation), alerting.py
(threshold -> severity evaluation) - into one monitoring run that actually USES their outputs
together, rather than four modules that each pass their own unit tests in isolation.

This module computes nothing new about data or model quality on its own - every number it
reports comes from calling one of those four existing modules. What IS new here:
  1. A real, minimal data-quality validator (schema / missing-value / duplicate checks over real
     input records).
  2. PSI drift wired to two real time windows of prediction_monitor's own real label-distribution
     output - not only the static BP8 Gold-data demo drift_detection.py already has.
  3. An append-only structured JSON event log of each monitoring run
     (governance/monitoring_events.jsonl - same pattern as governance.py/audit_log.py).
  4. A real alert audit trail (governance/alert_audit_log.jsonl) recording every AlertEvent this
     module actually raises from real computed values - not just logic that COULD raise one.

HONESTY RULES THIS MODULE FOLLOWS (same standard as the rest of src/mlops, src/monitoring):
  - Model-PERFORMANCE monitoring (accuracy against real outcomes) reports "awaiting_ground_truth"
    whenever the real prediction log has zero events with a real actual_outcome recorded - never
    silently skipped, never fabricated.
  - Fairness monitoring only runs for BP3/BP7 (the only two BPs with a real disparate-impact check
    in this project - see fairness_monitor.py's own docstring); every other bp_id reports
    status="not_applicable", exactly like src/mlops/enterprise_status.py already does for the
    classifier-threshold governance schema.
  - PSI drift requires MIN_EVENTS_FOR_DRIFT real events in BOTH windows; below that it reports
    "insufficient_data" rather than computing a PSI value on too little data to mean anything.

DEFAULT-ARGUMENT CONVENTION (a real bug class this project has hit twice already - see
src/mlops/audit_log.py's original log_path default, and src/mlops/enterprise_status.py's
MODELS_DIR default, Phase D and Phase E respectively): every log-path parameter below defaults
to None and is resolved to the current module-level constant INSIDE the function body, never
bound as `param: Path = MODULE_CONSTANT` in the signature - a signature default is captured once
at import time and a test (or caller) monkeypatching the module constant would have no effect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from monitoring import alerting, prediction_monitor
from monitoring.drift_detection import interpret_psi, population_stability_index
from monitoring.fairness_monitor import consolidated_fairness_report

REPO_ROOT = Path(__file__).resolve().parents[2]
MONITORING_EVENTS_LOG_PATH = REPO_ROOT / "governance" / "monitoring_events.jsonl"
ALERT_AUDIT_LOG_PATH = REPO_ROOT / "governance" / "alert_audit_log.jsonl"

MIN_EVENTS_FOR_DRIFT = 5

# Only these two BPs have a real, already-built disparate-impact check this module can honestly
# report (see fairness_monitor.py's own module docstring for exactly why).
FAIRNESS_APPLICABLE_BPS = frozenset({"bp3", "bp7"})


# ---- Data quality ------------------------------------------------------------------------------


@dataclass
class DataQualityResult:
    bp_id: str
    n_records: int
    schema_valid: bool
    missing_required_columns: list[str] = field(default_factory=list)
    missing_value_rates: dict[str, float] = field(default_factory=dict)
    duplicate_row_count: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def validate_input_schema(
    records: list[dict[str, Any]],
    *,
    bp_id: str,
    required_columns: tuple[str, ...],
) -> DataQualityResult:
    """Real schema/data-quality check over a real batch of input records (e.g. the raw payload a
    service received, or a reference sample pulled for monitoring). Never invents a verdict for
    an empty batch - n_records=0 is reported plainly as schema_valid=False, not silently treated
    as "nothing to check, so it passes". Duplicate detection compares the full record (every
    key/value pair), so every value in a record must be hashable - a real, documented limitation,
    not a silent truncation to a subset of columns."""
    if not records:
        return DataQualityResult(
            bp_id=bp_id, n_records=0, schema_valid=False, reasons=["No records supplied."]
        )

    present_columns: set[str] = set()
    for r in records:
        present_columns |= set(r.keys())
    missing_required = sorted(c for c in required_columns if c not in present_columns)

    reasons: list[str] = []
    if missing_required:
        reasons.append(f"Missing required column(s): {missing_required}")

    missing_value_rates: dict[str, float] = {}
    for col in required_columns:
        if col in present_columns:
            n_missing = sum(1 for r in records if r.get(col) in (None, "", []))
            missing_value_rates[col] = n_missing / len(records)

    seen: set[tuple] = set()
    duplicate_count = 0
    for r in records:
        key = tuple(sorted(r.items()))
        if key in seen:
            duplicate_count += 1
        else:
            seen.add(key)
    if duplicate_count:
        reasons.append(f"{duplicate_count} duplicate record(s) detected.")

    return DataQualityResult(
        bp_id=bp_id,
        n_records=len(records),
        schema_valid=not missing_required,
        missing_required_columns=missing_required,
        missing_value_rates=missing_value_rates,
        duplicate_row_count=duplicate_count,
        reasons=reasons,
    )


# ---- Drift (PSI, wired to two real prediction-event windows) -----------------------------------


def compute_prediction_drift(
    bp_id: str,
    *,
    reference_log_path: Path,
    current_log_path: Path,
    min_events: int = MIN_EVENTS_FOR_DRIFT,
) -> dict[str, Any]:
    """Real PSI between two real windows of prediction_monitor.summarize_predictions()'s own
    predicted_label_distribution output - the exact categorical-proportion format
    drift_detection.population_stability_index() already expects. Neither window is fabricated;
    both are real reads of real (possibly empty) JSONL logs."""
    reference_summary = prediction_monitor.summarize_predictions(bp_id=bp_id, log_path=reference_log_path)
    current_summary = prediction_monitor.summarize_predictions(bp_id=bp_id, log_path=current_log_path)

    if reference_summary["zero_events"] or current_summary["zero_events"]:
        return {
            "status": "insufficient_data",
            "reason": "One or both windows have zero recorded prediction events.",
        }
    if reference_summary["n_events"] < min_events or current_summary["n_events"] < min_events:
        return {
            "status": "insufficient_data",
            "reason": (
                f"Fewer than {min_events} events in at least one window "
                f"(reference={reference_summary['n_events']}, current={current_summary['n_events']})."
            ),
        }

    psi = population_stability_index(
        reference_summary["predicted_label_distribution"],
        current_summary["predicted_label_distribution"],
    )
    return {
        "status": "computed",
        "population_stability_index": round(psi, 4),
        "interpretation": interpret_psi(psi),
        "reference_n_events": reference_summary["n_events"],
        "current_n_events": current_summary["n_events"],
    }


# ---- Model performance (awaiting ground truth until real outcomes exist) -----------------------


def model_performance_status(bp_id: str, *, log_path: Path) -> dict[str, Any]:
    """Real accuracy against real logged outcomes, computed ONLY over events that actually carry
    a real `actual_outcome` - every other event is honestly excluded, never imputed. Reports
    "awaiting_ground_truth" (never a fabricated metric) when no event has one yet - this is the
    normal, expected, disclosed state for every BP in this project today, since no live
    production traffic with confirmed outcomes exists."""
    events = prediction_monitor.read_prediction_events(bp_id=bp_id, log_path=log_path)
    if not events:
        return {"status": "awaiting_ground_truth", "reason": "No prediction events recorded yet."}

    labeled = [e for e in events if e.get("actual_outcome") is not None]
    if not labeled:
        return {
            "status": "awaiting_ground_truth",
            "reason": f"{len(events)} prediction event(s) recorded, but none has a real actual_outcome yet.",
            "n_events": len(events),
        }

    n_correct = sum(1 for e in labeled if e["actual_outcome"] == e.get("predicted_label"))
    return {
        "status": "computed",
        "n_events_with_ground_truth": len(labeled),
        "accuracy_on_labeled_subset": n_correct / len(labeled),
    }


# ---- Fairness (only where a real check exists - BP3/BP7) ---------------------------------------


def fairness_status(bp_id: str) -> dict[str, Any]:
    """Real BP3/BP7 disparate-impact status via fairness_monitor.py's existing, tested aggregator
    - reused, never recomputed. Every other bp_id is honestly reported not_applicable, matching
    fairness_monitor.py's own module docstring on exactly why only these two BPs have a real
    check today."""
    bp_lower = bp_id.lower()
    if bp_lower not in FAIRNESS_APPLICABLE_BPS:
        return {
            "status": "not_applicable",
            "reason": f"No real disparate-impact check exists for {bp_id} in this project yet.",
        }
    report = consolidated_fairness_report()
    matching = [c for c in report["checks"] if c["bp"].lower() == bp_lower]
    if not matching:
        return {"status": "not_applicable", "reason": f"{bp_id} has no entry in the real fairness report."}
    return {"status": "computed", "check": matching[0]}


# ---- Alerting (real values -> real severities, via the existing evaluator) ----------------------


def evaluate_real_alerts(
    *,
    error_rate: Optional[float] = None,
    latency_p99_ms: Optional[float] = None,
    adverse_impact_ratio: Optional[float] = None,
    population_stability_index_value: Optional[float] = None,
) -> list[alerting.AlertEvent]:
    """Runs whichever real computed values are supplied through alerting.py's existing, already-
    tested evaluate_alert() and DEFAULT_THRESHOLDS - reused verbatim, never a second threshold
    table invented here. A None value is skipped (no event raised for a metric that was never
    actually computed this run), never defaulted to 0 (which would be a fabricated "all clear")."""
    events: list[alerting.AlertEvent] = []
    if error_rate is not None:
        events.append(alerting.evaluate_alert("api_error_rate_pct", error_rate * 100))
    if latency_p99_ms is not None:
        events.append(alerting.evaluate_alert("api_p99_latency_ms", latency_p99_ms))
    if adverse_impact_ratio is not None:
        events.append(alerting.evaluate_alert("adverse_impact_ratio", adverse_impact_ratio))
    if population_stability_index_value is not None:
        events.append(alerting.evaluate_alert("population_stability_index", population_stability_index_value))
    return events


def record_alert_events(
    events: list[alerting.AlertEvent], *, bp_id: str, log_path: Optional[Path] = None
) -> None:
    resolved_log_path = log_path if log_path is not None else ALERT_AUDIT_LOG_PATH
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(timezone.utc).isoformat()
    with resolved_log_path.open("a", encoding="utf-8") as fh:
        for e in events:
            fh.write(
                json.dumps(
                    {
                        "bp_id": bp_id,
                        "metric_name": e.metric_name,
                        "value": e.value,
                        "severity": e.severity.value,
                        "message": e.message,
                        "recorded_at_utc": recorded_at,
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def read_alert_audit_log(
    bp_id: Optional[str] = None, log_path: Optional[Path] = None
) -> list[dict[str, Any]]:
    resolved_log_path = log_path if log_path is not None else ALERT_AUDIT_LOG_PATH
    if not resolved_log_path.exists():
        return []
    entries = []
    with resolved_log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if bp_id is None or entry.get("bp_id") == bp_id:
                entries.append(entry)
    return entries


# ---- Top-level composition: one real monitoring run, one structured event ----------------------


@dataclass
class MonitoringRunResult:
    bp_id: str
    generated_at_utc: str
    prediction_summary: dict[str, Any]
    data_quality: Optional[dict[str, Any]]
    drift: Optional[dict[str, Any]]
    fairness: dict[str, Any]
    model_performance: dict[str, Any]
    alerts: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def run_monitoring_cycle(
    bp_id: str,
    *,
    current_log_path: Optional[Path] = None,
    reference_log_path: Optional[Path] = None,
    input_records: Optional[list[dict[str, Any]]] = None,
    required_columns: Optional[tuple[str, ...]] = None,
    events_log_path: Optional[Path] = None,
    alert_log_path: Optional[Path] = None,
) -> MonitoringRunResult:
    """The real, single entry point this module exists for: pulls real prediction-event summary,
    optionally real data-quality/drift/fairness/model-performance status, evaluates real alerts
    from whichever of those actually produced a computed value, records every raised alert to the
    real alert audit trail, and appends one real structured JSON record of the whole run to
    governance/monitoring_events.jsonl. Every sub-result keeps its own honest status string
    ("computed" / "insufficient_data" / "awaiting_ground_truth" / "not_applicable") - this
    function never collapses them into a single fabricated pass/fail."""
    resolved_current_log_path = (
        current_log_path if current_log_path is not None else prediction_monitor.PREDICTION_LOG_PATH
    )

    prediction_summary = prediction_monitor.summarize_predictions(
        bp_id=bp_id, log_path=resolved_current_log_path
    )

    data_quality = None
    if input_records is not None and required_columns is not None:
        data_quality = validate_input_schema(
            input_records, bp_id=bp_id, required_columns=required_columns
        ).to_dict()

    drift = None
    if reference_log_path is not None:
        drift = compute_prediction_drift(
            bp_id,
            reference_log_path=reference_log_path,
            current_log_path=resolved_current_log_path,
        )

    fairness = fairness_status(bp_id)
    model_performance = model_performance_status(bp_id, log_path=resolved_current_log_path)

    alert_kwargs: dict[str, Optional[float]] = {}
    if not prediction_summary.get("zero_events"):
        alert_kwargs["error_rate"] = prediction_summary.get("error_rate")
        alert_kwargs["latency_p99_ms"] = prediction_summary.get("latency_p99_ms")
    if fairness.get("status") == "computed":
        alert_kwargs["adverse_impact_ratio"] = fairness["check"]["adverse_impact_ratio"]
    if drift is not None and drift.get("status") == "computed":
        alert_kwargs["population_stability_index_value"] = drift["population_stability_index"]

    alert_events = evaluate_real_alerts(**{k: v for k, v in alert_kwargs.items() if v is not None})
    record_alert_events(alert_events, bp_id=bp_id, log_path=alert_log_path)

    result = MonitoringRunResult(
        bp_id=bp_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        prediction_summary=prediction_summary,
        data_quality=data_quality,
        drift=drift,
        fairness=fairness,
        model_performance=model_performance,
        alerts=[
            {
                "metric_name": e.metric_name,
                "value": e.value,
                "severity": e.severity.value,
                "message": e.message,
            }
            for e in alert_events
        ],
    )

    resolved_events_log_path = events_log_path if events_log_path is not None else MONITORING_EVENTS_LOG_PATH
    resolved_events_log_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_events_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result.to_dict(), sort_keys=True, default=str) + "\n")

    return result
