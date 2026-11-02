"""
tests/mlops/test_problem_specific_version_history.py — Customer360 Navigator

Tests for src/mlops/problem_specific_version_history.py (Phase I). All tests use tmp_path
isolation for the log file; the sync-level tests pass a synthetic `statuses` list (mirroring
enterprise_status.py's own `registry_entries` testability convention) rather than touching the
real configs/ directory, except one test that composes with the real
assess_all_bp_governance_status() to prove the real integration actually works end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from mlops import problem_specific_version_history as psvh


@dataclass
class _FakeStatus:
    """A minimal stand-in for mlops.enterprise_status.BPGovernanceStatus carrying only the three
    fields sync_version_history_from_enterprise_status() actually reads - this test file never
    imports the real dataclass, so it can't silently drift out of sync with a real BP's actual
    config and call this a "test"."""

    bp_id: str
    problem_type: str
    config_champion_identifier: Optional[str]


def test_record_version_if_changed_writes_an_initial_entry_on_first_call(tmp_path):
    log_path = tmp_path / "history.jsonl"
    entry = psvh.record_version_if_changed(
        "bp4", problem_type="benchmark_pipeline", config_champion_identifier="approach_a", log_path=log_path
    )
    assert entry is not None
    assert entry.change_type == "initial"
    assert entry.previous_identifier is None
    assert entry.config_champion_identifier == "approach_a"

    history = psvh.get_version_history("bp4", log_path=log_path)
    assert len(history) == 1


def test_record_version_if_changed_writes_nothing_when_identifier_is_unchanged(tmp_path):
    log_path = tmp_path / "history.jsonl"
    psvh.record_version_if_changed(
        "bp4", problem_type="benchmark_pipeline", config_champion_identifier="approach_a", log_path=log_path
    )
    second = psvh.record_version_if_changed(
        "bp4", problem_type="benchmark_pipeline", config_champion_identifier="approach_a", log_path=log_path
    )
    assert second is None
    assert len(psvh.get_version_history("bp4", log_path=log_path)) == 1


def test_record_version_if_changed_writes_a_changed_entry_when_identifier_differs(tmp_path):
    log_path = tmp_path / "history.jsonl"
    psvh.record_version_if_changed(
        "bp4", problem_type="benchmark_pipeline", config_champion_identifier="approach_a", log_path=log_path
    )
    second = psvh.record_version_if_changed(
        "bp4", problem_type="benchmark_pipeline", config_champion_identifier="approach_b", log_path=log_path
    )
    assert second is not None
    assert second.change_type == "changed"
    assert second.previous_identifier == "approach_a"
    assert second.config_champion_identifier == "approach_b"

    history = psvh.get_version_history("bp4", log_path=log_path)
    assert len(history) == 2
    assert history[0]["config_champion_identifier"] == "approach_a"
    assert history[1]["config_champion_identifier"] == "approach_b"


def test_record_version_if_changed_never_fabricates_an_entry_for_a_none_identifier(tmp_path):
    """Covers BP5/BP8's real, documented lack of a single discrete champion identifier - this
    must never silently invent one."""
    log_path = tmp_path / "history.jsonl"
    entry = psvh.record_version_if_changed(
        "bp5", problem_type="association_reporting", config_champion_identifier=None, log_path=log_path
    )
    assert entry is None
    assert psvh.get_version_history("bp5", log_path=log_path) == []
    # Confirms no file was even created for a BP that never has anything real to record.
    assert not log_path.exists()


def test_get_version_history_returns_empty_list_when_log_does_not_exist(tmp_path):
    log_path = tmp_path / "does_not_exist.jsonl"
    assert psvh.get_version_history(log_path=log_path) == []
    assert psvh.get_version_history("bp4", log_path=log_path) == []


def test_get_version_history_filters_by_bp_id(tmp_path):
    log_path = tmp_path / "history.jsonl"
    psvh.record_version_if_changed(
        "bp4", problem_type="benchmark_pipeline", config_champion_identifier="x", log_path=log_path
    )
    psvh.record_version_if_changed(
        "bp6", problem_type="retrieval_strategy", config_champion_identifier="y", log_path=log_path
    )
    assert len(psvh.get_version_history(log_path=log_path)) == 2
    bp4_only = psvh.get_version_history("bp4", log_path=log_path)
    assert len(bp4_only) == 1
    assert bp4_only[0]["bp_id"] == "bp4"


def test_sync_skips_trained_classifier_bps_entirely(tmp_path):
    """BP1-3 already have a real MLflow-based versioning mechanism (src/mlops/registry.py) - this
    module must never create a second, competing history for them."""
    log_path = tmp_path / "history.jsonl"
    statuses = [
        _FakeStatus(
            bp_id="bp1", problem_type="trained_classifier", config_champion_identifier="logistic_regression"
        ),
        _FakeStatus(bp_id="bp2", problem_type="trained_classifier", config_champion_identifier="xgboost"),
    ]
    written = psvh.sync_version_history_from_enterprise_status(statuses=statuses, log_path=log_path)
    assert written == []
    assert not log_path.exists()


def test_sync_writes_initial_entries_for_non_classifier_bps_with_a_real_identifier(tmp_path):
    log_path = tmp_path / "history.jsonl"
    statuses = [
        _FakeStatus(
            bp_id="bp4", problem_type="benchmark_pipeline", config_champion_identifier="polars_lazy_streaming"
        ),
        _FakeStatus(bp_id="bp5", problem_type="association_reporting", config_champion_identifier=None),
        _FakeStatus(
            bp_id="bp6", problem_type="retrieval_strategy", config_champion_identifier="taxonomy_bucket_match"
        ),
        _FakeStatus(
            bp_id="bp7",
            problem_type="rule_engine",
            config_champion_identifier="correlation_aware_plus_lr_diagnostic",
        ),
        _FakeStatus(bp_id="bp8", problem_type="gold_layer_aggregation", config_champion_identifier=None),
    ]
    written = psvh.sync_version_history_from_enterprise_status(statuses=statuses, log_path=log_path)
    written_bp_ids = {e.bp_id for e in written}
    assert written_bp_ids == {"bp4", "bp6", "bp7"}
    assert psvh.get_version_history("bp5", log_path=log_path) == []
    assert psvh.get_version_history("bp8", log_path=log_path) == []


def test_sync_is_idempotent_on_a_second_call_with_unchanged_statuses(tmp_path):
    log_path = tmp_path / "history.jsonl"
    statuses = [
        _FakeStatus(
            bp_id="bp4", problem_type="benchmark_pipeline", config_champion_identifier="polars_lazy_streaming"
        ),
    ]
    first = psvh.sync_version_history_from_enterprise_status(statuses=statuses, log_path=log_path)
    second = psvh.sync_version_history_from_enterprise_status(statuses=statuses, log_path=log_path)
    assert len(first) == 1
    assert second == []


def test_sync_records_a_real_change_when_a_bps_identifier_changes_between_calls(tmp_path):
    log_path = tmp_path / "history.jsonl"
    before = [
        _FakeStatus(bp_id="bp6", problem_type="retrieval_strategy", config_champion_identifier="strategy_a"),
    ]
    after = [
        _FakeStatus(bp_id="bp6", problem_type="retrieval_strategy", config_champion_identifier="strategy_b"),
    ]
    psvh.sync_version_history_from_enterprise_status(statuses=before, log_path=log_path)
    written = psvh.sync_version_history_from_enterprise_status(statuses=after, log_path=log_path)
    assert len(written) == 1
    assert written[0].change_type == "changed"
    assert written[0].previous_identifier == "strategy_a"
    assert written[0].config_champion_identifier == "strategy_b"


def test_sync_against_the_real_enterprise_status_only_touches_non_classifier_bps(tmp_path):
    """Real end-to-end integration test: no `statuses` argument, so this calls the real
    assess_all_bp_governance_status() against this project's actual configs/ directory. Does not
    assert specific identifier values (those are this project's real, evolving config data, not
    this test's concern) - only the structural guarantee that BP1-3 (trained_classifier) are
    never written here, and any BP4-8 entry written always carries a real, non-None
    identifier."""
    log_path = tmp_path / "history.jsonl"
    written = psvh.sync_version_history_from_enterprise_status(log_path=log_path)
    for entry in written:
        assert entry.bp_id not in {"bp1", "bp2", "bp3"}
        assert entry.config_champion_identifier is not None
        assert entry.problem_type in psvh._NON_CLASSIFIER_PROBLEM_TYPES
