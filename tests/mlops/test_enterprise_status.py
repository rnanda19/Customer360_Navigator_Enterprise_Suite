"""
tests/mlops/test_enterprise_status.py — Customer360 Navigator

Real pytest coverage for src/mlops/enterprise_status.py (Phase E Stage C). Every MLflow-touching
test uses the isolated, temp sqlite store from tests/mlops/conftest.py's mlflow_tracking_uri
fixture - never the real repo-root mlruns/. Synthetic registry_entries are used throughout so
these tests never depend on, or mutate, this project's real configs/*.yaml files.
"""

from __future__ import annotations

import hashlib

from mlops import registry
from mlops.enterprise_status import (
    assess_bp_governance_status,
    real_artifact_status,
)
from mlops.governance import LifecycleState


def _synthetic_entry(bp_id: str, **overrides) -> dict:
    base = {
        "bp_id": bp_id,
        "bp_name": f"{bp_id}_synthetic",
        "status": "gate1_confirmed_gate3_confirmed",
        "problem_type": "trained_classifier",
        "champion_identifier": "synthetic_model",
        "note": None,
        "config_file": f"configs/{bp_id}_synthetic.yaml",
    }
    base.update(overrides)
    return base


# ---- real_artifact_status -------------------------------------------------------------------


def test_real_artifact_status_absent_dir_reports_present_false(tmp_path):
    result = real_artifact_status("bp_test_missing", models_dir=tmp_path)
    assert result.present is False
    assert result.files == []
    assert result.sha256 == {}


def test_real_artifact_status_finds_real_files_and_computes_real_sha256(tmp_path):
    bp_dir = tmp_path / "bp_test_present"
    bp_dir.mkdir()
    content = b"not a real model, just a fixture for the hash check"
    (bp_dir / "champion.joblib").write_bytes(content)
    (bp_dir / ".gitkeep").write_text("")  # must NOT be picked up - not a known artifact extension
    (bp_dir / "notes.txt").write_text("ignore me")  # must NOT be picked up either

    result = real_artifact_status("bp_test_present", models_dir=tmp_path)

    assert result.present is True
    assert result.files == ["champion.joblib"]
    expected_sha256 = hashlib.sha256(content).hexdigest()
    assert result.sha256 == {"champion.joblib": expected_sha256}


def test_real_artifact_status_uses_models_subdir_name_override(tmp_path):
    bp_dir = tmp_path / "bp9_full_config_stem_name"
    bp_dir.mkdir()
    (bp_dir / "model.joblib").write_bytes(b"x")

    # Looking up by the short id with no override must NOT find it (real convention mismatch).
    assert real_artifact_status("bp9", models_dir=tmp_path).present is False
    # Passing the real full directory name must find it.
    found = real_artifact_status("bp9", models_dir=tmp_path, models_subdir_name="bp9_full_config_stem_name")
    assert found.present is True
    assert found.files == ["model.joblib"]


# ---- assess_bp_governance_status: problem_type / threshold applicability --------------------


def test_trained_classifier_is_governance_applicable():
    entries = [_synthetic_entry("bp_clf", problem_type="trained_classifier")]
    status = assess_bp_governance_status("bp_clf", registry_entries=entries)
    assert status.governance_applicable is True


def test_non_classifier_problem_types_are_not_governance_applicable():
    for problem_type in (
        "benchmark_pipeline",
        "association_reporting",
        "retrieval_strategy",
        "rule_engine",
        "gold_layer_aggregation",
    ):
        entries = [_synthetic_entry("bp_other", problem_type=problem_type)]
        status = assess_bp_governance_status("bp_other", registry_entries=entries)
        assert status.governance_applicable is False, problem_type


def test_unknown_bp_id_raises_rather_than_fabricating():
    import pytest

    entries = [_synthetic_entry("bp_known")]
    with pytest.raises(ValueError, match="bp_unknown"):
        assess_bp_governance_status("bp_unknown", registry_entries=entries)


# ---- assess_bp_governance_status: real MLflow registration state ----------------------------


