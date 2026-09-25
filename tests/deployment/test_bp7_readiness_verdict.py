"""
tests/deployment/test_bp7_readiness_verdict.py — Customer360 Navigator

Synthetic-fixture tests for src/deployment/bp7_readiness_verdict.py. Mirrors
tests/deployment/test_bp5_readiness_verdict.py's and test_bp6_readiness_verdict.py's own
structure: a tmp_path project root is built fresh per test with exactly the real files each check
needs, never touching the real device project and never writing/reading anything resembling the
real ~540MB Gate 5 CSV (the synthetic fixture CSV here carries only the real header plus a
handful of rows, purely to exercise the zero-row schema probe). Covers the happy path plus every
documented FAIL/WARN/PENDING branch, with particular attention to the two checks that are
genuinely BP7-specific: the Gate 5 records-CSV schema-only probe and the self-test reconciliation
wiring check (BP7's own analogue to BP5's association disclaimer and BP6's human-in-the-loop
guardrail - here a static code-wiring check, not a data-field check).
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

from deployment import bp7_readiness_verdict as rv  # noqa: E402

VALID_GATE5_SUMMARY = {
    "bp_id": "bp7",
    "gate": 5,
    "generated_at_utc": "2026-09-25T06:13:24.780323+00:00",
    "live_row_count": 1048575,
    "champion_rule_scheme": "correlation_aware_plus_lr_diagnostic",
    "champion_weights_normalized": {"bp2": 0.222714, "bp3": 0.170774, "bp4": 0.606512},
    "intervention_threshold": 0.5,
    "weight_rederivation_cross_check": {"matches_config": True},
    "champion_stats": {"intervention_flag_rate": 0.768415},
    "cross_checks_vs_gate3_gate4": {"all_passed": True},
    "gate4_bootstrap_ci_carried_forward": {"intervention_flag_rate_ci_95": [0.767609, 0.769243]},
    "contribution_decomposition_summary": {"reconstruction_exact_within_tolerance": True},
    "disparate_impact_audit": {"adverse_impact_ratio": 0.908127},
    "upstream_field_coverage": {"bp4_join_coverage": 0.975368},
    "recommended_action_breakdown": {"STANDARD_QUEUE": 500000},
    "bp4_tier_intervention_crosstab": {},
    "n_rows_covered_by_action_breakdown": 1048575,
    "n_rows_covered_by_tier_crosstab": 1048575,
    "compliance_touchpoint": "Decision layer & reporting",
    "records_csv_path": "notebooks/bp7_customer_navigator_decision_engine/artifacts/"
    "gate5_full_population_decision_records.csv",
    "action_breakdown_csv_path": "notebooks/bp7_customer_navigator_decision_engine/artifacts/"
    "gate5_recommended_action_breakdown.csv",
    "tier_crosstab_csv_path": "notebooks/bp7_customer_navigator_decision_engine/artifacts/"
    "gate5_bp4_tier_intervention_crosstab.csv",
}

VALID_ROLLUP_MANIFEST = {
    "bp_id": "bp7",
    "gate": 7,
    "output_paths": {
        "dashboard_html": "reports/bp7_customer_navigator_decision_engine/executive_rollup/d.html",
        "report_docx": "reports/bp7_customer_navigator_decision_engine/executive_rollup/r.docx",
        "workbook_xlsx": "reports/bp7_customer_navigator_decision_engine/executive_rollup/w.xlsx",
        "deck_pptx": "reports/bp7_customer_navigator_decision_engine/executive_rollup/p.pptx",
    },
    "output_sizes_bytes": {},  # filled in per-test to match real written sizes
}

SIMPLE_SERVICE_SOURCE = '''
"""Minimal real-shaped BP7 service stand-in for tests."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/decide/self-test")
def decide_self_test():
    return {}


@app.get("/decide/{complaint_id}")
def decide(complaint_id: int):
    return {}
