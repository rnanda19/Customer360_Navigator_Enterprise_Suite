"""
src/mlops/audit_log.py — Customer360 Navigator

PHASE D: a real, append-only audit trail for every governance/promotion/rollback decision this
project's MLOps tooling makes. Plain JSON Lines on disk (consistent with this module's own
`governance/model_governance_log.jsonl` sibling in governance.py) - no external audit service is
claimed or required. Every entry is appended, never rewritten or deleted by this module; the only
way to remove an entry is to edit the file by hand outside this code path, which would be visible
in git history for anyone who later commits the log.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_LOG_PATH = Path(__file__).resolve().parents[2] / "governance" / "audit_log.jsonl"


@dataclass
class AuditEntry:
    event_type: str
    bp_id: str
    actor: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    recorded_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "recorded_at_utc": self.recorded_at_utc,
            "event_type": self.event_type,
            "bp_id": self.bp_id,
            "actor": self.actor,
            "reason": self.reason,
            "details": self.details,
        }


def record_event(
    event_type: str,
    bp_id: str,
    actor: str,
    reason: str,
    details: dict[str, Any] | None = None,
    log_path: Path = AUDIT_LOG_PATH,
) -> AuditEntry:
    """Append one real audit entry. `actor` and `reason` are required and must be non-empty -
    this is the mechanical enforcement point for Phase D's "requiring explicit authorization"
    requirement: nothing calling this function can record a promotion/approval/rollback event
    without naming who approved it and why."""
    actor = (actor or "").strip()
    reason = (reason or "").strip()
    if not actor:
        raise ValueError(
            "audit_log.record_event() requires a non-empty `actor` - no anonymous governance actions."
        )
    if not reason:
        raise ValueError("audit_log.record_event() requires a non-empty `reason`.")
    entry = AuditEntry(event_type=event_type, bp_id=bp_id, actor=actor, reason=reason, details=details or {})
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")
    return entry


def read_log(
    bp_id: str | None = None, event_type: str | None = None, log_path: Path = AUDIT_LOG_PATH
) -> list[dict[str, Any]]:
    """Real read-back of every entry (optionally filtered) - used both by tests (to verify a
    promotion/rollback was actually recorded) and by the final delivery report."""
    if not log_path.exists():
        return []
    entries = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if bp_id is not None and entry.get("bp_id") != bp_id:
                continue
            if event_type is not None and entry.get("event_type") != event_type:
                continue
            entries.append(entry)
    return entries
