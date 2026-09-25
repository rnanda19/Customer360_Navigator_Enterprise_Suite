"""
src/deployment/bp4_readiness_verdict.py — Customer360 Navigator

BP4 (Customer Journey Analytics) deployment-readiness verdict module (Hardening Step 4, BP4
variant). A pure read-only audit, same honesty spirit as src/deployment/readiness_verdict.py: it
inspects the REAL artifacts earlier BP4 hardening steps already wrote to disk (or does not find
them, and says so honestly as PENDING) and produces an itemized, structured verdict - never a
subjective "looks good", never a fabricated PASS.

Deliberately a SEPARATE module from readiness_verdict.py, not an extension of it. BP4 fits no
supervised model (an explicit standing user decision - see
notebooks/bp4_customer_journey_analytics/bp4_customer_journey_analytics_decision_artifact_persistence.ipynb's
own module docstring): there is no joblib bundle, no REQUIRED_KEYS model-bundle contract, no
champion accuracy/PR-AUC to drift-check. readiness_verdict.py's SUPPORTED_BPS registry and
_check_model_persistence_block() are built entirely around that joblib-bundle shape; forcing BP4
into it would mean either fabricating a fake "model" concept BP4 does not have, or silently
special-casing BP4 inside a shared module a concurrent session may be editing this same turn for
BP1/2/3's own work. Neither is acceptable, so this module is a standalone sibling instead -
mirroring bp4_decision_service.py's own explicit "deliberately standalone, not import
service_common.py" design choice (see that file's module docstring) for exactly the same reason.

What this module actually checks, against BP4's real, different artifact shape:
  1. configs/bp4_customer_journey_analytics.yaml exists.
  2. The `decision_artifact_persistence` config block (written by the Hardening Step 2 notebook's
     own Section 11, via write_gate_block()) exists - PENDING, not FAIL, if the notebook has not
     been run for real yet.
  3. The persisted Parquet index (models/bp4_customer_journey_analytics/
     bp4_decision_artifact_index.parquet) exists on disk where the config says it should.
  4. Its real sha256 matches what the config recorded (drift/tamper detection - same spirit as
     readiness_verdict.py's joblib_bundle_integrity_sha256 check, adapted for a Parquet artifact
     instead of a joblib bundle).
  5. The Parquet loads cleanly via polars, its real CLUSTER_KEY columns are present, and its real
     row/column counts match what the config recorded.
  6. src/services/bp4_decision_service.py imports cleanly, exposes a FastAPI `app`, and that app
     serves the required read-only routes (/, /health, /cluster/lookup, /clusters) - never
     /predict, since BP4 serves lookups, not predictions.
  7. The runtime packages bp4_decision_service.py actually imports (polars, fastapi, pydantic -
     grep-verified against that file, see this module's REQUIRED_RUNTIME_PACKAGES comment) are
     declared in pyproject.toml.
  8. tests/services/test_bp4_decision_service.py exists, and (optionally) actually passes via a
     real pytest subprocess - never a fabricated pass/fail count.
  9. Docker (Hardening Step 5) and CI (Hardening Step 6) presence - honestly PENDING until those
     steps exist, exactly like readiness_verdict.py's own _check_containerization_and_ci().

A real finding this module's path-resolution logic was originally written to handle, since fixed at
the source: BP4's persistence notebook (Section 11) used to write `parquet_relative_path` into the
config YAML via `f'  parquet_relative_path: "{PARQUET_PATH.relative_to(PROJECT_ROOT)}"'` - an
f-string over a raw Path object, NOT `.as_posix()`. On the real Windows machine this produced the
exact same double-quoted-YAML backslash-escape corruption already documented and fixed in
readiness_verdict.py's own module comment for BP1-3's `joblib_relative_path` field (a `\\b`
sequence silently parsing as a backspace control character, 0x08, at YAML-load time). The
notebook source has since been corrected to call `.as_posix()` on that path before interpolating
it (confirmed directly against the real on-device notebook - matches BP1-3's own already-fixed
pattern), so a freshly-run notebook no longer produces the corrupted form. This module's
`_resolve_config_relative_path()` below is kept as-is, unchanged: a standalone reimplementation of
readiness_verdict.py's own already-battle-tested reversal logic (same reasoning, same
tests/deployment/test_readiness_verdict.py precedent for BP3), now serving as defense-in-depth for
any config written by a pre-fix run of the notebook, rather than a workaround for a live bug. This
module never depends on readiness_verdict.py at runtime and is unaffected by concurrent edits to it.

Usage (from the project root, after `pip install -e .`):
    python -m deployment.bp4_readiness_verdict
    python -m deployment.bp4_readiness_verdict --write-report
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import polars as pl
import yaml

BP_ID = "bp4"
BP4_FOLDER = "bp4_customer_journey_analytics"
BP4_CONFIG_FILE = "bp4_customer_journey_analytics.yaml"
BP4_SERVICE_MODULE = "services.bp4_decision_service"
BP4_TEST_FILES = ("tests/services/test_bp4_decision_service.py",)
PERSISTENCE_CONFIG_BLOCK = "decision_artifact_persistence"

# The real, disclosed issue-cluster key - identical to bp4_decision_service.py's own CLUSTER_KEY
# and the Hardening Step 2 notebook's own sort/index key. Duplicated here as a plain constant
# (not imported from bp4_decision_service.py) so this check module never has to import the very
# service module one of its own checks is independently verifying the importability of.
CLUSTER_KEY = ["Company", "Product", "Sub-product", "Issue", "Sub-issue"]

# grep-verified (2026-09-24) against src/services/bp4_decision_service.py's own module-level
# import statements: `import polars as pl`, `from fastapi import FastAPI, HTTPException, Query`,
# `from pydantic import BaseModel, Field` - no pandas, no pyarrow, no joblib, no scikit-learn.
# polars, fastapi and pydantic are ALL already declared in pyproject.toml's own
# [project.dependencies] (added for BP1-3's own real needs), so - unlike BP1/2/3's own hardening
# passes - BP4's service required NO new pyproject.toml/requirements.txt entry.
REQUIRED_RUNTIME_PACKAGES = ("polars", "fastapi", "pydantic")

REQUIRED_ROUTES = ("/", "/health", "/cluster/lookup", "/clusters")
SHA256_MATCH_REQUIRED = True


class CheckStatus(str, Enum):
    # Not a credential - a check-result enum value bandit's hardcoded-password heuristic flags on
    # the literal name "PASS". Suppressed on the line itself, below (mirrors readiness_verdict.py).
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    WARN = "WARN"
    PENDING = "PENDING"  # not yet applicable - a later step's own scope, not a failure of this one


@dataclasses.dataclass
class CheckResult:
    name: str
    status: str
    detail: str

    def __post_init__(self) -> None:
        # Accept either a CheckStatus enum member or a plain string, but always STORE the plain
        # .value - otherwise str(CheckStatus.PASS) prints "CheckStatus.PASS" in every report.
        if isinstance(self.status, CheckStatus):
            self.status = self.status.value


@dataclasses.dataclass
class BP4ReadinessVerdict:
    bp_id: str
    generated_at_utc: str
    checks: list
    artifact_ready: bool
    service_ready: bool
    fully_deployable: bool

    def to_dict(self) -> dict:
        return {
            "bp_id": self.bp_id,
            "generated_at_utc": self.generated_at_utc,
            "checks": [dataclasses.asdict(c) for c in self.checks],
            "artifact_ready": self.artifact_ready,
            "service_ready": self.service_ready,
            "fully_deployable": self.fully_deployable,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# BP4 Deployment Readiness Verdict - {self.bp_id}",
            "",
            f"Generated: {self.generated_at_utc}",
            "",
            f"- **Decision artifact ready**: {'YES' if self.artifact_ready else 'NO'}",
            f"- **Service ready**: {'YES' if self.service_ready else 'NO'}",
            f"- **Fully deployable (containerized + CI)**: {'YES' if self.fully_deployable else 'NO'}",
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
    """Identical resolution order to every service/notebook in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) - reimplemented here (not imported from
    utils.performance_setup or from bp4_decision_service.py) for the same standalone reasoning
    given in this module's own docstring and in bp4_decision_service.py's own docstring."""
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


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_pyproject_dependencies(pyproject_path: Path) -> list:
    """Intentionally NOT a general TOML parser - same documented reasoning as
    readiness_verdict.py's own _parse_pyproject_dependencies(): this project's pyproject.toml has
    one simple `dependencies = [...]` array of quoted strings, and a real TOML-parsing dependency
    just for this diagnostic check would be its own new dependency to track."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def _requirement_declared(requirements: list, package: str) -> bool:
    package_lower = package.lower()
    return any(re.match(rf"^{re.escape(package_lower)}\s*[><=~!]", r.lower()) for r in requirements)


