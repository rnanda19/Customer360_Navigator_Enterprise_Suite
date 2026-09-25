"""
tests/deployment/test_bp5_readiness_verdict.py — Customer360 Navigator

Synthetic-fixture tests for src/deployment/bp5_readiness_verdict.py. Mirrors
tests/deployment/test_bp4_readiness_verdict.py's own structure: a tmp_path project root is built
fresh per test with exactly the real files each check needs, never touching the real device
project. Covers the happy path plus every documented FAIL/PENDING branch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from deployment import bp5_readiness_verdict as rv  # noqa: E402

VALID_REPORT = {
    "outcome_field": None,  # filled in per-outcome by _write_reports()
    "association_not_causation_disclaimer": "Findings are statistical ASSOCIATIONS only, not causal.",
    "field_level_ranking": [],
    "category_level_findings_by_field": {},
    "champion_shap_feature_importance": [],
    "company_process_field_finding": {},
    "champion_validation_snapshot": {},
    "barred_field_governance_disclosures": {},
    "narrative_text": {},
    "min_n_per_category_threshold_used": 30,
    "top_k_fields": 5,
    "top_k_categories_per_field": 5,
    "top_k_shap_features": 10,
}

VALID_ROLLUP_MANIFEST = {
    "bp_id": "bp5",
    "output_paths": {
        "dashboard_html": "reports/bp5_root_cause_driver_analytics/executive_rollup/d.html",
        "report_docx": "reports/bp5_root_cause_driver_analytics/executive_rollup/r.docx",
        "workbook_xlsx": "reports/bp5_root_cause_driver_analytics/executive_rollup/w.xlsx",
        "deck_pptx": "reports/bp5_root_cause_driver_analytics/executive_rollup/p.pptx",
    },
    "output_sizes_bytes": {},  # filled in per-test to match real written sizes
}

SIMPLE_SERVICE_SOURCE = '''
"""Minimal real-shaped BP5 service stand-in for tests."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/outcomes")
def outcomes():
    return []


@app.get("/report/{outcome}")
def report(outcome: str):
    return {}


@app.get("/report/{outcome}/top-drivers")
def top_drivers(outcome: str):
    return {}


@app.get("/rollup")
def rollup():
    return {}