'''

BROKEN_SERVICE_SOURCE = "raise ImportError('deliberately broken for test')\n"

VALID_FEATURES_SOURCE = '''
"""Minimal real-shaped BP7 features stand-in for tests."""

DEFAULT_INTERVENTION_THRESHOLD: float = 0.5


def summarize_contribution_decomposition(rows):
    return {"reconstruction_exact_within_tolerance": True}
'''

BROKEN_FEATURES_SOURCE = "raise ImportError('deliberately broken features module for test')\n"

FEATURES_MISSING_ATTR_SOURCE = '''
"""Real-shaped but incomplete BP7 features stand-in - missing DEFAULT_INTERVENTION_THRESHOLD."""


def summarize_contribution_decomposition(rows):
    return {"reconstruction_exact_within_tolerance": True}
'''

MINIMAL_PYPROJECT = """
[project]
name = "customer360-navigator-enterprise-suite"
version = "0.1.0"
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.0",
    "polars>=1.9",
]
"""


def _write_gate5_records_csv(project_root: Path, columns=None):
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cols = list(columns) if columns is not None else list(rv.EXPECTED_GATE5_CSV_COLUMNS)
    header = ",".join(cols)
    # A handful of synthetic rows only - never anything resembling the real ~540MB/1,048,575-row
    # file. Values are placeholders; this check only ever probes the header (zero-row scan).
    row_values = ["1" for _ in cols]
    row = ",".join(row_values)
    (project_root / rv.ARTIFACTS_RELATIVE_DIR / rv.RECORDS_CSV_FILENAME).write_text(
        header + "\n" + row + "\n", encoding="utf-8"
    )


def _write_gate5_summary(project_root: Path, overrides: dict = None):
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary = dict(VALID_GATE5_SUMMARY)
    if overrides:
        summary.update(overrides)
    (artifacts_dir / rv.GATE5_SUMMARY_FILENAME).write_text(json.dumps(summary), encoding="utf-8")


def _write_rollup(project_root: Path, real_sizes: dict = None, manifest_overrides: dict = None):
    out_dir = project_root / "reports" / rv.BP7_FOLDER / "executive_rollup"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(VALID_ROLLUP_MANIFEST))
    if manifest_overrides:
        manifest.update(manifest_overrides)
    sizes = {}
    for key, rel_path in manifest["output_paths"].items():
        content = f"synthetic-{key}-content".encode("utf-8")
        (project_root / rel_path).write_bytes(content)
        sizes[key] = real_sizes.get(key, len(content)) if real_sizes else len(content)
    manifest["output_sizes_bytes"] = sizes
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / rv.ROLLUP_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")


def _write_project_skeleton(
    project_root: Path,
    service_source: str = SIMPLE_SERVICE_SOURCE,
    features_source: str = VALID_FEATURES_SOURCE,
):
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
    (project_root / "configs").mkdir(exist_ok=True)
    (project_root / "configs" / rv.BP7_CONFIG_FILE).write_text(
        yaml.safe_dump({"bp7": {"gate1_confirmed": True}}), encoding="utf-8"
    )
    (project_root / "src" / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "__init__.py").touch()

    services_dir = project_root / "src" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)
    (services_dir / "__init__.py").touch()
    (services_dir / "bp7_decision_engine_service.py").write_text(service_source, encoding="utf-8")

    features_dir = project_root / "src" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "__init__.py").touch()
    (features_dir / "bp7_decision_engine_features.py").write_text(features_source, encoding="utf-8")

    tests_dir = project_root / "tests" / "services"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_bp7_decision_engine_service.py").write_text(
        "def test_placeholder():\n    assert True\n"
    )


def _happy_path_root(tmp_path: Path) -> Path:
    _write_project_skeleton(tmp_path)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    return tmp_path


def test_happy_path_fully_deployable_pending_only_on_missing_docker_ci(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.service_ready is True
    # No Dockerfile/CI staged in this minimal skeleton -> honestly PENDING, not fabricated PASS.
    assert verdict.fully_deployable is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["dockerfile_present"] == "PENDING"
    assert by_name["ci_workflow_present"] == "PENDING"


def test_fully_deployable_true_when_docker_and_ci_present(tmp_path):
    root = _happy_path_root(tmp_path)
    docker_dir = root / "src" / "services" / "docker" / "bp7_decision_engine_service"
    docker_dir.mkdir(parents=True)
    (docker_dir / "Dockerfile").write_text("FROM python:3.11-slim\n")
    ci_dir = root / ".github" / "workflows"
    ci_dir.mkdir(parents=True)
    (ci_dir / "ci.yml").write_text("jobs:\n  x:\n    run: docker build bp7_decision_engine_service\n")
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    assert verdict.fully_deployable is True


def test_missing_config_is_a_clean_fail_not_a_crash(tmp_path):
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    assert verdict.service_ready is False
    assert verdict.fully_deployable is False
    assert verdict.checks[0].status == "FAIL"


def test_missing_gate5_records_csv_fails_artifact_ready(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_records_csv_exists"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate5_records_csv_schema_drift_missing_column_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    csv_path = root / rv.ARTIFACTS_RELATIVE_DIR / rv.RECORDS_CSV_FILENAME
    columns = [c for c in rv.EXPECTED_GATE5_CSV_COLUMNS if c != "tags_group"]
    csv_path.write_text(",".join(columns) + "\n" + ",".join("1" for _ in columns) + "\n", encoding="utf-8")
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_records_csv_schema_matches"] == "FAIL"
    assert "tags_group" in next(
        c.detail for c in verdict.checks if c.name == "gate5_records_csv_schema_matches"
    )
    assert verdict.artifact_ready is False


def test_gate5_records_csv_schema_matches_real_header_order(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_records_csv_schema_matches"] == "PASS"


def test_missing_gate5_summary_json_fails_artifact_ready(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate5_records_csv(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_summary_json_exists"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate5_summary_missing_required_key_fails_schema(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate5_records_csv(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    incomplete = dict(VALID_GATE5_SUMMARY)
    del incomplete["disparate_impact_audit"]
    (artifacts_dir / rv.GATE5_SUMMARY_FILENAME).write_text(json.dumps(incomplete))
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_summary_json_schema"] == "FAIL"
    assert "disparate_impact_audit" in next(
        c.detail for c in verdict.checks if c.name == "gate5_summary_json_schema"
    )


def test_gate5_summary_identity_drift_is_caught(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path, overrides={"gate": 3})
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_summary_identity_matches"] == "FAIL"
    assert verdict.artifact_ready is False


def test_missing_gate7_rollup_manifest_fails_artifact_ready(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_manifest_exists"] == "FAIL"


def test_gate7_wrong_bp_id_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    bad_manifest = {**VALID_ROLLUP_MANIFEST, "bp_id": "bp4"}
    (artifacts_dir / rv.ROLLUP_FILENAME).write_text(json.dumps(bad_manifest))
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_manifest_bp_id"] == "FAIL"


def test_gate7_output_size_drift_is_a_real_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    out_dir = root / "reports" / rv.BP7_FOLDER / "executive_rollup"
    (out_dir / "d.html").write_bytes(b"tampered content of a different length than recorded")
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_output_size_matches[dashboard_html]"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate7_output_file_missing_is_a_real_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    out_dir = root / "reports" / rv.BP7_FOLDER / "executive_rollup"
    (out_dir / "p.pptx").unlink()
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_output_exists[deck_pptx]"] == "FAIL"


def test_broken_service_import_fails_service_ready_never_crashes_the_check(tmp_path):
    _write_project_skeleton(tmp_path, service_source=BROKEN_SERVICE_SOURCE)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.service_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_module_imports_cleanly"] == "FAIL"


def test_missing_route_fails_route_check(tmp_path):
    missing_route_source = SIMPLE_SERVICE_SOURCE.replace(
        '@app.get("/decide/self-test")\ndef decide_self_test():\n    return {}\n', ""
    )
    _write_project_skeleton(tmp_path, service_source=missing_route_source)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_required_routes_present"] == "FAIL"
    assert "/decide/self-test" in next(
        c.detail for c in verdict.checks if c.name == "service_required_routes_present"
    )


def test_wrong_http_method_on_decide_fails_route_check(tmp_path):
    """/decide/{complaint_id} declared as POST instead of GET must fail the route check -
    path-only matching would incorrectly let this real mismatch slide."""
    wrong_method_source = SIMPLE_SERVICE_SOURCE.replace(
        '@app.get("/decide/{complaint_id}")\ndef decide(complaint_id: int):\n    return {}\n',
        '@app.post("/decide/{complaint_id}")\ndef decide(complaint_id: int):\n    return {}\n',
    )
    _write_project_skeleton(tmp_path, service_source=wrong_method_source)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_required_routes_present"] == "FAIL"


def test_self_test_reconciliation_wiring_passes_on_real_shape(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["self_test_reconciliation_function_wired"] == "PASS"
    assert verdict.service_ready is True


def test_self_test_reconciliation_wiring_fails_on_broken_features_import(tmp_path):
    _write_project_skeleton(tmp_path, features_source=BROKEN_FEATURES_SOURCE)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["self_test_reconciliation_function_wired"] == "FAIL"
    assert verdict.service_ready is False


def test_self_test_reconciliation_wiring_fails_on_missing_attr(tmp_path):
    _write_project_skeleton(tmp_path, features_source=FEATURES_MISSING_ATTR_SOURCE)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["self_test_reconciliation_function_wired"] == "FAIL"
    assert "DEFAULT_INTERVENTION_THRESHOLD" in next(
        c.detail for c in verdict.checks if c.name == "self_test_reconciliation_function_wired"
    )
    assert verdict.service_ready is False


def test_self_test_reconciliation_wiring_never_invokes_the_real_function(tmp_path, monkeypatch):
    """The static wiring check must never actually CALL summarize_contribution_decomposition - a
    real call would require the real 540MB Gate 5 CSV read into a polars frame, well outside what
    a readiness-verdict check should ever do. A function that raises if called (but is otherwise
    present/callable) must still PASS this check."""
    calling_features_source = '''