# Reversal table for PyYAML's own double-quoted-scalar single-character escapes - see this
# module's own docstring for the real, concrete BP4 finding this exists to handle (identical root
# cause to readiness_verdict.py's own already-documented BP1-3 `joblib_relative_path` corruption).
_YAML_SINGLE_CHAR_ESCAPE_REVERSE = {
    "\x07": "a",
    "\x08": "b",
    "\x0c": "f",
    "\x0a": "n",
    "\x0d": "r",
    "\x09": "t",
    "\x0b": "v",
    "\x00": "0",
}


def _resolve_config_relative_path(project_root: Path, raw_relative_path: str) -> Path:
    """Resolves a `parquet_relative_path` config value to a real filesystem Path, portably:
    reverses any YAML-escape corruption (see this module's own docstring), then splits on both
    `/` and `\\` and rejoins via Path.joinpath(*parts) so the check works regardless of which OS
    wrote the string (Windows, on the real device) or which OS is running this check (Linux, in a
    sandbox or CI). Standalone reimplementation of readiness_verdict.py's own function of the same
    name - see this module's docstring for why it is not imported from there instead."""
    recovered = "".join(
        f"\\{_YAML_SINGLE_CHAR_ESCAPE_REVERSE[ch]}" if ch in _YAML_SINGLE_CHAR_ESCAPE_REVERSE else ch
        for ch in raw_relative_path
    )
    parts = [p for p in re.split(r"[\\/]+", recovered) if p]
    return project_root.joinpath(*parts)


