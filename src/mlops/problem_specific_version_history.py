"""
src/mlops/problem_specific_version_history.py — Customer360 Navigator

PHASE I: real version history for the BPs whose "champion" is not a trained classifier.
src/mlops/registry.py's MLflow-backed alias registry (champion/challenger/previous_champion) is
the real versioning mechanism for BP1-3 (trained_classifier problem type) - this module does NOT
duplicate or replace that, and does not touch BP1-3.

BP4-BP8 are five structurally different, non-classifier problem types (benchmark_pipeline,
association_reporting, retrieval_strategy, rule_engine, gold_layer_aggregation - see
src/monitoring/model_registry.py's own docstring for the full breakdown). Forcing these through
MLflow's registered-model/model-version API - which fundamentally expects a logged model artifact
per version - would mean fabricating a "model" for a benchmark pipeline or a Gold-layer
aggregation that has none. That is exactly the "forced classifier schema" the Master Engineering
Directive's own rules prohibit. What these BPs DO have, for real, is each problem type's own
"champion" concept: BP4's config_champion_identifier names a real benchmarked approach
(e.g. "polars_lazy_streaming"), BP6's names a real retrieval strategy, BP7's names a real rule
scheme - all already read, for real, by src/mlops/enterprise_status.py's
assess_all_bp_governance_status() (reused here, never re-derived). BP5 and BP8 have NO single
discrete champion identifier at all (association_reporting and gold_layer_aggregation
respectively, both already documented as such in their own config_note fields) - this module
never fabricates one for them; a None identifier is simply never recorded as a "version."

Design: the same append-only JSON Lines pattern already established by
src/mlops/governance.py, src/mlops/audit_log.py, and src/monitoring/prediction_monitor.py. A new
line is written only when the real config_champion_identifier for a BP actually changes from the
last recorded value (or there is no prior entry at all) - never on every call, which would turn
an unchanged read into a fabricated "new version."
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_HISTORY_LOG_PATH = REPO_ROOT / "governance" / "problem_specific_version_history.jsonl"

# Problem types this module covers. Deliberately excludes "trained_classifier" (BP1-3), which
# already has a real versioning mechanism in src/mlops/registry.py - recording those here too
# would create two competing, confusable version histories for the same BPs.
_NON_CLASSIFIER_PROBLEM_TYPES = frozenset(
    {
        "benchmark_pipeline",  # BP4
        "association_reporting",  # BP5 (no discrete identifier - see module docstring)
        "retrieval_strategy",  # BP6
        "rule_engine",  # BP7
        "gold_layer_aggregation",  # BP8 (no discrete identifier - see module docstring)
    }
)


@dataclass
class VersionHistoryEntry:
    bp_id: str
    problem_type: str
    config_champion_identifier: str
    change_type: str  # "initial" | "changed"
    previous_identifier: Optional[str]
    recorded_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "bp_id": self.bp_id,
            "problem_type": self.problem_type,
            "config_champion_identifier": self.config_champion_identifier,
            "change_type": self.change_type,
            "previous_identifier": self.previous_identifier,
            "recorded_at_utc": self.recorded_at_utc,
        }


def get_version_history(bp_id: Optional[str] = None, log_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Real reader over the append-only log. Returns [] (never raises) if the log doesn't exist
    yet - an honest "no history recorded yet," not an error."""
    resolved_log_path = log_path if log_path is not None else VERSION_HISTORY_LOG_PATH
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


def _latest_identifier_for(bp_id: str, log_path: Path) -> Optional[str]:
    history = get_version_history(bp_id, log_path=log_path)
    if not history:
        return None
    return history[-1].get("config_champion_identifier")


def record_version_if_changed(
    bp_id: str,
    *,
    problem_type: str,
    config_champion_identifier: Optional[str],
    log_path: Optional[Path] = None,
) -> Optional[VersionHistoryEntry]:
    """Appends one real entry only when config_champion_identifier is non-None AND differs from
    the last recorded value for this bp_id (or there is no prior entry). Returns the new entry,
    or None when nothing changed (or when config_champion_identifier is None - this BP has no
    discrete champion concept, e.g. BP5/BP8, and nothing is ever fabricated for it)."""
    if config_champion_identifier is None:
        return None

    resolved_log_path = log_path if log_path is not None else VERSION_HISTORY_LOG_PATH
    previous_identifier = _latest_identifier_for(bp_id, resolved_log_path)
    if previous_identifier == config_champion_identifier:
        return None

    entry = VersionHistoryEntry(
        bp_id=bp_id,
        problem_type=problem_type,
        config_champion_identifier=config_champion_identifier,
        change_type="initial" if previous_identifier is None else "changed",
        previous_identifier=previous_identifier,
    )
    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), sort_keys=True, default=str) + "\n")
    return entry


def sync_version_history_from_enterprise_status(
    statuses: Optional[list[Any]] = None, log_path: Optional[Path] = None
) -> list[VersionHistoryEntry]:
    """Composes with src/mlops/enterprise_status.py's real, already-tested
    assess_all_bp_governance_status() (reused, never re-derived) and calls
    record_version_if_changed() for every BP whose problem_type is one of this module's
    non-classifier types. `statuses` lets a caller (or a test) pass a pre-computed list instead
    of re-querying the real configs/ directory - mirrors enterprise_status.py's own
    `registry_entries` parameter convention. Returns only the entries actually written (an empty
    list on a run where nothing changed, including a run where it was called with no prior
    history gap - that first run DOES write "initial" entries, so an empty list here really does
    mean nothing changed since the last sync, not that nothing was checked)."""
    if statuses is None:
        from mlops.enterprise_status import assess_all_bp_governance_status

        statuses = assess_all_bp_governance_status()

    written = []
    for status in statuses:
        if status.problem_type not in _NON_CLASSIFIER_PROBLEM_TYPES:
            continue
        entry = record_version_if_changed(
            status.bp_id,
            problem_type=status.problem_type,
            config_champion_identifier=status.config_champion_identifier,
            log_path=log_path,
        )
        if entry is not None:
            written.append(entry)
    return written
