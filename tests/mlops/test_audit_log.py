"""
tests/mlops/test_audit_log.py — Customer360 Navigator

Real pytest coverage for src/mlops/audit_log.py.
"""

from __future__ import annotations

import pytest

from mlops import audit_log


def test_record_event_requires_non_empty_actor(tmp_path):
    with pytest.raises(ValueError):
        audit_log.record_event(
            "promotion", "bp1", actor="", reason="some reason", log_path=tmp_path / "log.jsonl"
        )


def test_record_event_requires_non_empty_reason(tmp_path):
    with pytest.raises(ValueError):
        audit_log.record_event(
            "promotion", "bp1", actor="alice", reason="   ", log_path=tmp_path / "log.jsonl"
        )


def test_record_event_round_trips_through_read_log(tmp_path):
    log_path = tmp_path / "log.jsonl"
    entry = audit_log.record_event(
        "promotion", "bp1", actor="alice", reason="looks good", details={"version": "1"}, log_path=log_path
    )
    entries = audit_log.read_log(log_path=log_path)
    assert len(entries) == 1
    assert entries[0]["entry_id"] == entry.entry_id
    assert entries[0]["actor"] == "alice"
    assert entries[0]["details"]["version"] == "1"


def test_read_log_filters_by_bp_id_and_event_type(tmp_path):
    log_path = tmp_path / "log.jsonl"
    audit_log.record_event("promotion", "bp1", actor="alice", reason="r1", log_path=log_path)
    audit_log.record_event("rollback", "bp1", actor="bob", reason="r2", log_path=log_path)
    audit_log.record_event("promotion", "bp2", actor="carol", reason="r3", log_path=log_path)

    assert len(audit_log.read_log(bp_id="bp1", log_path=log_path)) == 2
    assert len(audit_log.read_log(event_type="promotion", log_path=log_path)) == 2
    assert len(audit_log.read_log(bp_id="bp1", event_type="rollback", log_path=log_path)) == 1


def test_read_log_on_missing_file_returns_empty_list(tmp_path):
    assert audit_log.read_log(log_path=tmp_path / "nope.jsonl") == []


def test_every_entry_has_a_unique_entry_id(tmp_path):
    log_path = tmp_path / "log.jsonl"
    for i in range(5):
        audit_log.record_event("promotion", "bp1", actor="alice", reason=f"r{i}", log_path=log_path)
    entries = audit_log.read_log(log_path=log_path)
    ids = {e["entry_id"] for e in entries}
    assert len(ids) == 5
