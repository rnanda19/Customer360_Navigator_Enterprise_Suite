"""
src/deployment/bp8_readiness_verdict.py — Customer360 Navigator

BP8 (Executive/Product Analytics) readiness-verdict module. A pure read-only audit, same honesty
spirit as readiness_verdict.py, bp4_readiness_verdict.py, bp5_readiness_verdict.py, and
bp6_readiness_verdict.py: it inspects the REAL artifacts BP8's own gates already wrote to disk
(or does not find them, and says so honestly as PENDING/FAIL) and produces an itemized,
structured verdict - never a subjective "looks good", never a fabricated PASS.

STANDING SCOPE DECISION (explicit, user-confirmed): BP8 is "Packaging + CI/tests only, no
service." Unlike BP1-BP7's own readiness-verdict siblings, this module performs NO
service-importable / FastAPI-route check, because BP8 has no FastAPI service at all - no
src/services/bp8_* module, no src/services/docker/bp8_* Dockerfile, and none is being built here.
BP8's real, sole deliverable is a cross-BP Gold-layer aggregation and Power BI reporting layer
(configs/bp8_executive_product_analytics.yaml's own aggregation_scope_definition.naming_commitment:
"never a ninth modeling problem - no target, no classifier, no GenAI call"), written in Python to
powerbi/gold_tables/. This module's checks are scoped to exactly what is real for BP8 today:

  1. configs/bp8_executive_product_analytics.yaml exists, parses, and its real `status` field
     (as of this module's writing: "gate1_confirmed_gate2_confirmed_gate3_confirmed") is read to
     honestly report which of BP8's real Gates 1-3 are confirmed, and which of Gates 4-7 remain
     PENDING (never a fabricated PASS, never a FAIL for a gate that simply hasn't run yet by
     design - BP8 has only completed Gates 1-3 so far).
  2. notebooks/bp8_executive_product_analytics/artifacts/gate2_gold_table_manifest.json exists,
     parses, and carries the real top-level keys this project's own schema uses (read-verified
     2026-09-25 directly against the real on-device file: bp_id, bp_name, gate, generated_at_utc,
     upstream_bp_status, kpi_category_scope, gold_tables_written, corrections_vs_gate1,
     bp7_observed_not_yet_aggregated, scope_boundaries, bp6_deferred_reason).
  3. notebooks/bp8_executive_product_analytics/artifacts/gate3_decision_engine_kpi_manifest.json
     exists, parses, and carries its own real top-level keys (read-verified 2026-09-25:
     gold_tables_written, n_gold_tables_written, bp_id, bp_name, gate, generated_at_utc,
     source_bp, source_gate, genai_resolution_kpis_out_of_scope_reason,
     gate1_gate2_files_verified_untouched). Cross-checked against Gate 2's manifest: Gate 3 is
     documented as ADDITIVE ONLY (see bp8_gate3_decision_engine_kpi_builders.py's own module
     docstring) so no Gold-table filename may appear in both manifests, Gate 3's own
     n_gold_tables_written must match the real length of its gold_tables_written list, and Gate
     3's own gate1_gate2_files_verified_untouched flag must be true.
  4. Every real Gold Parquet filename named in either manifest's gold_tables_written list is
     confirmed present on disk under powerbi/gold_tables/ (11 real files as of this module's
     writing: 7 from Gate 2, 4 from Gate 3).
  5. Gate 7 (executive rollup) is honestly reported PENDING, never FAIL: BP8's real Gate 7 has
     not run yet, so no executive_rollup_manifest.json is expected to exist under BP8's own
     artifacts directory yet. If one is unexpectedly found, this module reports that as a WARN
     (an unexpected artifact, not an automatic FAIL) rather than silently ignoring or trusting it.
  6. No service-readiness check of any kind (see the scope decision above).
  7. The real runtime packages BP8's own two src/features/bp8_*.py modules import
     (grep-verified 2026-09-25: only `polars`, beyond the standard library's `json`/`pathlib`/
     `typing`) are declared in pyproject.toml's [project.dependencies] - a read-only check; this
     module never edits pyproject.toml even if something were found missing, it only reports.
  8. This BP's own new pytest test file(s) exist under tests/bp8_executive_product_analytics/,
     and (optionally, via --no-run-tests, matching every sibling module's existing CLI
     convention) can actually be run via a real pytest subprocess.
  9. Packaging + CI coverage - both READ-ONLY checks, confirming coverage already exists rather
     than adding any: pyproject.toml's [tool.setuptools.packages.find] uses `where = ["src"]`
     (flat auto-discovery that already covers src/features/bp8_*.py - no per-BP packaging block
     needed or added), and .github/workflows/ci.yml's `test` job already runs a generic
     `pytest tests/ -v` step (no BP8-specific CI edit needed - a new test file under tests/ is
     picked up automatically). There is deliberately no `docker-validate` CI entry for BP8 (no
     service, per the scope decision above) and this module does not check for one.

Usage (from the project root, after `pip install -e .`):
    python -m deployment.bp8_readiness_verdict
    python -m deployment.bp8_readiness_verdict --write-report
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

BP_ID = "bp8"
BP8_FOLDER = "bp8_executive_product_analytics"
BP8_CONFIG_FILE = "bp8_executive_product_analytics.yaml"
BP8_TEST_FILES = ("tests/bp8_executive_product_analytics/test_bp8_gold_tables.py",)

ARTIFACTS_RELATIVE_DIR = Path("notebooks") / BP8_FOLDER / "artifacts"
GATE2_MANIFEST_FILENAME = "gate2_gold_table_manifest.json"
GATE3_MANIFEST_FILENAME = "gate3_decision_engine_kpi_manifest.json"
GATE7_ROLLUP_FILENAME = "executive_rollup_manifest.json"
GOLD_TABLES_RELATIVE_DIR = Path("powerbi") / "gold_tables"

# Real top-level keys - read-verified 2026-09-25 directly against the real on-device
# gate2_gold_table_manifest.json.
REQUIRED_GATE2_MANIFEST_KEYS = (
    "bp_id",
    "bp_name",
    "gate",
    "generated_at_utc",
    "upstream_bp_status",
    "kpi_category_scope",
    "gold_tables_written",
    "corrections_vs_gate1",
    "bp7_observed_not_yet_aggregated",
    "scope_boundaries",
    "bp6_deferred_reason",
)

# Real top-level keys - read-verified 2026-09-25 directly against the real on-device
# gate3_decision_engine_kpi_manifest.json.
REQUIRED_GATE3_MANIFEST_KEYS = (
    "gold_tables_written",
    "n_gold_tables_written",
    "bp_id",
    "bp_name",
    "gate",
    "generated_at_utc",
    "source_bp",
    "source_gate",
    "genai_resolution_kpis_out_of_scope_reason",
    "gate1_gate2_files_verified_untouched",
)

# grep-verified (2026-09-25) against src/features/bp8_gold_table_builders.py and
# src/features/bp8_gate3_decision_engine_kpi_builders.py's own module-level import statements:
# both `import polars as pl`; the Gate 3 module's only other non-stdlib import is
# `from features.bp8_gold_table_builders import UNSPECIFIED_TIER_SENTINEL`, an internal
# same-project import, not an external runtime package. `json`/`pathlib`/`typing` are stdlib.
REQUIRED_RUNTIME_PACKAGES = ("polars",)

# BP8's real, current Gate1 status field, as of this module's writing:
# "gate1_confirmed_gate2_confirmed_gate3_confirmed" - Gates 4-7 have not run. This tuple drives
# the honest per-gate PENDING/PASS reporting below; it makes no assumption that any of these
# gates ever runs, and reports whatever the real status string actually says at run time.
STATUS_TRACKED_GATES = ("gate1", "gate2", "gate3", "gate4", "gate5", "gate6", "gate7")
CONFIRMED_BY_DESIGN_GATES = ("gate1", "gate2", "gate3")


class CheckStatus(str, Enum):
    PASS = "PASS"  # nosec B105 - a check-result enum value, not a credential
    FAIL = "FAIL"
    WARN = "WARN"
    PENDING = "PENDING"  # not yet applicable - an honest not-yet-run state, not a failure


@dataclasses.dataclass
class CheckResult:
    name: str
    status: str
    detail: str

    def __post_init__(self) -> None:
        if isinstance(self.status, CheckStatus):
            self.status = self.status.value


@dataclasses.dataclass
class BP8ReadinessVerdict:
    bp_id: str
    generated_at_utc: str
    checks: list
    artifact_ready: bool
    packaging_and_tests_ready: bool
    fully_ready_gates_1_to_3: bool

    def to_dict(self) -> dict:
        return {
            "bp_id": self.bp_id,
            "generated_at_utc": self.generated_at_utc,
            "checks": [dataclasses.asdict(c) for c in self.checks],
            "artifact_ready": self.artifact_ready,
            "packaging_and_tests_ready": self.packaging_and_tests_ready,
            "fully_ready_gates_1_to_3": self.fully_ready_gates_1_to_3,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# BP8 Readiness Verdict - {self.bp_id}",
            "",
            f"Generated: {self.generated_at_utc}",
            "",
            "Scope: Packaging + CI/tests only, no service (explicit, standing project decision) -",
            "this verdict never claims BP8 is 'deployable', only that its real Gate 1-3 Gold-layer",
            "deliverables, packaging, and test coverage are in place. Gates 4-7 are honestly",
            "reported PENDING below, never a fabricated PASS or an unearned FAIL.",
            "",
            f"- **Real Gate 1-3 Gold-layer artifacts ready**: {'YES' if self.artifact_ready else 'NO'}",
            f"- **Packaging + tests ready**: {'YES' if self.packaging_and_tests_ready else 'NO'}",
            f"- **Fully ready for Gates 1-3**: {'YES' if self.fully_ready_gates_1_to_3 else 'NO'}",
            "",
            "| Check | Status | Detail |",
            "|---|---|---|",
        ]
        for c in self.checks:
            detail = c.detail.replace("|", "\\|")
            lines.append(f"| {c.name} | {c.status} | {detail} |")
        lines.append("")
        return "\n".join(lines)


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every service/notebook/readiness module in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) - reimplemented here (not imported from
    readiness_verdict.py or any sibling module) for the same standalone reasoning every sibling
    module's own docstring gives: no readiness-verdict sibling module depends on another at
    runtime, so a concurrent edit to one never breaks another."""
    env_override = os.environ.get("C360_PROJECT_ROOT")
    if env_override:
        candidate = Path(env_override)
        if (candidate / marker_filename).exists():
            return candidate
        raise RuntimeError(
            f"C360_PROJECT_ROOT is set to {candidate} but {marker_filename} was not found there. "
            "Fix the environment variable rather than removing this check."
        )
    start = Path.cwd()
    current = start
    for _ in range(8):
        if (current / marker_filename).exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(
        f"Could not resolve PROJECT_ROOT: no {marker_filename} found by walking up from {start}. "
        "Set the C360_PROJECT_ROOT environment variable to the "
        "Customer360_Navigator_Enterprise_Suite folder before running this check."
    )


