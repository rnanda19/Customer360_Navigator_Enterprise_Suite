"""
tests/deployment/test_bp6_readiness_verdict.py — Customer360 Navigator

Synthetic-fixture tests for src/deployment/bp6_readiness_verdict.py. Mirrors
tests/deployment/test_bp5_readiness_verdict.py's own structure: a tmp_path project root is built
fresh per test with exactly the real files each check needs, never touching the real device
project. Covers the happy path plus every documented FAIL/WARN/PENDING branch, with particular
attention to the two checks that are genuinely BP6-specific: the human-in-the-loop governance
guardrail (Gate 5 and its Gate 7 rollup surfacing) and the GEMINI_API_KEY WARN-not-FAIL behavior.
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

from deployment import bp6_readiness_verdict as rv  # noqa: E402

VALID_PII_REPORT = {
    "n_rows_screened": 13083,
    "n_rows_flagged": 0,
    "pct_rows_flagged": 0.0,
    "category_counts": {"email": 0, "phone": 0, "ssn_like": 0, "card_like": 0},
    "pii_categories_checked": ["email", "phone", "ssn_like", "card_like"],
}

VALID_EVIDENCE_REGISTRY = {
    "generated_at_utc": "2026-09-24T15:44:04.745180+00:00",
    "upstream_bps": {
        "bp1": {"bp_id": "bp1", "artifacts": []},
        "bp2": {"bp_id": "bp2", "artifacts": []},
        "bp3": {"bp_id": "bp3", "artifacts": []},
        "bp4": {"bp_id": "bp4", "artifacts": []},
        "bp5": {"bp_id": "bp5", "artifacts": []},
    },
}

VALID_GATE3_REPORT = {
    "bp_id": "bp6",
    "gate": 3,
    "compliance_touchpoint": "Retrieval strategy inventory entry opened",
    "champion_strategy": "taxonomy_bucket_match",
    "champion_coverage": 0.333333,
    "runner_up_strategy": "raw_string_match",
    "runner_up_coverage": 0.0,
    "candidates_evaluated": ["taxonomy_bucket_match", "raw_string_match"],
    "candidates_failed": [],
    "strategy_a_detail": {"strategy": "taxonomy_bucket_match"},
    "strategy_b_detail": {"strategy": "raw_string_match"},
    "generated_at_utc": "2026-09-24T15:44:05.107516+00:00",
}

VALID_GATE5_REPORT = {
    "bp_id": "bp6",
    "gate": 5,
    "compliance_touchpoint": "UDAAP language review; NIST AI RMF Measure/Manage check",
    "customer_message_context": {"category": "cash_withdrawal_not_recognised"},
    "generated_recommendation_text": "synthetic recommendation text",
    "model_used": "gemini-3.5-flash",
    "input_tokens": 1032,
    "output_tokens": 113,
    "finish_reason": "FinishReason.STOP",
    "citation_table": [],
    "citation_check": {"passed": True},
    "udaap_check": {"passed": True},
    "nist_ai_rmf_risk_category": {"risk_category_value": "MEDIUM"},
    "approval_status": "PENDING_HUMAN_REVIEW",
    "auto_applied": False,
    "human_in_the_loop_required": True,
    "human_in_the_loop_auto_apply_allowed": False,
    "generated_at_utc": "2026-09-24T15:44:11.451308+00:00",
}

VALID_ROLLUP_MANIFEST = {
    "bp_id": "bp6",
    "human_in_the_loop_required": True,
    "output_paths": {
        "dashboard_html": "reports/bp6_genai_resolution_assistant/executive_rollup/d.html",
        "report_docx": "reports/bp6_genai_resolution_assistant/executive_rollup/r.docx",
        "workbook_xlsx": "reports/bp6_genai_resolution_assistant/executive_rollup/w.xlsx",
        "deck_pptx": "reports/bp6_genai_resolution_assistant/executive_rollup/p.pptx",
    },
    "output_sizes_bytes": {},  # filled in per-test to match real written sizes
}

SIMPLE_SERVICE_SOURCE = '''
"""Minimal real-shaped BP6 service stand-in for tests."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/resolve")
def resolve():
    return {}