def _check_decision_artifact_persistence(project_root: Path, config_yaml: dict) -> tuple:
    """Returns (checks, parquet_path_or_None, artifact_ready: bool). BP4's structural analogue of
    readiness_verdict.py's _check_model_persistence_block(), adapted for a Parquet decision-
    records index instead of a joblib model bundle - no champion model, no accuracy/PR-AUC drift
    check, because BP4 has neither."""
    checks = []
    block = config_yaml.get(PERSISTENCE_CONFIG_BLOCK)
    if block is None:
        checks.append(
            CheckResult(
                "decision_artifact_persistence_config_block",
                CheckStatus.PENDING,
                f"No `{PERSISTENCE_CONFIG_BLOCK}:` block in configs/{BP4_CONFIG_FILE} yet - run "
                f"notebooks/{BP4_FOLDER}/{BP4_FOLDER}_decision_artifact_persistence.ipynb for real "
                "first (Hardening Step 2, BP4 variant). This is the expected, honest state until "
                "the user runs that notebook themselves.",
            )
        )
        return checks, None, False
    checks.append(
        CheckResult(
            "decision_artifact_persistence_config_block",
            CheckStatus.PASS,
            f"Present, n_rows={block.get('n_rows')!r}, n_columns={block.get('n_columns')!r}, "
            f"generated_at_utc={block.get('generated_at_utc')!r}.",
        )
    )

    parquet_relative_path = block.get("parquet_relative_path")
    parquet_path = (
        _resolve_config_relative_path(project_root, parquet_relative_path)
        if parquet_relative_path
        else None
    )
    if parquet_path is None or not parquet_path.exists():
        checks.append(
            CheckResult(
                "parquet_exists_on_disk",
                CheckStatus.FAIL,
                f"Config records parquet_relative_path={parquet_relative_path!r} but no file "
                "exists there - config and disk have drifted, or the artifact was deleted after "
                "the notebook ran.",
            )
        )
        return checks, None, False
    checks.append(CheckResult("parquet_exists_on_disk", CheckStatus.PASS, f"Found at {parquet_path}."))

    real_sha256 = _sha256_of(parquet_path)
    recorded_sha256 = block.get("parquet_sha256")
    if real_sha256 != recorded_sha256:
        checks.append(
            CheckResult(
                "parquet_integrity_sha256",
                CheckStatus.FAIL,
                f"Real file sha256 {real_sha256} does not match config's recorded "
                f"{recorded_sha256} - the file on disk is not the one the notebook actually "
                "persisted (modified, truncated, or corrupted since).",
            )
        )
        return checks, parquet_path, False
    checks.append(
        CheckResult("parquet_integrity_sha256", CheckStatus.PASS, f"{real_sha256} matches config.")
    )

    try:
        frame = pl.read_parquet(parquet_path)
    except Exception as exc:  # noqa: BLE001 - any parquet-read failure is a real, concrete FAIL
        checks.append(
            CheckResult(
                "parquet_loads_and_schema_sane",
                CheckStatus.FAIL,
                f"pl.read_parquet({parquet_path}) raised {type(exc).__name__}: {exc}",
            )
        )
        return checks, parquet_path, False

    missing_cols = [c for c in CLUSTER_KEY if c not in frame.columns]
    recorded_n_rows = block.get("n_rows")
    recorded_n_columns = block.get("n_columns")
    row_count_ok = recorded_n_rows is None or frame.height == recorded_n_rows
    col_count_ok = recorded_n_columns is None or len(frame.columns) == recorded_n_columns
    if missing_cols or not row_count_ok or not col_count_ok:
        checks.append(
            CheckResult(
                "parquet_loads_and_schema_sane",
                CheckStatus.FAIL,
                f"Loaded {frame.height:,} rows x {len(frame.columns)} columns; missing real "
                f"CLUSTER_KEY column(s): {missing_cols}; config recorded n_rows={recorded_n_rows!r} "
                f"(match={row_count_ok}), n_columns={recorded_n_columns!r} (match={col_count_ok}).",
            )
        )
        return checks, parquet_path, False
    checks.append(
        CheckResult(
            "parquet_loads_and_schema_sane",
            CheckStatus.PASS,
            f"Loaded cleanly: {frame.height:,} rows x {len(frame.columns)} columns, all real "
            f"CLUSTER_KEY columns {CLUSTER_KEY} present, matches config's recorded n_rows/n_columns.",
        )
    )

    artifact_ready = all(c.status == CheckStatus.PASS.value for c in checks)
    return checks, parquet_path, artifact_ready


