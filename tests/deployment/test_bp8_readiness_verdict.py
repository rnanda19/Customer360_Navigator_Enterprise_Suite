"""
tests/deployment/test_bp8_readiness_verdict.py — Customer360 Navigator

Synthetic-fixture tests for src/deployment/bp8_readiness_verdict.py. Mirrors
tests/deployment/test_bp5_readiness_verdict.py's own structure: a tmp_path project root is built
fresh per test with exactly the real files each check needs, never touching the real device
project. Covers the happy path plus every documented FAIL/PENDING/WARN branch, including BP8's
own real "no service" scope decision and its real Gates 4-7-pending reporting.
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

from deployment import bp8_readiness_verdict as rv  # noqa: E402

REAL_STATUS = "gate1_confirmed_gate2_confirmed_gate3_confirmed"

MINIMAL_PYPROJECT = """
[project]
name = "customer360-navigator-enterprise-suite"
version = "0.1.0"
dependencies = [
    "polars>=1.9",
]

[tool.setuptools.packages.find]
where = ["src"]
"""

MINIMAL_CI_YML = """
name: CI
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v
"""

GATE2_MANIFEST = {
    "bp_id": "bp8",
    "bp_name": "bp8_executive_product_analytics",
    "gate": 2,
    "generated_at_utc": "2026-09-25T09:38:15.512377+00:00",
    "upstream_bp_status": {},
    "kpi_category_scope": {},
    "gold_tables_written": [
        {"category": "friction_trends", "filename": "bp8_gold_friction_trends.parquet", "n_rows": 700},
        {"category": "escalation_trends", "filename": "bp8_gold_escalation_trends.parquet", "n_rows": 521},
    ],
    "corrections_vs_gate1": [],
    "bp7_observed_not_yet_aggregated": {},
    "scope_boundaries": [],
    "bp6_deferred_reason": "deferred",
}

GATE3_MANIFEST = {
    "gold_tables_written": [
        {
            "category": "decision_engine_kpis__summary",
            "filename": "bp8_gold_decision_engine_summary.parquet",
            "n_rows": 1,
        },
    ],
    "n_gold_tables_written": 1,
    "bp_id": "bp8",
    "bp_name": "bp8_executive_product_analytics",
    "gate": 3,
    "generated_at_utc": "2026-09-25T09:38:29.044184+00:00",
    "source_bp": "bp7",
    "source_gate": 5,
    "genai_resolution_kpis_out_of_scope_reason": "n=1, no trend to aggregate.",
    "gate1_gate2_files_verified_untouched": True,
}


def _write_project_skeleton(project_root: Path, status: str = REAL_STATUS) -> None:
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
    ci_dir = project_root / ".github" / "workflows"
    ci_dir.mkdir(parents=True, exist_ok=True)
    (ci_dir / "ci.yml").write_text(MINIMAL_CI_YML, encoding="utf-8")

    (project_root / "configs").mkdir(exist_ok=True)
    (project_root / "configs" / rv.BP8_CONFIG_FILE).write_text(
        yaml.safe_dump({"bp_id": "bp8", "bp_name": "bp8_executive_product_analytics", "status": status}),
        encoding="utf-8",
    )

    tests_dir = project_root / "tests" / "bp8_executive_product_analytics"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_bp8_gold_tables.py").write_text("def test_placeholder():\n    assert True\n")


def _write_manifests(project_root: Path, gate2: dict = None, gate3: dict = None) -> None:
    artifacts_dir = project_root / rv.ARTIFACTS_RELATIVE_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    if gate2 is not None:
        (artifacts_dir / rv.GATE2_MANIFEST_FILENAME).write_text(json.dumps(gate2), encoding="utf-8")
    if gate3 is not None:
        (artifacts_dir / rv.GATE3_MANIFEST_FILENAME).write_text(json.dumps(gate3), encoding="utf-8")


def _write_gold_tables(project_root: Path, filenames) -> None:
    gold_dir = project_root / rv.GOLD_TABLES_RELATIVE_DIR
    gold_dir.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        (gold_dir / filename).write_bytes(b"synthetic-tiny-parquet-stand-in")


def _all_real_filenames() -> list:
    names = [t["filename"] for t in GATE2_MANIFEST["gold_tables_written"]]
    names += [t["filename"] for t in GATE3_MANIFEST["gold_tables_written"]]
    return names


def _happy_path_root(tmp_path: Path) -> Path:
    _write_project_skeleton(tmp_path)
    _write_manifests(tmp_path, GATE2_MANIFEST, GATE3_MANIFEST)
    _write_gold_tables(tmp_path, _all_real_filenames())
    return tmp_path


# ---------------------------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------------------------


def test_happy_path_fully_ready(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    assert verdict.artifact_ready is True
    assert verdict.packaging_and_tests_ready is True
    assert verdict.fully_ready_gates_1_to_3 is True
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["bp8_gates_1_to_3_confirmed"] == "PASS"
    assert by_name["gate2_gold_table_manifest_schema"] == "PASS"
    assert by_name["gate3_decision_engine_kpi_manifest_schema"] == "PASS"
    assert by_name["gate2_gate3_no_filename_collision"] == "PASS"
    assert by_name["pyproject_declares_polars"] == "PASS"
    assert by_name["pyproject_packages_find_covers_bp8"] == "PASS"
    assert by_name["ci_pytest_tests_step_covers_bp8"] == "PASS"


def test_gates_4_to_7_are_honestly_pending_not_pass_or_fail(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    for gate in ("gate4", "gate5", "gate6", "gate7"):
        assert by_name[f"bp8_status_{gate}"] == "PENDING"
    assert by_name["gate7_executive_rollup"] == "PENDING"
    assert "Gate 7 not yet run" in next(
        c.detail for c in verdict.checks if c.name == "gate7_executive_rollup"
    )


def test_a_gate4_confirmed_status_is_honestly_reported_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "configs" / rv.BP8_CONFIG_FILE).write_text(
        yaml.safe_dump({"status": REAL_STATUS + "_gate4_confirmed"}), encoding="utf-8"
    )
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["bp8_status_gate4"] == "PASS"
    assert by_name["bp8_status_gate5"] == "PENDING"


# ---------------------------------------------------------------------------------------------
# Config checks
# ---------------------------------------------------------------------------------------------


def test_missing_config_is_a_clean_fail_not_a_crash(tmp_path):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker")
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    assert verdict.artifact_ready is False
    assert verdict.fully_ready_gates_1_to_3 is False
    assert verdict.checks[0].status == "FAIL"
    assert verdict.checks[0].name == "bp8_config_exists"


def test_gates_1_to_3_not_all_confirmed_fails_that_check(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "configs" / rv.BP8_CONFIG_FILE).write_text(
        yaml.safe_dump({"status": "gate1_confirmed_gate2_confirmed"}), encoding="utf-8"
    )
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["bp8_gates_1_to_3_confirmed"] == "FAIL"
    assert verdict.artifact_ready is False


def test_empty_status_field_fails_cleanly(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "configs" / rv.BP8_CONFIG_FILE).write_text(yaml.safe_dump({"status": ""}), encoding="utf-8")
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["bp8_status_field_present"] == "FAIL"


def test_unparseable_config_yaml_fails_cleanly(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "configs" / rv.BP8_CONFIG_FILE).write_text("bp_id: [unterminated", encoding="utf-8")
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["bp8_config_parses"] == "FAIL"


# ---------------------------------------------------------------------------------------------
# Gate 2 / Gate 3 manifest checks
# ---------------------------------------------------------------------------------------------


def test_missing_gate2_manifest_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_manifests(tmp_path, gate2=None, gate3=GATE3_MANIFEST)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate2_gold_table_manifest_exists"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate2_manifest_missing_required_key_fails_schema_check(tmp_path):
    _write_project_skeleton(tmp_path)
    incomplete = dict(GATE2_MANIFEST)
    del incomplete["scope_boundaries"]
    _write_manifests(tmp_path, gate2=incomplete, gate3=GATE3_MANIFEST)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate2_gold_table_manifest_schema"] == "FAIL"
    assert "scope_boundaries" in next(
        c.detail for c in verdict.checks if c.name == "gate2_gold_table_manifest_schema"
    )


def test_missing_gate3_manifest_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    _write_manifests(tmp_path, gate2=GATE2_MANIFEST, gate3=None)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate3_decision_engine_kpi_manifest_exists"] == "FAIL"
    assert verdict.artifact_ready is False


def test_gate3_manifest_missing_required_key_fails_schema_check(tmp_path):
    _write_project_skeleton(tmp_path)
    incomplete = dict(GATE3_MANIFEST)
    del incomplete["source_bp"]
    _write_manifests(tmp_path, gate2=GATE2_MANIFEST, gate3=incomplete)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate3_decision_engine_kpi_manifest_schema"] == "FAIL"


def test_gate3_n_gold_tables_written_mismatch_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    bad_gate3 = {**GATE3_MANIFEST, "n_gold_tables_written": 99}
    _write_manifests(tmp_path, gate2=GATE2_MANIFEST, gate3=bad_gate3)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate3_n_gold_tables_written_matches_list"] == "FAIL"


def test_gate3_verified_untouched_flag_not_true_fails(tmp_path):
    _write_project_skeleton(tmp_path)
    bad_gate3 = {**GATE3_MANIFEST, "gate1_gate2_files_verified_untouched": False}
    _write_manifests(tmp_path, gate2=GATE2_MANIFEST, gate3=bad_gate3)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate3_gate1_gate2_files_verified_untouched"] == "FAIL"


def test_filename_collision_between_gate2_and_gate3_fails_additive_only_guarantee(tmp_path):
    _write_project_skeleton(tmp_path)
    colliding_gate3 = dict(GATE3_MANIFEST)
    colliding_gate3["gold_tables_written"] = [
        {"category": "x", "filename": "bp8_gold_friction_trends.parquet", "n_rows": 1}
    ]
    colliding_gate3["n_gold_tables_written"] = 1
    _write_manifests(tmp_path, gate2=GATE2_MANIFEST, gate3=colliding_gate3)
    verdict = rv.assess_bp8_readiness(tmp_path, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate2_gate3_no_filename_collision"] == "FAIL"
    assert verdict.artifact_ready is False


# ---------------------------------------------------------------------------------------------
# Gold parquet file existence
# ---------------------------------------------------------------------------------------------


def test_missing_one_gold_parquet_file_fails_only_that_file(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / rv.GOLD_TABLES_RELATIVE_DIR / "bp8_gold_friction_trends.parquet").unlink()
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gold_parquet_exists[bp8_gold_friction_trends.parquet]"] == "FAIL"
    assert by_name["gold_parquet_exists[bp8_gold_escalation_trends.parquet]"] == "PASS"
    assert verdict.artifact_ready is False


def test_all_real_gold_tables_present_pass_individually(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    for filename in _all_real_filenames():
        assert by_name[f"gold_parquet_exists[{filename}]"] == "PASS"


# ---------------------------------------------------------------------------------------------
# Gate 7 rollup (PENDING by design; WARN if unexpectedly present)
# ---------------------------------------------------------------------------------------------


def test_unexpected_gate7_rollup_is_a_warn_not_a_fail_or_silent_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / rv.ARTIFACTS_RELATIVE_DIR / rv.GATE7_ROLLUP_FILENAME).write_text("{}", encoding="utf-8")
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["gate7_executive_rollup"] == "WARN"


# ---------------------------------------------------------------------------------------------
# Dependencies / packaging / CI (all read-only checks)
# ---------------------------------------------------------------------------------------------


def test_missing_polars_dependency_declaration_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = []\n'
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n'
    )
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["pyproject_declares_polars"] == "FAIL"
    assert verdict.packaging_and_tests_ready is False


def test_missing_flat_packaging_discovery_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = ["polars>=1.9"]\n'
    )
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["pyproject_packages_find_covers_bp8"] == "FAIL"


def test_missing_ci_pytest_step_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\njobs:\n  lint:\n    steps: []\n")
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["ci_pytest_tests_step_covers_bp8"] == "FAIL"


def test_missing_ci_file_entirely_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / ".github" / "workflows" / "ci.yml").unlink()
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["ci_pytest_tests_step_covers_bp8"] == "FAIL"


# ---------------------------------------------------------------------------------------------
# Test-file presence / run
# ---------------------------------------------------------------------------------------------


def test_missing_test_file_fails(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "tests" / "bp8_executive_product_analytics" / "test_bp8_gold_tables.py").unlink()
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_files_present"] == "FAIL"
    assert verdict.packaging_and_tests_ready is False


def test_run_tests_false_reports_pending_not_a_fabricated_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_suite_passes"] == "PENDING"


def test_run_tests_true_actually_executes_pytest_and_passes(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=True)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_suite_passes"] == "PASS"


def test_run_tests_true_reports_real_failure_not_fabricated_pass(tmp_path):
    root = _happy_path_root(tmp_path)
    (root / "tests" / "bp8_executive_product_analytics" / "test_bp8_gold_tables.py").write_text(
        "def test_deliberately_fails():\n    assert False\n"
    )
    verdict = rv.assess_bp8_readiness(root, run_tests=True)
    by_name = {c.name: c.status for c in verdict.checks}
    assert by_name["test_suite_passes"] == "FAIL"
    assert verdict.packaging_and_tests_ready is False


# ---------------------------------------------------------------------------------------------
# No service-readiness check at all (explicit scope decision)
# ---------------------------------------------------------------------------------------------


def test_no_service_related_check_names_exist_anywhere_in_the_verdict(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    names = [c.name for c in verdict.checks]
    assert not any("service" in n.lower() for n in names)
    assert not any("docker" in n.lower() for n in names)
    assert not any("route" in n.lower() for n in names)


# ---------------------------------------------------------------------------------------------
# to_dict / to_markdown / resolve_project_root
# ---------------------------------------------------------------------------------------------


def test_to_dict_and_to_markdown_do_not_raise(tmp_path):
    root = _happy_path_root(tmp_path)
    verdict = rv.assess_bp8_readiness(root, run_tests=False)
    d = verdict.to_dict()
    assert d["bp_id"] == "bp8"
    assert d["fully_ready_gates_1_to_3"] is True
    md = verdict.to_markdown()
    assert "BP8 Readiness Verdict" in md
    assert "no service" in md.lower()


def test_resolve_project_root_env_override(tmp_path, monkeypatch):
    (tmp_path / "PROJECT_STRUCTURE_LOCKED.md").write_text("marker")
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    assert rv.resolve_project_root() == tmp_path


def test_resolve_project_root_env_override_wrong_path_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError):
        rv.resolve_project_root()


def test_main_cli_no_run_tests_exits_zero_on_happy_path(tmp_path, monkeypatch, capsys):
    root = _happy_path_root(tmp_path)
    monkeypatch.setenv("C360_PROJECT_ROOT", str(root))
    monkeypatch.setattr(sys, "argv", ["bp8_readiness_verdict.py", "--no-run-tests"])
    exit_code = rv.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "BP8 Readiness Verdict" in captured.out