@app.post("/resolve/self-test")
def resolve_self_test():
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


def _write_gate2_artifacts(project_root: Path, flagged: bool = False, missing_csv: bool = False):
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    pii_report = dict(VALID_PII_REPORT)
    if flagged:
        pii_report["n_rows_flagged"] = 3
    (artifacts_dir / rv.GATE2_PII_REPORT_FILENAME).write_text(json.dumps(pii_report), encoding="utf-8")
    (artifacts_dir / rv.GATE2_EVIDENCE_REGISTRY_FILENAME).write_text(
        json.dumps(VALID_EVIDENCE_REGISTRY), encoding="utf-8"
    )
    if not missing_csv:
        (artifacts_dir / rv.GATE2_PII_SCREENED_CSV_FILENAME).write_text(
            "masked_text,category,common_taxonomy_bucket\n", encoding="utf-8"
        )


def _write_gate3_artifact(project_root: Path, overrides: dict = None):
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report = dict(VALID_GATE3_REPORT)
    if overrides:
        report.update(overrides)
    (artifacts_dir / rv.GATE3_RETRIEVAL_INVENTORY_FILENAME).write_text(
        json.dumps(report), encoding="utf-8"
    )


def _write_gate5_artifact(project_root: Path, overrides: dict = None):
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report = dict(VALID_GATE5_REPORT)
    if overrides:
        report.update(overrides)
    (artifacts_dir / rv.GATE5_RECOMMENDATION_FILENAME).write_text(json.dumps(report), encoding="utf-8")


def _write_rollup(project_root: Path, real_sizes: dict = None, manifest_overrides: dict = None):
    out_dir = project_root / "reports" / rv.BP6_FOLDER / "executive_rollup"
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


def _write_project_skeleton(project_root: Path, service_source: str = SIMPLE_SERVICE_SOURCE):
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
    (project_root / "configs").mkdir(exist_ok=True)
    (project_root / "configs" / rv.BP6_CONFIG_FILE).write_text(
        yaml.safe_dump({"bp6": {"gate1_confirmed": True}}), encoding="utf-8"
    )
    services_dir = project_root / "src" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "__init__.py").touch()
    (services_dir / "__init__.py").touch()
    (services_dir / "bp6_resolution_service.py").write_text(service_source, encoding="utf-8")
    tests_dir = project_root / "tests" / "services"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_bp6_resolution_service.py").write_text("def test_placeholder():\n    assert True\n")


def _happy_path_root(tmp_path: Path) -> Path:
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    return tmp_path