'''

BROKEN_SERVICE_SOURCE = "raise ImportError('deliberately broken for test')\n"

MINIMAL_PYPROJECT = """
[project]
name = "customer360-navigator-enterprise-suite"
version = "0.1.0"
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.0",
]
"""


def _write_reports(project_root: Path, outcomes=rv.VALID_OUTCOMES, disclaimer=True, matching_field=True):
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for outcome in outcomes:
        report = dict(VALID_REPORT)
        report["outcome_field"] = outcome if matching_field else "wrong_outcome_field"
        if not disclaimer:
            report["association_not_causation_disclaimer"] = ""
        (artifacts_dir / rv.REPORT_FILENAMES[outcome]).write_text(json.dumps(report), encoding="utf-8")


def _write_rollup(project_root: Path, real_sizes: dict = None):
    out_dir = project_root / "reports" / rv.BP5_FOLDER / "executive_rollup"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(VALID_ROLLUP_MANIFEST))
    sizes = {}
    for key, rel_path in manifest["output_paths"].items():
        content = f"synthetic-{key}-content".encode("utf-8")
        (project_root / rel_path).write_bytes(content)
        sizes[key] = real_sizes.get(key, len(content)) if real_sizes else len(content)
    manifest["output_sizes_bytes"] = sizes
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / rv.ROLLUP_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")


def _write_project_skeleton(project_root: Path, service_source: str = SIMPLE_SERVICE_SOURCE):
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
    (project_root / "configs").mkdir(exist_ok=True)
    (project_root / "configs" / rv.BP5_CONFIG_FILE).write_text(
        yaml.safe_dump({"bp5": {"gate1_confirmed": True}}), encoding="utf-8"
    )
    services_dir = project_root / "src" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "__init__.py").touch()
    (services_dir / "__init__.py").touch()
    (services_dir / "bp5_driver_service.py").write_text(service_source, encoding="utf-8")
    tests_dir = project_root / "tests" / "services"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_bp5_driver_service.py").write_text("def test_placeholder():\n    assert True\n")


def _happy_path_root(tmp_path: Path) -> Path:
    _write_project_skeleton(tmp_path)
    _write_reports(tmp_path)
    _write_rollup(tmp_path)
    return tmp_path


def test_happy_path_fully_deployable_pending_only_on_missing_docker_ci(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.service_ready is True
    # No Dockerfile/CI staged in this minimal skeleton -> honestly PENDING, not fabricated PASS.
    assert verdict.fully_deployable is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["dockerfile_present"] == "PENDING"
    assert by_name["ci_workflow_present"] == "PENDING"


def test_fully_deployable_true_when_docker_and_ci_present(tmp_path):
    root = _happy_path_root(tmp_path)
    docker_dir = root / "src" / "services" / "docker" / "bp5_driver_service"
    docker_dir.mkdir(parents=True)
    (docker_dir / "Dockerfile").write_text("FROM python:3.11-slim\n")
    ci_dir = root / ".github" / "workflows"
    ci_dir.mkdir(parents=True)
    (ci_dir / "ci.yml").write_text("jobs:\n  x:\n    run: docker build bp5_driver_service\n")
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    assert verdict.fully_deployable is True


def test_missing_config_is_a_clean_fail_not_a_crash(tmp_path):
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    assert verdict.service_ready is False
    assert verdict.fully_deployable is False
    assert verdict.checks[0].status == "FAIL"


def test_missing_gate5_report_for_one_outcome_fails_that_outcome_only(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / rv.ARTIFACTS_RELATIVE_DIR / rv.REPORT_FILENAMES["outcome_2_timely_response_failure"]).unlink()
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    assert verdict.artifact_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_report_exists[outcome_1_intervention_required]"] == "PASS"
    assert by_name["gate5_report_exists[outcome_2_timely_response_failure]"] == "FAIL"


def test_gate5_report_missing_required_key_fails_schema_check(tmp_path):
    _write_project_skeleton(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    incomplete = dict(VALID_REPORT)
    incomplete["outcome_field"] = "outcome_1_intervention_required"
    del incomplete["narrative_text"]
    (artifacts_dir / rv.REPORT_FILENAMES["outcome_1_intervention_required"]).write_text(
        json.dumps(incomplete)
    )
    (artifacts_dir / rv.REPORT_FILENAMES["outcome_2_timely_response_failure"]).write_text(
        json.dumps({**VALID_REPORT, "outcome_field": "outcome_2_timely_response_failure"})
    )
    _write_rollup(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_report_schema[outcome_1_intervention_required]"] == "FAIL"
    assert "narrative_text" in next(
        c.detail for c in verdict.checks if c.name == "gate5_report_schema[outcome_1_intervention_required]"
    )


def test_outcome_field_filename_drift_is_caught(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_reports(tmp_path, outcomes=("outcome_1_intervention_required",), matching_field=False)
    outcome_2_path = tmp_path / rv.ARTIFACTS_RELATIVE_DIR / rv.REPORT_FILENAMES[
        "outcome_2_timely_response_failure"
    ]
    outcome_2_path.write_text(
        json.dumps({**VALID_REPORT, "outcome_field": "outcome_2_timely_response_failure"})
    )
    _write_rollup(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_report_outcome_matches_filename[outcome_1_intervention_required]"] == "FAIL"
    assert verdict.artifact_ready is False


def test_missing_disclaimer_fails_the_governance_guardrail_check(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_reports(tmp_path, disclaimer=False)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["association_not_causation_disclaimer_present[outcome_1_intervention_required]"] == "FAIL"
    key = "association_not_causation_disclaimer_present[outcome_2_timely_response_failure]"
    assert by_name[key] == "FAIL"


def test_missing_gate7_rollup_manifest_fails_artifact_ready(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_reports(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_manifest_exists"] == "FAIL"


def test_gate7_wrong_bp_id_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_reports(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    bad_manifest = {**VALID_ROLLUP_MANIFEST, "bp_id": "bp3"}
    (artifacts_dir / rv.ROLLUP_FILENAME).write_text(json.dumps(bad_manifest))
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_manifest_bp_id"] == "FAIL"


def test_gate7_output_size_drift_is_a_real_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    # Tamper the real dashboard file after the manifest recorded its original size.
    out_dir = root / "reports" / rv.BP5_FOLDER / "executive_rollup"
    (out_dir / "d.html").write_bytes(b"tampered content of a different length than recorded")
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_output_size_matches[dashboard_html]"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate7_output_file_missing_is_a_real_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    out_dir = root / "reports" / rv.BP5_FOLDER / "executive_rollup"
    (out_dir / "p.pptx").unlink()
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_output_exists[deck_pptx]"] == "FAIL"


def test_broken_service_import_fails_service_ready_never_crashes_the_check(tmp_path):
    _write_project_skeleton(tmp_path, service_source=BROKEN_SERVICE_SOURCE)
    _write_reports(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.service_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_module_imports_cleanly"] == "FAIL"


def test_missing_route_fails_route_check(tmp_path):
    missing_route_source = SIMPLE_SERVICE_SOURCE.replace(
        '@app.get("/rollup")\ndef rollup():\n    return {}\n', ""
    )
    _write_project_skeleton(tmp_path, service_source=missing_route_source)
    _write_reports(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_required_routes_present"] == "FAIL"
    assert "/rollup" in next(
        c.detail for c in verdict.checks if c.name == "service_required_routes_present"
    )


def test_missing_dependency_declaration_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["pydantic>=2.0"]\n'
    )
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["pyproject_declares_fastapi"] == "FAIL"
    assert by_name["pyproject_declares_pydantic"] == "PASS"


def test_missing_test_file_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "tests" / "services" / "test_bp5_driver_service.py").unlink()
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_files_present"] == "FAIL"


def test_run_tests_false_reports_pending_not_a_fabricated_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_suite_passes"] == "PENDING"


def test_to_dict_and_to_markdown_do_not_raise(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp5_deployment_readiness(root, run_tests=False)
    d = verdict.to_dict()
    assert d["bp_id"] == "bp5"
    md = verdict.to_markdown()
    assert "BP5 Deployment Readiness Verdict" in md


def test_resolve_project_root_env_override(tmp_path, monkeypatch):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker")
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    assert rv.resolve_project_root() == tmp_path


def test_resolve_project_root_env_override_wrong_path_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError):
        rv.resolve_project_root()