DEFAULT_INTERVENTION_THRESHOLD: float = 0.5


def summarize_contribution_decomposition(rows):
    raise AssertionError("summarize_contribution_decomposition must never be invoked by the readiness check")
'''
    _write_project_skeleton(tmp_path, features_source=calling_features_source)
    _write_gate5_records_csv(tmp_path)
    _write_gate5_summary(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["self_test_reconciliation_function_wired"] == "PASS"


def test_missing_dependency_declaration_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["pydantic>=2.0", "polars>=1.9"]\n'
    )
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["pyproject_declares_fastapi"] == "FAIL"
    assert by_name["pyproject_declares_pydantic"] == "PASS"
    assert by_name["pyproject_declares_polars"] == "PASS"


def test_missing_polars_dependency_declaration_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["fastapi>=0.115", "pydantic>=2.0"]\n'
    )
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["pyproject_declares_polars"] == "FAIL"


def test_missing_test_file_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "tests" / "services" / "test_bp7_decision_engine_service.py").unlink()
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_files_present"] == "FAIL"


def test_run_tests_false_reports_pending_not_a_fabricated_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_suite_passes"] == "PENDING"


def test_to_dict_and_to_markdown_do_not_raise(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp7_deployment_readiness(root, run_tests=False)
    d = verdict.to_dict()
    assert d["bp_id"] == "bp7"
    md = verdict.to_markdown()
    assert "BP7 Deployment Readiness Verdict" in md


def test_resolve_project_root_env_override(tmp_path, monkeypatch):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker")
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    assert rv.resolve_project_root() == tmp_path


def test_resolve_project_root_env_override_wrong_path_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError):
        rv.resolve_project_root()
