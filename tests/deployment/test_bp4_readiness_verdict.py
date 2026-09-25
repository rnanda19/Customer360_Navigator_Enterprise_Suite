"""
tests/deployment/test_bp4_readiness_verdict.py — Customer360 Navigator

Tests for src/deployment/bp4_readiness_verdict.py (Hardening Step 4, BP4 variant). Builds a small,
complete SYNTHETIC project tree per test (config YAML, a real, schema-correct Parquet decision-
artifact index written via polars, pyproject.toml, and an importable dummy bp4_decision_service
module) so the module's checks can be exercised against every real code path - happy path, honest
PENDING states, and tampered/drifted FAIL states - without touching any real BP4 data or the real
device project. Mirrors tests/deployment/test_readiness_verdict.py's own established synthetic-
fixture test style (see that file's own docstring), adapted for BP4's decision-artifact shape
instead of a joblib model bundle.
"""

from __future__ import annotations

import hashlib
import sys

import polars as pl
import pytest

from deployment.bp4_readiness_verdict import (
    CLUSTER_KEY,
    CheckStatus,
    _resolve_config_relative_path,
    assess_bp4_deployment_readiness,
)


def _build_project_tree(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "configs").mkdir(parents=True)
    (project_root / "models" / "bp4_customer_journey_analytics").mkdir(parents=True)
    (project_root / "src" / "services").mkdir(parents=True)
    (project_root / "tests" / "services").mkdir(parents=True)
    (project_root / "PROJECT_STRUCTURE_LOCKED.md").write_text("locked\n", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(
        'dependencies = [\n    "polars>=1.9",\n    "fastapi>=0.115",\n    "pydantic>=2.0",\n]\n',
        encoding="utf-8",
    )
    return project_root


def _parquet_path(project_root):
    return project_root / "models" / "bp4_customer_journey_analytics" / "bp4_decision_artifact_index.parquet"


def _build_synthetic_parquet(path):
    """Tiny, real, schema-correct Parquet index - same CLUSTER_KEY columns as the real Hardening
    Step 2 notebook produces (plus a couple of representative non-key columns), written via
    polars exactly like the real notebook does (indexed_frame.write_parquet(...))."""
    frame = pl.DataFrame(
        {
            "Company": ["Acme Bank", "Beta Bank"],
            "Product": ["Checking or savings account", "Mortgage"],
            "Sub-product": ["Checking account", "Conventional home mortgage"],
            "Issue": ["Problem with a lender", "Struggling to pay"],
            "Sub-issue": ["MISSING_SUB_ISSUE", "MISSING_SUB_ISSUE"],
            "n_complaints_total": [12, 5],
            "review_priority_tier": ["HIGH", "LOW"],
        }
    ).sort(CLUSTER_KEY)
    frame.write_parquet(path)
    with open(path, "rb") as f:
        real_sha256 = hashlib.sha256(f.read()).hexdigest()
    return frame, real_sha256


def _write_config(
    project_root,
    *,
    include_persistence_block,
    parquet_relative_path="models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet",
    sha256_override=None,
    n_rows=2,
    n_columns=7,
):
    lines = [
        'bp_id: "bp4"',
        'bp_name: "bp4_customer_journey_analytics"',
    ]
    if include_persistence_block:
        lines += [
            "decision_artifact_persistence:",
            f'  parquet_relative_path: "{parquet_relative_path}"',
            f'  parquet_sha256: "{sha256_override}"',
            f"  n_rows: {n_rows}",
            f"  n_columns: {n_columns}",
            f"  sort_key: {CLUSTER_KEY}",
            "  idempotent_rewrite_verified: true",
            "  round_trip_verified: true",
            '  generated_at_utc: "2026-09-24T00:00:00+00:00"',
        ]
    (project_root / "configs" / "bp4_customer_journey_analytics.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_working_service_module(project_root):
    """A minimal-but-real FastAPI app with the four required read-only routes - not a mock of the
    real bp4_decision_service.py, but real enough to exercise the import/route-detection checks."""
    (project_root / "src" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (project_root / "src" / "services" / "bp4_decision_service.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/')\n"
        "def root(): return {}\n"
        "@app.get('/health')\n"
        "def health(): return {}\n"
        "@app.get('/cluster/lookup')\n"
        "def lookup(): return {}\n"
        "@app.get('/clusters')\n"
        "def clusters(): return {}\n",
        encoding="utf-8",
    )


@pytest.fixture()
def synthetic_project(tmp_path, monkeypatch):
    project_root = _build_project_tree(tmp_path)
    monkeypatch.syspath_prepend(str(project_root / "src"))
    yield project_root
    for mod in ("services.bp4_decision_service", "services"):
        sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fully_healthy_bp4_is_artifact_and_service_ready(synthetic_project):
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "tests" / "services" / "test_bp4_decision_service.py").write_text(
        "", encoding="utf-8"
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)

    assert verdict.artifact_ready is True
    assert verdict.service_ready is True
    assert verdict.fully_deployable is False  # Docker/CI (Steps 5/6) correctly not yet present
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["parquet_integrity_sha256"] == CheckStatus.PASS.value
    assert statuses["parquet_loads_and_schema_sane"] == CheckStatus.PASS.value
    assert statuses["dockerfile_present"] == CheckStatus.PENDING.value
    assert statuses["ci_workflow_present"] == CheckStatus.PENDING.value


# ---------------------------------------------------------------------------
# Honest PENDING states - nothing fabricated when a step hasn't run yet
# ---------------------------------------------------------------------------


def test_no_config_at_all_reports_fail_not_a_crash(synthetic_project):
    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    assert verdict.artifact_ready is False
    assert verdict.service_ready is False
    assert verdict.checks[0].name == "bp4_config_exists"
    assert verdict.checks[0].status == CheckStatus.FAIL.value


def test_config_exists_but_no_persistence_block_is_pending_not_fail(synthetic_project):
    """Hardening Step 2 (decision-artifact persistence) simply hasn't been run for real yet - this
    must read as PENDING, the honest current real state of the actual BP4 project today, never a
    fabricated PASS or an alarming FAIL."""
    _write_config(synthetic_project, include_persistence_block=False)
    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    assert verdict.artifact_ready is False
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["decision_artifact_persistence_config_block"] == CheckStatus.PENDING.value


def test_run_tests_false_marks_test_suite_passes_pending(synthetic_project):
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "tests" / "services" / "test_bp4_decision_service.py").write_text(
        "", encoding="utf-8"
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["test_suite_passes"] == CheckStatus.PENDING.value


# ---------------------------------------------------------------------------
# Real drift/tamper detection - FAIL, never silently accepted (at least 2 deliberate FAIL cases)
# ---------------------------------------------------------------------------


def test_tampered_parquet_fails_integrity_check(synthetic_project):
    """FAIL case 1: the persisted Parquet artifact on disk no longer matches the sha256 the
    persistence notebook recorded in the config - a real, detectable tamper/corruption case."""
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    # Tamper: append a byte to the real persisted file after the config recorded its real hash.
    with open(parquet_path, "ab") as f:
        f.write(b"\x00")

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["parquet_integrity_sha256"] == CheckStatus.FAIL.value
    assert verdict.artifact_ready is False


def test_missing_parquet_file_fails_not_pending(synthetic_project):
    """FAIL case 2: config claims a Parquet artifact was persisted, but the file isn't there on
    disk - config/disk have drifted (deleted after the notebook ran, or a bad manual edit). This
    is a real FAIL, distinct from the honest PENDING case where the notebook simply never ran."""
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override="0" * 64,
        n_rows=2,
        n_columns=7,
    )
    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["parquet_exists_on_disk"] == CheckStatus.FAIL.value
    assert verdict.artifact_ready is False


def test_row_count_drift_fails_schema_sane_check(synthetic_project):
    """FAIL case 3 (bonus, beyond the required 2): the config's recorded n_rows no longer matches
    the real row count in the Parquet file on disk - a real, detectable drift distinct from a
    sha256 mismatch (covers the case where the hash check would pass on a legitimately re-written
    but differently-sized file, if a recorded hash were stale)."""
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=999999,  # deliberately wrong - real file has frame.height rows
        n_columns=len(frame.columns),
    )
    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["parquet_loads_and_schema_sane"] == CheckStatus.FAIL.value
    assert verdict.artifact_ready is False