def test_happy_path_fully_deployable_pending_only_on_missing_docker_ci(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.service_ready is True
    # No Dockerfile/CI staged in this minimal skeleton -> honestly PENDING, not fabricated PASS.
    assert verdict.fully_deployable is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["dockerfile_present"] == "PENDING"
    assert by_name["ci_workflow_present"] == "PENDING"


def test_fully_deployable_true_when_docker_and_ci_present(tmp_path):
    root = _happy_path_root(tmp_path)
    docker_dir = root / "src" / "services" / "docker" / "bp6_resolution_service"
    docker_dir.mkdir(parents=True)
    (docker_dir / "Dockerfile").write_text("FROM python:3.11-slim\n")
    ci_dir = root / ".github" / "workflows"
    ci_dir.mkdir(parents=True)
    (ci_dir / "ci.yml").write_text("jobs:\n  x:\n    run: docker build bp6_resolution_service\n")
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    assert verdict.fully_deployable is True


def test_missing_config_is_a_clean_fail_not_a_crash(tmp_path):
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    assert verdict.service_ready is False
    assert verdict.fully_deployable is False
    assert verdict.checks[0].status == "FAIL"


def test_missing_gate2_pii_report_fails_artifact_ready(tmp_path):
    _write_project_skeleton(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / rv.GATE2_EVIDENCE_REGISTRY_FILENAME).write_text(
        json.dumps(VALID_EVIDENCE_REGISTRY), encoding="utf-8"
    )
    (artifacts_dir / rv.GATE2_PII_SCREENED_CSV_FILENAME).write_text("masked_text\n", encoding="utf-8")
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate2_pii_screening_report_exists"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate2_pii_screened_csv_missing_fails_even_when_reports_present(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / rv.ARTIFACTS_RELATIVE_DIR / rv.GATE2_PII_SCREENED_CSV_FILENAME).unlink()
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate2_pii_screened_narrative_csv_exists"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate2_evidence_registry_missing_upstream_bp_fails_schema(tmp_path):
    _write_project_skeleton(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / rv.GATE2_PII_REPORT_FILENAME).write_text(
        json.dumps(VALID_PII_REPORT), encoding="utf-8"
    )
    incomplete_registry = json.loads(json.dumps(VALID_EVIDENCE_REGISTRY))
    del incomplete_registry["upstream_bps"]["bp5"]
    (artifacts_dir / rv.GATE2_EVIDENCE_REGISTRY_FILENAME).write_text(
        json.dumps(incomplete_registry), encoding="utf-8"
    )
    (artifacts_dir / rv.GATE2_PII_SCREENED_CSV_FILENAME).write_text("masked_text\n", encoding="utf-8")
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate2_evidence_source_registry_schema"] == "FAIL"
    assert "bp5" in next(
        c.detail for c in verdict.checks if c.name == "gate2_evidence_source_registry_schema"
    )


def test_gate3_missing_required_key_fails_schema(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    incomplete = dict(VALID_GATE3_REPORT)
    del incomplete["champion_coverage"]
    (artifacts_dir / rv.GATE3_RETRIEVAL_INVENTORY_FILENAME).write_text(json.dumps(incomplete))
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate3_retrieval_strategy_inventory_schema"] == "FAIL"
    assert "champion_coverage" in next(
        c.detail for c in verdict.checks if c.name == "gate3_retrieval_strategy_inventory_schema"
    )


def test_gate3_identity_drift_is_caught(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path, overrides={"gate": 5})
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate3_retrieval_strategy_identity_matches"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate5_missing_required_key_fails_schema(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    incomplete = dict(VALID_GATE5_REPORT)
    del incomplete["citation_table"]
    (artifacts_dir / rv.GATE5_RECOMMENDATION_FILENAME).write_text(json.dumps(incomplete))
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_recommendation_artifact_schema"] == "FAIL"


@pytest.mark.parametrize(
    "overrides",
    [
        {"auto_applied": True},
        {"human_in_the_loop_required": False},
        {"human_in_the_loop_auto_apply_allowed": True},
        {"approval_status": "AUTO_APPROVED"},
    ],
)
def test_gate5_governance_guardrail_fails_on_any_real_drift(tmp_path, overrides):
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path, overrides=overrides)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_human_in_the_loop_governance_guardrail"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate5_governance_guardrail_passes_on_real_shape(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate5_human_in_the_loop_governance_guardrail"] == "PASS"