def test_status_with_no_registration_reports_none_for_both_aliases(mlflow_tracking_uri):
    entries = [_synthetic_entry("bp_never_registered")]
    status = assess_bp_governance_status("bp_never_registered", registry_entries=entries)
    assert status.mlflow_registered_champion_version is None
    assert status.mlflow_registered_challenger_version is None


def test_status_reports_real_registered_champion_version(mlflow_tracking_uri, logged_run):
    run_id, artifact_subpath = logged_run
    registry.register_model_version(
        bp_id="bp_has_champion",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={"git_sha": "abc123"},
        evaluation_metrics={"accuracy": 0.9},
    )
    registry.set_alias("bp_has_champion", "champion", "1")

    entries = [_synthetic_entry("bp_has_champion")]
    status = assess_bp_governance_status("bp_has_champion", registry_entries=entries)
    assert status.mlflow_registered_champion_version == "1"
    assert status.mlflow_registered_challenger_version is None


# ---- lifecycle state derivation: every real branch, from real evidence ----------------------


def test_lifecycle_development_when_nothing_registered_and_no_gate3(mlflow_tracking_uri):
    entries = [_synthetic_entry("bp_dev", status="gate1_confirmed")]
    status = assess_bp_governance_status("bp_dev", registry_entries=entries)
    assert status.lifecycle_state == LifecycleState.DEVELOPMENT.value


def test_lifecycle_validation_when_gate3_confirmed_but_not_registered(mlflow_tracking_uri):
    entries = [_synthetic_entry("bp_val", status="gate1_confirmed_gate3_confirmed")]
    status = assess_bp_governance_status("bp_val", registry_entries=entries)
    assert status.lifecycle_state == LifecycleState.VALIDATION.value


def test_lifecycle_staging_when_challenger_registered_with_no_artifact_on_disk(
    mlflow_tracking_uri, logged_run
):
    run_id, artifact_subpath = logged_run
    registry.register_model_version(
        bp_id="bp_staging",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={},
    )
    registry.set_alias("bp_staging", "challenger", "1")

    entries = [_synthetic_entry("bp_staging", status="gate1_confirmed_gate3_confirmed")]
    status = assess_bp_governance_status("bp_staging", registry_entries=entries)
    assert status.lifecycle_state == LifecycleState.STAGING.value
    assert status.artifact_present is False


def test_lifecycle_production_when_champion_registered_and_artifact_present(
    mlflow_tracking_uri, logged_run, tmp_path, monkeypatch
):
    run_id, artifact_subpath = logged_run
    registry.register_model_version(
        bp_id="bp_prod",
        run_id=run_id,
        artifact_subpath=artifact_subpath,
        provenance_tags={},
        evaluation_metrics={},
    )
    registry.set_alias("bp_prod", "champion", "1")

    # Real artifact on disk, under the real full-config-stem directory name.
    bp_dir = tmp_path / "bp_prod_full_name"
    bp_dir.mkdir()
    (bp_dir / "champion.joblib").write_bytes(b"real enough for a presence check")
    monkeypatch.setattr("mlops.enterprise_status.MODELS_DIR", tmp_path)

    entries = [_synthetic_entry("bp_prod", config_file="configs/bp_prod_full_name.yaml")]
    status = assess_bp_governance_status("bp_prod", registry_entries=entries)
    assert status.lifecycle_state == LifecycleState.PRODUCTION.value
    assert status.artifact_present is True


# ---- has_governance_thresholds reflects the real governance.py threshold table --------------


def test_has_governance_thresholds_true_for_bp1_bp2_bp3():
    for bp_id in ("bp1", "bp2", "bp3"):
        entries = [_synthetic_entry(bp_id)]
        status = assess_bp_governance_status(bp_id, registry_entries=entries)
        assert status.has_governance_thresholds is True, bp_id


def test_has_governance_thresholds_false_for_a_bp_with_no_threshold_entry():
    entries = [_synthetic_entry("bp_no_threshold")]
    status = assess_bp_governance_status("bp_no_threshold", registry_entries=entries)
    assert status.has_governance_thresholds is False