def test_broken_service_module_fails_import_check(synthetic_project):
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    (synthetic_project / "src" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (synthetic_project / "src" / "services" / "bp4_decision_service.py").write_text(
        "raise RuntimeError('deliberately broken for this test')\n", encoding="utf-8"
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["service_module_imports_cleanly"] == CheckStatus.FAIL.value
    assert verdict.service_ready is False


def test_service_missing_required_route_fails(synthetic_project):
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    (synthetic_project / "src" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (synthetic_project / "src" / "services" / "bp4_decision_service.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/')\n"
        "def root(): return {}\n"
        "@app.get('/health')\n"
        "def health(): return {}\n",  # missing /cluster/lookup and /clusters
        encoding="utf-8",
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["service_required_routes_present"] == CheckStatus.FAIL.value
    assert verdict.service_ready is False


def test_missing_pyproject_dependency_declaration_fails(synthetic_project):
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "pyproject.toml").write_text(
        'dependencies = [\n    "fastapi>=0.115",\n    "pydantic>=2.0",\n]\n',  # polars removed
        encoding="utf-8",
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["pyproject_declares_polars"] == CheckStatus.FAIL.value
    assert verdict.service_ready is False


# ---------------------------------------------------------------------------
# Real subprocess test-suite execution (not mocked)
# ---------------------------------------------------------------------------


def test_run_tests_true_actually_executes_pytest_subprocess(synthetic_project):
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    _write_config(
        synthetic_project,
        include_persistence_block=True,
        sha256_override=real_sha256,
        n_rows=frame.height,
        n_columns=len(frame.columns),
    )
    _write_working_service_module(synthetic_project)
    (synthetic_project / "tests" / "services" / "test_bp4_decision_service.py").write_text(
        "def test_trivial_fail():\n    assert False, 'deliberate failure for this test'\n",
        encoding="utf-8",
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=True)
    statuses = {c.name: (c.status, c.detail) for c in verdict.checks}
    status, detail = statuses["test_suite_passes"]
    assert status == CheckStatus.FAIL.value  # the deliberate failure above must be caught, not hidden
    assert "pytest exited" in detail
    assert verdict.service_ready is False


# ---------------------------------------------------------------------------
# _resolve_config_relative_path - the real, load-bearing BP4 finding (see module docstring): the
# persistence notebook's Section 11 writes parquet_relative_path via a raw f-string on a Path
# object (never `.as_posix()`), so the real value on the actual Windows device will hit the exact
# same double-quoted-YAML backslash-escape corruption already documented for BP1-3's
# joblib_relative_path in readiness_verdict.py - both real path segments here start with "b"
# ("...s\bp4_customer_journey_analytics\bp4_decision..."), producing two real backspace (0x08)
# control characters at YAML-parse time, not two literal backslash-b sequences.
# ---------------------------------------------------------------------------


def test_resolve_config_relative_path_handles_clean_forward_slash_path(tmp_path):
    target = tmp_path / "models" / "bp4_customer_journey_analytics" / "bp4_decision_artifact_index.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake")
    resolved = _resolve_config_relative_path(
        tmp_path, "models/bp4_customer_journey_analytics/bp4_decision_artifact_index.parquet"
    )
    assert resolved == target
    assert resolved.exists()


def test_resolve_config_relative_path_reverses_real_yaml_escape_corruption(tmp_path):
    """Reproduces the exact real corruption BP4's own persistence notebook will produce on the
    real Windows device if run as-is: a double-quoted YAML scalar containing `\\b` (backslash + the
    letter b, TWICE - once per "bp4_..." segment) gets parsed by yaml.safe_load into two real
    backspace control characters (0x08), not four literal characters - this is what
    _resolve_config_relative_path actually receives as input in that real scenario."""
    import yaml

    target = tmp_path / "models" / "bp4_customer_journey_analytics" / "bp4_decision_artifact_index.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"fake")
    yaml_corrupted_value = yaml.safe_load(
        '"models\\bp4_customer_journey_analytics\\bp4_decision_artifact_index.parquet"'
    )
    assert yaml_corrupted_value.count("\x08") == 2  # sanity: reproduces the real double corruption
    resolved = _resolve_config_relative_path(tmp_path, yaml_corrupted_value)
    assert resolved == target
    assert resolved.exists()


def test_bp4_readiness_check_resolves_real_corrupted_parquet_path(synthetic_project):
    """End-to-end: a full assess_bp4_deployment_readiness() pass against a config file written the
    exact real way the current (unmodified) persistence notebook writes it - a raw Windows-style
    backslash path embedded directly in a double-quoted YAML scalar - must still find the real
    artifact. The ON-DISK text below is the literal two-characters-twice backslash+"b" (matching
    what the notebook's f-string over PARQUET_PATH.relative_to(PROJECT_ROOT) actually writes on
    Windows); it is yaml.safe_load() itself, inside assess_bp4_deployment_readiness(), that turns
    those into the real corrupted control characters at parse time."""
    parquet_path = _parquet_path(synthetic_project)
    frame, real_sha256 = _build_synthetic_parquet(parquet_path)
    raw_windows_style_path = "models\\bp4_customer_journey_analytics\\bp4_decision_artifact_index.parquet"
    lines = [
        'bp_id: "bp4"',
        "decision_artifact_persistence:",
        f'  parquet_relative_path: "{raw_windows_style_path}"',
        f'  parquet_sha256: "{real_sha256}"',
        f"  n_rows: {frame.height}",
        f"  n_columns: {len(frame.columns)}",
        '  generated_at_utc: "2026-09-24T00:00:00+00:00"',
    ]
    (synthetic_project / "configs" / "bp4_customer_journey_analytics.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    verdict = assess_bp4_deployment_readiness(synthetic_project, run_tests=False)
    statuses = {c.name: c.status for c in verdict.checks}
    assert statuses["parquet_exists_on_disk"] == CheckStatus.PASS.value
    assert statuses["parquet_integrity_sha256"] == CheckStatus.PASS.value


def test_cluster_key_constant_matches_real_service_key():
    assert CLUSTER_KEY == ["Company", "Product", "Sub-product", "Issue", "Sub-issue"]