def _check_service_importable(project_root: Path) -> list:
    checks = []
    src_dir = str(project_root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    try:
        if BP4_SERVICE_MODULE in sys.modules:
            del sys.modules[BP4_SERVICE_MODULE]
        module = importlib.import_module(BP4_SERVICE_MODULE)
    except Exception as exc:  # a broken service import is a real, concrete FAIL - never swallowed
        checks.append(
            CheckResult(
                "service_module_imports_cleanly",
                CheckStatus.FAIL,
                f"`import {BP4_SERVICE_MODULE}` raised {type(exc).__name__}: {exc}",
            )
        )
        return checks

    checks.append(
        CheckResult("service_module_imports_cleanly", CheckStatus.PASS, f"`{BP4_SERVICE_MODULE}` imported.")
    )

    app = getattr(module, "app", None)
    if app is None:
        checks.append(
            CheckResult("service_app_object_present", CheckStatus.FAIL, "Module has no `app` attribute.")
        )
        return checks

    try:
        from fastapi import FastAPI

        is_fastapi = isinstance(app, FastAPI)
    except ImportError:
        is_fastapi = hasattr(app, "routes")  # fastapi not installed in this environment - fall back

    if not is_fastapi:
        checks.append(
            CheckResult(
                "service_app_object_present",
                CheckStatus.FAIL,
                f"`app` is a {type(app).__name__}, not a FastAPI instance.",
            )
        )
        return checks
    checks.append(CheckResult("service_app_object_present", CheckStatus.PASS, "`app` is a FastAPI instance."))

    real_paths = {getattr(route, "path", None) for route in app.routes}
    missing = [p for p in REQUIRED_ROUTES if p not in real_paths]
    if missing:
        checks.append(
            CheckResult(
                "service_required_routes_present",
                CheckStatus.FAIL,
                f"Missing routes: {missing}. Found: {sorted(p for p in real_paths if p)}.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "service_required_routes_present",
                CheckStatus.PASS,
                f"All of {REQUIRED_ROUTES} present (read-only lookup/query routes - never "
                "/predict, BP4 fits no model).",
            )
        )
    return checks


def _check_dependencies_declared(project_root: Path) -> list:
    checks = []
    pyproject_deps = _parse_pyproject_dependencies(project_root / "pyproject.toml")
    for package in REQUIRED_RUNTIME_PACKAGES:
        declared = _requirement_declared(pyproject_deps, package)
        checks.append(
            CheckResult(
                f"pyproject_declares_{package}",
                CheckStatus.PASS if declared else CheckStatus.FAIL,
                f"{'Found' if declared else 'NOT found'} in pyproject.toml [project.dependencies] "
                f"(grep-verified real import in src/services/bp4_decision_service.py).",
            )
        )
    return checks


def _check_test_files_exist_and_pass(project_root: Path, run_tests: bool) -> list:
    checks = []
    missing = [t for t in BP4_TEST_FILES if not (project_root / t).exists()]
    if missing:
        checks.append(
            CheckResult("test_files_present", CheckStatus.FAIL, f"Missing test file(s): {missing}.")
        )
        return checks
    checks.append(CheckResult("test_files_present", CheckStatus.PASS, f"All of {BP4_TEST_FILES} present."))

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
        # No shell=True: args are a fixed list built from this module's own constants (never
        # external/untrusted input), and sys.executable is the real interpreter already running
        # this process. Same suppression reasoning as readiness_verdict.py's own identical call.
        result = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pytest", *BP4_TEST_FILES, "-q"],
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


def _check_containerization_and_ci(project_root: Path) -> list:
    """Steps 5 (Docker) and 6 (CI) - PENDING is the honest, expected result until they exist, not
    a failure of Step 4's own scope. Same pattern as readiness_verdict.py's own
    _check_containerization_and_ci(), pointed at BP4's own service directory name."""
    checks = []
    dockerfile_candidates = [
        project_root / "src" / "services" / "docker" / "bp4_decision_service" / "Dockerfile",
        project_root / "docker" / "bp4_decision_service" / "Dockerfile",
    ]
    if any(p.exists() for p in dockerfile_candidates):
        found = next(p for p in dockerfile_candidates if p.exists())
        checks.append(CheckResult("dockerfile_present", CheckStatus.PASS, f"Found at {found}."))
    else:
        checks.append(
            CheckResult(
                "dockerfile_present",
                CheckStatus.PENDING,
                "No Dockerfile yet - Hardening Step 5 (Docker packaging) has not started.",
            )
        )

    ci_dir = project_root / ".github" / "workflows"
    if ci_dir.exists() and any(ci_dir.glob("*.yml")):
        checks.append(CheckResult("ci_workflow_present", CheckStatus.PASS, f"Found workflow(s) in {ci_dir}."))
    else:
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PENDING,
                "No .github/workflows/*.yml yet - Hardening Step 6 (CI wiring) has not started.",
            )
        )
    return checks


