"""
tests/mlops/test_registry.py — Customer360 Navigator

Real pytest coverage for src/mlops/registry.py, against a real (but isolated, temp) sqlite-backed
MLflow registry - see tests/mlops/conftest.py for the mlflow_tracking_uri/logged_run fixtures.
"""

from __future__ import annotations

from mlops import registry


def test_registered_model_name_is_namespaced():
    assert registry.registered_model_name("bp1") == "customer360_bp1"


def test_ensure_registered_model_is_idempotent(mlflow_tracking_uri):
    name1 = registry.ensure_registered_model("bp_test_idempotent")
    name2 = registry.ensure_registered_model("bp_test_idempotent")
    assert name1 == name2 == "customer360_bp_test_idempotent"


def test_register_model_version_returns_real_version_info(logged_run):
    run_id, artifact_subpath = logged_run
    info = registry.register_model_version(
        bp_id="bp_test_register",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={"git_sha": "abc123", "software_versions": {"python": "3.10"}},
        evaluation_metrics={"accuracy": 0.9},
    )
    assert info.version == "1"
    assert info.run_id == run_id
    assert info.tags["metric__accuracy"] == "0.9"
    assert info.tags["provenance__git_sha"] == "abc123"


def test_version_tags_are_readable_back_from_registry(logged_run):
    run_id, artifact_subpath = logged_run
    info = registry.register_model_version(
        bp_id="bp_test_tags",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={"accuracy": 0.77},
    )
    tags = registry.get_version_tags("bp_test_tags", info.version)
    assert tags["metric__accuracy"] == "0.77"


def test_get_version_by_alias_returns_none_when_no_alias_set(mlflow_tracking_uri):
    registry.ensure_registered_model("bp_test_no_alias")
    assert registry.get_version_by_alias("bp_test_no_alias", "champion") is None


def test_set_alias_and_get_version_by_alias_round_trip(logged_run):
    run_id, artifact_subpath = logged_run
    info = registry.register_model_version(
        bp_id="bp_test_alias",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={"accuracy": 0.8},
    )
    registry.set_alias("bp_test_alias", "champion", info.version)
    fetched = registry.get_version_by_alias("bp_test_alias", "champion")
    assert fetched is not None
    assert fetched.version == info.version
    assert isinstance(fetched.version, str)


def test_set_alias_moves_alias_between_versions(logged_run):
    run_id, artifact_subpath = logged_run
    v1 = registry.register_model_version(
        bp_id="bp_test_move",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={"accuracy": 0.8},
    )
    v2 = registry.register_model_version(
        bp_id="bp_test_move",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={"accuracy": 0.9},
    )
    registry.set_alias("bp_test_move", "champion", v1.version)
    assert registry.get_version_by_alias("bp_test_move", "champion").version == v1.version
    registry.set_alias("bp_test_move", "champion", v2.version)
    assert registry.get_version_by_alias("bp_test_move", "champion").version == v2.version


def test_delete_alias_removes_it(logged_run):
    run_id, artifact_subpath = logged_run
    info = registry.register_model_version(
        bp_id="bp_test_delete_alias",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={"accuracy": 0.8},
    )
    registry.set_alias("bp_test_delete_alias", "challenger", info.version)
    assert registry.get_version_by_alias("bp_test_delete_alias", "challenger") is not None
    registry.delete_alias("bp_test_delete_alias", "challenger")
    assert registry.get_version_by_alias("bp_test_delete_alias", "challenger") is None


def test_delete_alias_on_nonexistent_alias_does_not_raise(mlflow_tracking_uri):
    registry.ensure_registered_model("bp_test_delete_missing")
    registry.delete_alias("bp_test_delete_missing", "no_such_alias")  # should not raise


def test_list_versions_returns_most_recent_first(logged_run):
    run_id, artifact_subpath = logged_run
    for acc in (0.5, 0.6, 0.7):
        registry.register_model_version(
            bp_id="bp_test_list",
            run_id=run_id,
            artifact_subpath=artifact_subpath,
            provenance_tags={},
            evaluation_metrics={"accuracy": acc},
        )
    versions = registry.list_versions("bp_test_list")
    assert [v.version for v in versions] == ["3", "2", "1"]
    assert all(isinstance(v.version, str) for v in versions)


def test_list_versions_on_unknown_model_returns_empty_list(mlflow_tracking_uri):
    assert registry.list_versions("bp_totally_unregistered") == []