def _parse_pyproject_dependencies(pyproject_path: Path) -> list:
    """Intentionally not a general TOML parser - same documented reasoning as
    readiness_verdict.py's, bp4_readiness_verdict.py's, and bp5_readiness_verdict.py's own
    identically-named function."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def _requirement_declared(requirements: list, package: str) -> bool:
    package_lower = package.lower()
    return any(re.match(rf"^{re.escape(package_lower)}\s*[><=~!]", r.lower()) for r in requirements)


def _load_json(path: Path) -> tuple:
    """Returns (data_or_None, error_checkresult_or_None)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _check_config(project_root: Path) -> tuple:
    """Returns (checks, config_dict_or_None, status_string). A missing/unparseable config is a
    real, concrete FAIL - never silently skipped."""
    checks: list = []
    config_path = project_root / "configs" / BP8_CONFIG_FILE
    if not config_path.exists():
        checks.append(
            CheckResult(
                "bp8_config_exists",
                CheckStatus.FAIL,
                f"configs/{BP8_CONFIG_FILE} not found - no BP8 gates have run yet.",
            )
        )
        return checks, None, ""
    checks.append(CheckResult("bp8_config_exists", CheckStatus.PASS, f"Found at {config_path}."))

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        checks.append(CheckResult("bp8_config_parses", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}"))
        return checks, None, ""
    checks.append(CheckResult("bp8_config_parses", CheckStatus.PASS, "Parsed as valid YAML."))

    status = str(config.get("status") or "")
    if not status:
        checks.append(
            CheckResult(
                "bp8_status_field_present",
                CheckStatus.FAIL,
                "config has no non-empty top-level `status` field.",
            )
        )
        return checks, config, status
    checks.append(CheckResult("bp8_status_field_present", CheckStatus.PASS, f"status={status!r}."))

    status_lower = status.lower()
    confirmed_ok = all(f"{g}_confirmed" in status_lower for g in CONFIRMED_BY_DESIGN_GATES)
    checks.append(
        CheckResult(
            "bp8_gates_1_to_3_confirmed",
            CheckStatus.PASS if confirmed_ok else CheckStatus.FAIL,
            (
                f"Real status string {status!r} confirms {CONFIRMED_BY_DESIGN_GATES}."
                if confirmed_ok
                else f"Real status string {status!r} does NOT confirm all of "
                f"{CONFIRMED_BY_DESIGN_GATES} - BP8's own Gate 1-3 completion is not yet real."
            ),
        )
    )

    for gate in ("gate4", "gate5", "gate6", "gate7"):
        done = f"{gate}_confirmed" in status_lower or f"{gate}_complete" in status_lower
        checks.append(
            CheckResult(
                f"bp8_status_{gate}",
                CheckStatus.PASS if done else CheckStatus.PENDING,
                (
                    f"Real status string shows {gate} confirmed."
                    if done
                    else f"{gate.upper()} has not run for BP8 yet (by design, as of this "
                    "verdict) - honestly PENDING, not a fabricated PASS or an unearned FAIL."
                ),
            )
        )

    return checks, config, status


def _check_gate2_manifest(project_root: Path) -> tuple:
    """Returns (checks, manifest_dict_or_None, ready: bool)."""
    checks: list = []
    manifest_path = project_root / ARTIFACTS_RELATIVE_DIR / GATE2_MANIFEST_FILENAME
    if not manifest_path.exists():
        checks.append(
            CheckResult(
                "gate2_gold_table_manifest_exists",
                CheckStatus.FAIL,
                f"Expected at {manifest_path} - Gate 2 has not produced a real manifest.",
            )
        )
        return checks, None, False

    manifest, error = _load_json(manifest_path)
    if error is not None:
        checks.append(
            CheckResult(
                "gate2_gold_table_manifest_exists",
                CheckStatus.FAIL,
                f"Found at {manifest_path} but failed to parse as JSON: {error}",
            )
        )
        return checks, None, False
    checks.append(
        CheckResult("gate2_gold_table_manifest_exists", CheckStatus.PASS, f"Found at {manifest_path}.")
    )

    missing_keys = [k for k in REQUIRED_GATE2_MANIFEST_KEYS if k not in manifest]
    if missing_keys:
        checks.append(
            CheckResult(
                "gate2_gold_table_manifest_schema",
                CheckStatus.FAIL,
                f"Missing real required key(s): {missing_keys}.",
            )
        )
        return checks, manifest, False
    checks.append(
        CheckResult(
            "gate2_gold_table_manifest_schema",
            CheckStatus.PASS,
            f"All {len(REQUIRED_GATE2_MANIFEST_KEYS)} real required keys present.",
        )
    )
    return checks, manifest, True


def _check_gate3_manifest(project_root: Path, gate2_manifest: Optional[dict]) -> tuple:
    """Returns (checks, manifest_dict_or_None, ready: bool). Cross-checks against Gate 2's own
    manifest since Gate 3 is documented ADDITIVE ONLY (bp8_gate3_decision_engine_kpi_builders.py's
    own module docstring) - a real filename collision between the two would mean that guarantee
    has been broken, and must be a concrete FAIL here, never silently ignored."""
    checks: list = []
    manifest_path = project_root / ARTIFACTS_RELATIVE_DIR / GATE3_MANIFEST_FILENAME
    if not manifest_path.exists():
        checks.append(
            CheckResult(
                "gate3_decision_engine_kpi_manifest_exists",
                CheckStatus.FAIL,
                f"Expected at {manifest_path} - Gate 3 has not produced a real manifest.",
            )
        )
        return checks, None, False

    manifest, error = _load_json(manifest_path)
    if error is not None:
        checks.append(
            CheckResult(
                "gate3_decision_engine_kpi_manifest_exists",
                CheckStatus.FAIL,
                f"Found at {manifest_path} but failed to parse as JSON: {error}",
            )
        )
        return checks, None, False
    checks.append(
        CheckResult(
            "gate3_decision_engine_kpi_manifest_exists", CheckStatus.PASS, f"Found at {manifest_path}."
        )
    )

    missing_keys = [k for k in REQUIRED_GATE3_MANIFEST_KEYS if k not in manifest]
    if missing_keys:
        checks.append(
            CheckResult(
                "gate3_decision_engine_kpi_manifest_schema",
                CheckStatus.FAIL,
                f"Missing real required key(s): {missing_keys}.",
            )
        )
        return checks, manifest, False
    checks.append(
        CheckResult(
            "gate3_decision_engine_kpi_manifest_schema",
            CheckStatus.PASS,
            f"All {len(REQUIRED_GATE3_MANIFEST_KEYS)} real required keys present.",
        )
    )

    ready = True

    tables_written = manifest.get("gold_tables_written") or []
    declared_count = manifest.get("n_gold_tables_written")
    real_count = len(tables_written)
    if declared_count != real_count:
        checks.append(
            CheckResult(
                "gate3_n_gold_tables_written_matches_list",
                CheckStatus.FAIL,
                f"Manifest declares n_gold_tables_written={declared_count!r} but its own "
                f"gold_tables_written list has {real_count} real entries.",
            )
        )
        ready = False
    else:
        checks.append(
            CheckResult(
                "gate3_n_gold_tables_written_matches_list",
                CheckStatus.PASS,
                f"n_gold_tables_written ({declared_count}) matches the real list length.",
            )
        )

    verified_untouched = manifest.get("gate1_gate2_files_verified_untouched")
    if verified_untouched is not True:
        checks.append(
            CheckResult(
                "gate3_gate1_gate2_files_verified_untouched",
                CheckStatus.FAIL,
                f"Manifest's own gate1_gate2_files_verified_untouched={verified_untouched!r}, "
                "expected real value True - Gate 3's additive-only guarantee is not confirmed.",
            )
        )
        ready = False
    else:
        checks.append(
            CheckResult(
                "gate3_gate1_gate2_files_verified_untouched",
                CheckStatus.PASS,
                "Gate 3 itself confirms Gate 1/Gate 2 files were verified untouched.",
            )
        )

    if gate2_manifest is not None:
        gate2_filenames = {t.get("filename") for t in (gate2_manifest.get("gold_tables_written") or [])}
        gate3_filenames = {t.get("filename") for t in tables_written}
        collisions = gate2_filenames & gate3_filenames
        if collisions:
            checks.append(
                CheckResult(
                    "gate2_gate3_no_filename_collision",
                    CheckStatus.FAIL,
                    f"Gate 3 is documented ADDITIVE ONLY but these filename(s) appear in BOTH "
                    f"manifests: {sorted(collisions)} - a real overwrite-safety violation.",
                )
            )
            ready = False
        else:
            checks.append(
                CheckResult(
                    "gate2_gate3_no_filename_collision",
                    CheckStatus.PASS,
                    "No Gold-table filename is shared between Gate 2's and Gate 3's manifests, "
                    "consistent with Gate 3's documented additive-only guarantee.",
                )
            )

    return checks, manifest, ready


def _check_gold_parquet_files(
    project_root: Path, gate2_manifest: Optional[dict], gate3_manifest: Optional[dict]
) -> tuple:
    """Returns (checks, all_present: bool). Confirms every real filename either manifest names in
    its own gold_tables_written list actually exists on disk under powerbi/gold_tables/ - one
    check per file, never merged into a single check, so one missing file's FAIL never masks
    another file's real PASS."""
    checks: list = []
    all_present = True
    seen_filenames: set = set()

    for manifest, gate_label in ((gate2_manifest, "gate2"), (gate3_manifest, "gate3")):
        if manifest is None:
            continue
        for table in manifest.get("gold_tables_written") or []:
            filename = table.get("filename")
            if not filename or filename in seen_filenames:
                continue
            seen_filenames.add(filename)
            table_path = project_root / GOLD_TABLES_RELATIVE_DIR / filename
            if table_path.exists():
                checks.append(
                    CheckResult(
                        f"gold_parquet_exists[{filename}]",
                        CheckStatus.PASS,
                        f"Found at {table_path} (named by {gate_label}'s manifest).",
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        f"gold_parquet_exists[{filename}]",
                        CheckStatus.FAIL,
                        f"{gate_label}'s manifest names {filename} but no file exists at " f"{table_path}.",
                    )
                )
                all_present = False

    if not seen_filenames:
        checks.append(
            CheckResult(
                "gold_parquet_exists[any]",
                CheckStatus.FAIL,
                "No Gold-table filenames were found in either manifest to check.",
            )
        )
        all_present = False

    return checks, all_present


def _check_gate7_rollup_pending(project_root: Path) -> list:
    """Gate 7 has not run for BP8 - this is honestly PENDING, never FAIL. If a rollup manifest is
    unexpectedly found (e.g. a future run this module predates), that is reported as a WARN
    (worth a human's attention) rather than silently trusted or treated as an automatic FAIL."""
    rollup_path = project_root / ARTIFACTS_RELATIVE_DIR / GATE7_ROLLUP_FILENAME
    if not rollup_path.exists():
        return [
            CheckResult(
                "gate7_executive_rollup",
                CheckStatus.PENDING,
                "Gate 7 not yet run for BP8, no executive_rollup_manifest.json expected yet.",
            )
        ]
    return [
        CheckResult(
            "gate7_executive_rollup",
            CheckStatus.WARN,
            f"Found {rollup_path} even though Gate 7 was not expected to have run yet for BP8 - "
            "this module makes no PASS/FAIL claim about its contents, flagged for human review.",
        )
    ]


def _check_dependencies_declared(project_root: Path) -> list:
    checks = []
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        return [
            CheckResult(
                f"pyproject_declares_{package}",
                CheckStatus.FAIL,
                f"{pyproject_path} not found - cannot confirm real dependency declarations.",
            )
            for package in REQUIRED_RUNTIME_PACKAGES
        ]
    pyproject_deps = _parse_pyproject_dependencies(pyproject_path)
    for package in REQUIRED_RUNTIME_PACKAGES:
        declared = _requirement_declared(pyproject_deps, package)
        checks.append(
            CheckResult(
                f"pyproject_declares_{package}",
                CheckStatus.PASS if declared else CheckStatus.FAIL,
                f"{'Found' if declared else 'NOT found'} in pyproject.toml [project.dependencies] "
                "(grep-verified real import in src/features/bp8_gold_table_builders.py and "
                "src/features/bp8_gate3_decision_engine_kpi_builders.py). Read-only check - this "
                "module never edits pyproject.toml.",
            )
        )
    return checks


def _check_test_files_exist_and_pass(project_root: Path, run_tests: bool) -> list:
    checks = []
    missing = [t for t in BP8_TEST_FILES if not (project_root / t).exists()]
    if missing:
        checks.append(
            CheckResult("test_files_present", CheckStatus.FAIL, f"Missing test file(s): {missing}.")
        )
        return checks
    checks.append(CheckResult("test_files_present", CheckStatus.PASS, f"All of {BP8_TEST_FILES} present."))

    if not run_tests:
        checks.append(
            CheckResult(
                "test_suite_passes",
                CheckStatus.PENDING,
                "Skipped (run_tests=False) - test files exist but were not executed this run.",
            )
        )
        return checks

    try:
        result = subprocess.run(  # nosec B603 - fixed arg list from this module's own constants
            [sys.executable, "-m", "pytest", *BP8_TEST_FILES, "-q"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        checks.append(CheckResult("test_suite_passes", CheckStatus.WARN, f"Could not run pytest: {exc}"))
        return checks

    summary_line = next(
        (
            line
            for line in result.stdout.splitlines()[::-1]
            if "passed" in line or "failed" in line or "error" in line
        ),
        (result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "(no output)"),
    )
    if result.returncode == 0:
        checks.append(CheckResult("test_suite_passes", CheckStatus.PASS, summary_line))
    else:
        checks.append(
            CheckResult(
                "test_suite_passes",
                CheckStatus.FAIL,
                f"pytest exited {result.returncode}: {summary_line}",
            )
        )
    return checks


def _check_packaging_and_ci_coverage(project_root: Path) -> list:
    """Both checks are READ-ONLY: they confirm packaging/CI coverage for BP8 already exists via
    the project's generic, flat conventions - this module never edits pyproject.toml or
    .github/workflows/ci.yml, both of which are off-limits to this task."""
    checks = []

    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text(encoding="utf-8")
        has_flat_discovery = re.search(r'where\s*=\s*\[\s*"src"\s*\]', text) is not None
        checks.append(
            CheckResult(
                "pyproject_packages_find_covers_bp8",
                CheckStatus.PASS if has_flat_discovery else CheckStatus.FAIL,
                (
                    'pyproject.toml\'s [tool.setuptools.packages.find] uses where = ["src"] - '
                    "flat auto-discovery that already packages src/features/bp8_gold_table_"
                    "builders.py and src/features/bp8_gate3_decision_engine_kpi_builders.py with "
                    "no per-BP entry needed."
                    if has_flat_discovery
                    else 'No where = ["src"]-style flat auto-discovery found in pyproject.toml '
                    "- BP8's src/features/bp8_*.py modules may not be packaged."
                ),
            )
        )
    else:
        checks.append(
            CheckResult(
                "pyproject_packages_find_covers_bp8",
                CheckStatus.FAIL,
                f"{pyproject_path} not found.",
            )
        )

    ci_path = project_root / ".github" / "workflows" / "ci.yml"
    if ci_path.exists():
        ci_text = ci_path.read_text(encoding="utf-8")
        has_pytest_step = re.search(r"pytest\s+tests/", ci_text) is not None
        checks.append(
            CheckResult(
                "ci_pytest_tests_step_covers_bp8",
                CheckStatus.PASS if has_pytest_step else CheckStatus.FAIL,
                (
                    f"{ci_path}'s `test` job runs a generic `pytest tests/` step - this already "
                    "picks up BP8's new test file(s) with no CI edit needed."
                    if has_pytest_step
                    else f"No generic `pytest tests/` step found in {ci_path} - BP8's test "
                    "file(s) may never actually run in CI."
                ),
            )
        )
    else:
        checks.append(
            CheckResult(
                "ci_pytest_tests_step_covers_bp8",
                CheckStatus.FAIL,
                f"{ci_path} not found.",
            )
        )

    return checks


def assess_bp8_readiness(project_root: Optional[Path] = None, run_tests: bool = True) -> BP8ReadinessVerdict:
    if project_root is None:
        project_root = resolve_project_root()

    checks: list[CheckResult] = []

    config_checks, config, _status = _check_config(project_root)
    checks.extend(config_checks)
    config_ready = config is not None and all(
        c.status in (CheckStatus.PASS.value, CheckStatus.PENDING.value) for c in config_checks
    )

    gate2_checks, gate2_manifest, gate2_ready = _check_gate2_manifest(project_root)
    checks.extend(gate2_checks)

    gate3_checks, gate3_manifest, gate3_ready = _check_gate3_manifest(project_root, gate2_manifest)
    checks.extend(gate3_checks)

    gold_file_checks, gold_files_ready = _check_gold_parquet_files(
        project_root, gate2_manifest, gate3_manifest
    )
    checks.extend(gold_file_checks)

    checks.extend(_check_gate7_rollup_pending(project_root))

    artifact_ready = config_ready and gate2_ready and gate3_ready and gold_files_ready

    dependency_checks = _check_dependencies_declared(project_root)
    checks.extend(dependency_checks)

    test_checks = _check_test_files_exist_and_pass(project_root, run_tests)
    checks.extend(test_checks)

    packaging_ci_checks = _check_packaging_and_ci_coverage(project_root)
    checks.extend(packaging_ci_checks)

    packaging_and_tests_ready = (
        all(c.status == CheckStatus.PASS.value for c in dependency_checks)
        and all(c.status in (CheckStatus.PASS.value, CheckStatus.PENDING.value) for c in test_checks)
        and not any(c.status == CheckStatus.FAIL.value for c in test_checks)
        and all(c.status == CheckStatus.PASS.value for c in packaging_ci_checks)
    )

    fully_ready_gates_1_to_3 = artifact_ready and packaging_and_tests_ready

    return BP8ReadinessVerdict(
        bp_id=BP_ID,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        artifact_ready=artifact_ready,
        packaging_and_tests_ready=packaging_and_tests_ready,
        fully_ready_gates_1_to_3=fully_ready_gates_1_to_3,
    )


def _write_report(verdict: BP8ReadinessVerdict, project_root: Path) -> tuple:
    out_dir = project_root / "reports" / BP8_FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bp8_readiness_verdict.json"
    md_path = out_dir / "bp8_readiness_verdict.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verdict.to_dict(), f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(verdict.to_markdown())
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer360 Navigator BP8 readiness verdict.")
    parser.add_argument("--no-run-tests", action="store_true", help="Skip executing the pytest suite.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON+MD under reports/bp8_.../")
    args = parser.parse_args()

    project_root = resolve_project_root()
    verdict = assess_bp8_readiness(project_root, run_tests=not args.no_run_tests)
    print(verdict.to_markdown())
    if args.write_report:
        json_path, md_path = _write_report(verdict, project_root)
        print(f"[SAVED] {json_path}")
        print(f"[SAVED] {md_path}")
    return 0 if verdict.fully_ready_gates_1_to_3 else 1


if __name__ == "__main__":
    sys.exit(main())