def assess_bp4_deployment_readiness(
    project_root: Optional[Path] = None, run_tests: bool = True
) -> BP4ReadinessVerdict:
    if project_root is None:
        project_root = resolve_project_root()

    config_path = project_root / "configs" / BP4_CONFIG_FILE
    if not config_path.exists():
        checks = [
            CheckResult(
                "bp4_config_exists",
                CheckStatus.FAIL,
                f"configs/{BP4_CONFIG_FILE} not found - no BP4 gates have run yet.",
            )
        ]
        return BP4ReadinessVerdict(
            bp_id=BP_ID,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            checks=checks,
            artifact_ready=False,
            service_ready=False,
            fully_deployable=False,
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config_yaml = yaml.safe_load(f) or {}

    checks: list = [CheckResult("bp4_config_exists", CheckStatus.PASS, f"Found at {config_path}.")]

    persistence_checks, _parquet_path, artifact_ready = _check_decision_artifact_persistence(
        project_root, config_yaml
    )
    checks.extend(persistence_checks)

    service_checks = _check_service_importable(project_root)
    checks.extend(service_checks)

    dependency_checks = _check_dependencies_declared(project_root)
    checks.extend(dependency_checks)

    test_checks = _check_test_files_exist_and_pass(project_root, run_tests)
    checks.extend(test_checks)

    container_ci_checks = _check_containerization_and_ci(project_root)
    checks.extend(container_ci_checks)

    service_ready = (
        artifact_ready
        and all(c.status == CheckStatus.PASS.value for c in service_checks)
        and all(c.status == CheckStatus.PASS.value for c in dependency_checks)
        and all(c.status in (CheckStatus.PASS.value, CheckStatus.PENDING.value) for c in test_checks)
        and not any(c.status == CheckStatus.FAIL.value for c in test_checks)
    )
    fully_deployable = service_ready and all(c.status == CheckStatus.PASS.value for c in container_ci_checks)

    return BP4ReadinessVerdict(
        bp_id=BP_ID,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        artifact_ready=artifact_ready,
        service_ready=service_ready,
        fully_deployable=fully_deployable,
    )


def _write_report(verdict: BP4ReadinessVerdict, project_root: Path) -> tuple:
    import json

    out_dir = project_root / "reports" / BP4_FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bp4_deployment_readiness_verdict.json"
    md_path = out_dir / "bp4_deployment_readiness_verdict.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verdict.to_dict(), f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(verdict.to_markdown())
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer360 Navigator BP4 deployment-readiness verdict.")
    parser.add_argument("--no-run-tests", action="store_true", help="Skip executing the pytest suite.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON+MD under reports/bp4_.../")
    args = parser.parse_args()

    project_root = resolve_project_root()
    verdict = assess_bp4_deployment_readiness(project_root, run_tests=not args.no_run_tests)
    print(verdict.to_markdown())
    if args.write_report:
        json_path, md_path = _write_report(verdict, project_root)
        print(f"[SAVED] {json_path}")
        print(f"[SAVED] {md_path}")
    return 0 if verdict.service_ready else 1


if __name__ == "__main__":
    sys.exit(main())