def test_missing_gate7_rollup_manifest_fails_artifact_ready(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_manifest_exists"] == "FAIL"


def test_gate7_wrong_bp_id_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    artifacts_dir = tmp_path / rv.ARTIFACTS_RELATIVE_DIR
    bad_manifest = {**VALID_ROLLUP_MANIFEST, "bp_id": "bp3"}
    (artifacts_dir / rv.ROLLUP_FILENAME).write_text(json.dumps(bad_manifest))
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_manifest_bp_id"] == "FAIL"


def test_gate7_human_in_the_loop_flag_missing_fails_but_does_not_crash(tmp_path):
    root = _happy_path_root(tmp_path)
    manifest_path = root / rv.ARTIFACTS_RELATIVE_DIR / rv.ROLLUP_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["human_in_the_loop_required"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_human_in_the_loop_required_surfaced"] == "FAIL"


def test_gate7_human_in_the_loop_flag_present_is_an_informational_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    by_detail = {c.name: c.detail for c in verdict.checks}
    assert by_name["gate7_human_in_the_loop_required_surfaced"] == "PASS"
    assert "True" in by_detail["gate7_human_in_the_loop_required_surfaced"]


def test_gate7_output_size_drift_is_a_real_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    out_dir = root / "reports" / rv.BP6_FOLDER / "executive_rollup"
    (out_dir / "d.html").write_bytes(b"tampered content of a different length than recorded")
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_output_size_matches[dashboard_html]"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate7_output_file_missing_is_a_real_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    out_dir = root / "reports" / rv.BP6_FOLDER / "executive_rollup"
    (out_dir / "p.pptx").unlink()
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_rollup_output_exists[deck_pptx]"] == "FAIL"


def test_broken_service_import_fails_service_ready_never_crashes_the_check(tmp_path):
    _write_project_skeleton(tmp_path, service_source=BROKEN_SERVICE_SOURCE)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.service_ready is False
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_module_imports_cleanly"] == "FAIL"


def test_missing_route_fails_route_check(tmp_path):
    missing_route_source = SIMPLE_SERVICE_SOURCE.replace(
        '@app.post("/resolve/self-test")\ndef resolve_self_test():\n    return {}\n', ""
    )
    _write_project_skeleton(tmp_path, service_source=missing_route_source)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_required_routes_present"] == "FAIL"
    assert "/resolve/self-test" in next(
        c.detail for c in verdict.checks if c.name == "service_required_routes_present"
    )


def test_wrong_http_method_on_resolve_fails_route_check(tmp_path):
    """/resolve declared as GET instead of POST must fail the route check - path-only matching
    would incorrectly let this real mismatch slide."""
    wrong_method_source = SIMPLE_SERVICE_SOURCE.replace(
        '@app.post("/resolve")\ndef resolve():\n    return {}\n',
        '@app.get("/resolve")\ndef resolve():\n    return {}\n',
    )
    _write_project_skeleton(tmp_path, service_source=wrong_method_source)
    _write_gate2_artifacts(tmp_path)
    _write_gate3_artifact(tmp_path)
    _write_gate5_artifact(tmp_path)
    _write_rollup(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["service_required_routes_present"] == "FAIL"


def test_missing_dependency_declaration_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["pydantic>=2.0"]\n'
    )
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["pyproject_declares_fastapi"] == "FAIL"
    assert by_name["pyproject_declares_pydantic"] == "PASS"


def test_gemini_api_key_absent_is_warn_not_fail(tmp_path, monkeypatch):
    monkeypatch.delenv(rv.GEMINI_API_KEY_ENV_VAR, raising=False)
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gemini_api_key_env_var_set"] == "WARN"
    # A missing real external secret never blocks service_ready or fully_deployable-eligibility.
    assert verdict.service_ready is True


def test_gemini_api_key_present_is_pass(tmp_path, monkeypatch):
    monkeypatch.setenv(rv.GEMINI_API_KEY_ENV_VAR, "test-key-not-real")
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gemini_api_key_env_var_set"] == "PASS"


def test_missing_test_file_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "tests" / "services" / "test_bp6_resolution_service.py").unlink()
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_files_present"] == "FAIL"


def test_run_tests_false_reports_pending_not_a_fabricated_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_suite_passes"] == "PENDING"


def test_to_dict_and_to_markdown_do_not_raise(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp6_deployment_readiness(root, run_tests=False)
    d = verdict.to_dict()
    assert d["bp_id"] == "bp6"
    md = verdict.to_markdown()
    assert "BP6 Deployment Readiness Verdict" in md


def test_resolve_project_root_env_override(tmp_path, monkeypatch):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker")
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    assert rv.resolve_project_root() == tmp_path


def test_resolve_project_root_env_override_wrong_path_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError):
        rv.resolve_project_root()
