"""
src/deployment/bp5_readiness_verdict.py — Customer360 Navigator

BP5 (Root-Cause & Driver Analytics) deployment-readiness verdict module (Hardening pass, BP5
variant). A pure read-only audit, same honesty spirit as readiness_verdict.py and
bp4_readiness_verdict.py: it inspects the REAL artifacts BP5's own gates already wrote to disk (or
does not find them, and says so honestly as PENDING/FAIL) and produces an itemized, structured
verdict - never a subjective "looks good", never a fabricated PASS.

Deliberately a SEPARATE standalone sibling module, not an extension of readiness_verdict.py or
bp4_readiness_verdict.py. BP5 fits no deployable supervised classifier at all - unlike BP1/2/3
(joblib champion bundle) AND unlike BP4 (a persisted Parquet decision-artifact index). Confirmed
directly from src/services/bp5_driver_service.py's own module docstring: BP5's Gate 3 logistic
regression exists only to drive SHAP/coefficient-based ASSOCIATION findings, never a decision
boundary, and BP5 "has no such persistence notebook" - models/bp5_root_cause_driver_analytics/
holds only a .gitkeep, by design, not by omission. There is therefore no model_persistence-style
config block, no champion accuracy/PR-AUC to drift-check, and no Parquet index either. Building a
"bp5" entry into either existing module would mean fabricating an artifact-readiness concept BP5
does not have - unacceptable under this project's zero-fabrication rule - so this module instead
audits exactly what BP5's own real, already-committed evidence actually is: the Gate 5 prioritized
root-cause report JSON (one per outcome) and the Gate 7 executive rollup manifest, both already
real-run confirmed and already committed under notebooks/bp5_root_cause_driver_analytics/artifacts/
(NOT gitignored - see .gitignore - so these are real, already-committed evidence, not something a
Claude session generates), exactly the same "read the real committed artifacts directly" shape
bp5_driver_service.py itself already established, and BP6's own service before it.

What this module actually checks, against BP5's real, two-outcome artifact shape:
  1. configs/bp5_root_cause_driver_analytics.yaml exists.
  2. For EACH of BP5's two real outcomes (outcome_1_intervention_required,
     outcome_2_timely_response_failure): the Gate 5 prioritized root-cause report JSON exists,
     parses, and carries the real required keys this project's own schema uses (never assumed -
     grep/read-verified against the real on-device file: outcome_field, field_level_ranking,
     category_level_findings_by_field, champion_shap_feature_importance,
     company_process_field_finding, champion_validation_snapshot,
     barred_field_governance_disclosures, narrative_text, association_not_causation_disclaimer,
     min_n_per_category_threshold_used, top_k_fields, top_k_categories_per_field,
     top_k_shap_features) - and that outcome_field inside the JSON matches the outcome the
     filename claims (a real drift/mismatch would be a concrete FAIL, never silently accepted).
  3. association_not_causation_disclaimer is present and non-empty in both reports - BP5's central
     governance guardrail (this BP tests statistical ASSOCIATION only, never causation) must
     survive into every real artifact this module inspects, never silently dropped.
  4. The Gate 7 executive rollup manifest (executive_rollup_manifest.json) exists, parses, has
     bp_id=="bp5", and its own real output_paths (dashboard_html/report_docx/workbook_xlsx/
     deck_pptx) all exist on disk with byte sizes matching what the manifest itself recorded in
     output_sizes_bytes (drift/tamper detection - same spirit as readiness_verdict.py's
     joblib_bundle_integrity_sha256 check and bp4_readiness_verdict.py's parquet sha256 check,
     adapted to file-size comparison since the rollup outputs are DOCX/XLSX/PPTX/HTML rather than
     a single hashable data file already recorded with a sha256 in this project's real schema).
  5. src/services/bp5_driver_service.py imports cleanly, exposes a FastAPI `app`, and that app
     serves the required read-only routes (grep-verified against the real file: /, /health,
     /outcomes, /report/{outcome}, /report/{outcome}/top-drivers, /rollup) - never /predict, since
     BP5 serves real, already-computed findings, not live predictions.
  6. The runtime packages bp5_driver_service.py actually imports (fastapi, pydantic - grep-verified,
     no polars/pandas/joblib/scikit-learn: this service is pure JSON-file serving) are declared in
     pyproject.toml.
  7. tests/services/test_bp5_driver_service.py exists, and (optionally) actually passes via a real
     pytest subprocess - never a fabricated pass/fail count.
  8. Docker and CI presence - honestly PENDING if not found, PASS if found; both were in fact
     already delivered for BP5 as of this module's writing (src/services/docker/bp5_driver_service/
     and a docker-validate CI job entry), so this check is expected to PASS today, not PENDING -
     but the check itself makes no such assumption and reports whatever it actually finds on disk.

Usage (from the project root, after `pip install -e .`):
    python -m deployment.bp5_readiness_verdict
    python -m deployment.bp5_readiness_verdict --write-report
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
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

BP_ID = "bp5"
BP5_FOLDER = "bp5_root_cause_driver_analytics"
BP5_CONFIG_FILE = "bp5_root_cause_driver_analytics.yaml"
BP5_SERVICE_MODULE = "services.bp5_driver_service"
BP5_TEST_FILES = ("tests/services/test_bp5_driver_service.py",)

ARTIFACTS_RELATIVE_DIR = Path("notebooks") / BP5_FOLDER / "artifacts"
ROLLUP_FILENAME = "executive_rollup_manifest.json"

# The real two outcomes and their real Gate 5 report filenames - identical to
# bp5_driver_service.py's own VALID_OUTCOMES / REPORT_FILENAMES constants (grep-verified against
# that file, duplicated here rather than imported so this check module never depends on the very
# service module one of its own checks is independently verifying the importability of).
VALID_OUTCOMES = (
    "outcome_1_intervention_required",
    "outcome_2_timely_response_failure",
)
REPORT_FILENAMES: dict = {
    "outcome_1_intervention_required": (
        "gate5_prioritized_root_cause_report_outcome_1_intervention_required.json"
    ),
    "outcome_2_timely_response_failure": (
        "gate5_prioritized_root_cause_report_outcome_2_timely_response_failure.json"
    ),
}

# Real required keys in each Gate 5 report - read-verified 2026-09-25 directly against the real
# on-device gate5_prioritized_root_cause_report_outcome_1_intervention_required.json.
REQUIRED_GATE5_REPORT_KEYS = (
    "outcome_field",
    "association_not_causation_disclaimer",
    "field_level_ranking",
    "category_level_findings_by_field",
    "champion_shap_feature_importance",
    "company_process_field_finding",
    "champion_validation_snapshot",
    "barred_field_governance_disclosures",
    "narrative_text",
    "min_n_per_category_threshold_used",
    "top_k_fields",
    "top_k_categories_per_field",
    "top_k_shap_features",
)

REQUIRED_ROLLUP_OUTPUT_KEYS = ("dashboard_html", "report_docx", "workbook_xlsx", "deck_pptx")

# grep-verified (2026-09-25) against src/services/bp5_driver_service.py's own module-level import
# statements: `from fastapi import FastAPI, HTTPException`, `from pydantic import BaseModel,
# Field` - no polars, no pandas, no joblib, no scikit-learn (this service serves real,
# already-committed JSON files directly, it fits/loads no model). Both packages are already
# declared in pyproject.toml (added for BP1-3's own real needs), so - like BP4's service - BP5's
# service required no new pyproject.toml/requirements.txt entry.
REQUIRED_RUNTIME_PACKAGES = ("fastapi", "pydantic")

REQUIRED_ROUTES = (
    "/", "/health", "/outcomes", "/report/{outcome}", "/report/{outcome}/top-drivers", "/rollup",
)


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
class BP5ReadinessVerdict:
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
            f"# BP5 Deployment Readiness Verdict - {self.bp_id}",
            "",
            f"Generated: {self.generated_at_utc}",
            "",
            f"- **Real Gate 5/Gate 7 evidence ready**: {'YES' if self.artifact_ready else 'NO'}",
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
    """Identical resolution order to every service/notebook/readiness module in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) - reimplemented here (not imported from
    readiness_verdict.py or bp4_readiness_verdict.py) for the same standalone reasoning given in
    this module's own docstring: no readiness-verdict sibling module depends on another at
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
    readiness_verdict.py's and bp4_readiness_verdict.py's own identically-named function."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def _requirement_declared(requirements: list, package: str) -> bool:
    package_lower = package.lower()
    return any(re.match(rf"^{re.escape(package_lower)}\s*[><=~!]", r.lower()) for r in requirements)


def _check_gate5_reports(project_root: Path) -> tuple:
    """Returns (checks, all_ready: bool). One structural pass per real outcome - never merged into
    a single check, so a problem with one outcome's report is never masked by the other's PASS."""
    checks: list = []
    artifacts_dir = project_root / ARTIFACTS_RELATIVE_DIR
    all_ready = True

    for outcome in VALID_OUTCOMES:
        report_path = artifacts_dir / REPORT_FILENAMES[outcome]
        if not report_path.exists():
            checks.append(
                CheckResult(
                    f"gate5_report_exists[{outcome}]",
                    CheckStatus.FAIL,
                    f"Expected at {report_path} - Gate 5 has not produced this outcome's real "
                    "prioritized root-cause report.",
                )
            )
            all_ready = False
            continue

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            checks.append(
                CheckResult(
                    f"gate5_report_exists[{outcome}]",
                    CheckStatus.FAIL,
                    f"Found at {report_path} but failed to parse as JSON: "
                    f"{type(exc).__name__}: {exc}",
                )
            )
            all_ready = False
            continue

        checks.append(
            CheckResult(f"gate5_report_exists[{outcome}]", CheckStatus.PASS, f"Found at {report_path}.")
        )

        missing_keys = [k for k in REQUIRED_GATE5_REPORT_KEYS if k not in report]
        if missing_keys:
            checks.append(
                CheckResult(
                    f"gate5_report_schema[{outcome}]",
                    CheckStatus.FAIL,
                    f"Missing real required key(s): {missing_keys}.",
                )
            )
            all_ready = False
        else:
            checks.append(
                CheckResult(
                    f"gate5_report_schema[{outcome}]",
                    CheckStatus.PASS,
                    f"All {len(REQUIRED_GATE5_REPORT_KEYS)} real required keys present.",
                )
            )

        report_outcome_field = report.get("outcome_field")
        if report_outcome_field != outcome:
            checks.append(
                CheckResult(
                    f"gate5_report_outcome_matches_filename[{outcome}]",
                    CheckStatus.FAIL,
                    f"Filename claims outcome={outcome!r} but the report's own outcome_field "
                    f"reads {report_outcome_field!r} - a real drift between the artifact's name "
                    "and its content.",
                )
            )
            all_ready = False
        else:
            checks.append(
                CheckResult(
                    f"gate5_report_outcome_matches_filename[{outcome}]",
                    CheckStatus.PASS,
                    "outcome_field matches the filename's own outcome.",
                )
            )

        disclaimer = report.get("association_not_causation_disclaimer")
        if not disclaimer:
            checks.append(
                CheckResult(
                    f"association_not_causation_disclaimer_present[{outcome}]",
                    CheckStatus.FAIL,
                    "association_not_causation_disclaimer is missing or empty - BP5's central "
                    "governance guardrail must survive into every real artifact.",
                )
            )
            all_ready = False
        else:
            checks.append(
                CheckResult(
                    f"association_not_causation_disclaimer_present[{outcome}]",
                    CheckStatus.PASS,
                    "Present and non-empty.",
                )
            )

    return checks, all_ready


def _check_gate7_rollup_manifest(project_root: Path) -> tuple:
    """Returns (checks, all_ready: bool). Checks the manifest itself, then cross-checks every
    real output file it names against what is actually on disk (existence + byte-size match) -
    drift/tamper detection, same spirit as every other BP's readiness-verdict module."""
    checks: list = []
    manifest_path = project_root / ARTIFACTS_RELATIVE_DIR / ROLLUP_FILENAME

    if not manifest_path.exists():
        checks.append(
            CheckResult(
                "gate7_rollup_manifest_exists",
                CheckStatus.FAIL,
                f"Expected at {manifest_path} - the Gate 7 executive rollup has not produced a "
                "real manifest.",
            )
        )
        return checks, False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(
            CheckResult(
                "gate7_rollup_manifest_exists",
                CheckStatus.FAIL,
                f"Found at {manifest_path} but failed to parse as JSON: {type(exc).__name__}: {exc}",
            )
        )
        return checks, False

    checks.append(CheckResult("gate7_rollup_manifest_exists", CheckStatus.PASS, f"Found at {manifest_path}."))

    if manifest.get("bp_id") != "bp5":
        checks.append(
            CheckResult(
                "gate7_rollup_manifest_bp_id",
                CheckStatus.FAIL,
                f"Manifest bp_id={manifest.get('bp_id')!r}, expected 'bp5'.",
            )
        )
        return checks, False
    checks.append(CheckResult("gate7_rollup_manifest_bp_id", CheckStatus.PASS, "bp_id == 'bp5'."))

    output_paths = manifest.get("output_paths") or {}
    output_sizes = manifest.get("output_sizes_bytes") or {}
    missing_keys = [k for k in REQUIRED_ROLLUP_OUTPUT_KEYS if k not in output_paths]
    if missing_keys:
        checks.append(
            CheckResult(
                "gate7_rollup_output_paths_declared",
                CheckStatus.FAIL,
                f"Manifest's output_paths is missing real key(s): {missing_keys}.",
            )
        )
        return checks, False
    checks.append(
        CheckResult(
            "gate7_rollup_output_paths_declared",
            CheckStatus.PASS,
            f"All {len(REQUIRED_ROLLUP_OUTPUT_KEYS)} real output keys declared.",
        )
    )

    all_ready = True
    for key in REQUIRED_ROLLUP_OUTPUT_KEYS:
        raw_relative = str(output_paths[key])
        parts = [p for p in re.split(r"[\\/]+", raw_relative) if p]
        output_file = project_root.joinpath(*parts)
        if not output_file.exists():
            checks.append(
                CheckResult(
                    f"gate7_rollup_output_exists[{key}]",
                    CheckStatus.FAIL,
                    f"Manifest names {output_file} but no file exists there.",
                )
            )
            all_ready = False
            continue
        real_size = output_file.stat().st_size
        recorded_size = output_sizes.get(key)
        if recorded_size is not None and real_size != recorded_size:
            checks.append(
                CheckResult(
                    f"gate7_rollup_output_size_matches[{key}]",
                    CheckStatus.FAIL,
                    f"Real size {real_size:,} bytes does not match manifest's recorded "
                    f"{recorded_size:,} bytes for {output_file} - the file on disk is not the "
                    "one the rollup notebook actually wrote.",
                )
            )
            all_ready = False
        else:
            checks.append(
                CheckResult(
                    f"gate7_rollup_output_size_matches[{key}]",
                    CheckStatus.PASS,
                    f"{real_size:,} bytes, matches manifest.",
                )
            )

    return checks, all_ready


def _check_service_importable(project_root: Path) -> list:
    checks = []
    src_dir = str(project_root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    try:
        # Drop BOTH the submodule AND its parent "services" package from sys.modules before
        # re-importing, then invalidate import caches. A stale cached parent package would keep
        # resolving "services.bp5_driver_service" against whichever src/ directory "services" was
        # FIRST imported from in this process, silently ignoring a freshly-inserted sys.path entry
        # for a different project_root - a real cross-call caching gap this check must not carry
        # (found and fixed via this module's own test suite exercising several different
        # project roots against the same long-lived pytest process).
        for mod_name in (BP5_SERVICE_MODULE, BP5_SERVICE_MODULE.split(".")[0]):
            sys.modules.pop(mod_name, None)
        importlib.invalidate_caches()
        module = importlib.import_module(BP5_SERVICE_MODULE)
    except Exception as exc:  # a broken service import is a real, concrete FAIL - never swallowed
        checks.append(
            CheckResult(
                "service_module_imports_cleanly",
                CheckStatus.FAIL,
                f"`import {BP5_SERVICE_MODULE}` raised {type(exc).__name__}: {exc}",
            )
        )
        return checks

    checks.append(
        CheckResult("service_module_imports_cleanly", CheckStatus.PASS, f"`{BP5_SERVICE_MODULE}` imported.")
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
        is_fastapi = hasattr(app, "routes")

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
                f"All of {REQUIRED_ROUTES} present (read-only reporting routes - never /predict, "
                "BP5 fits no deployable classifier).",
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
                "(grep-verified real import in src/services/bp5_driver_service.py).",
            )
        )
    return checks


def _check_test_files_exist_and_pass(project_root: Path, run_tests: bool) -> list:
    checks = []
    missing = [t for t in BP5_TEST_FILES if not (project_root / t).exists()]
    if missing:
        checks.append(
            CheckResult("test_files_present", CheckStatus.FAIL, f"Missing test file(s): {missing}.")
        )
        return checks
    checks.append(CheckResult("test_files_present", CheckStatus.PASS, f"All of {BP5_TEST_FILES} present."))

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
            [sys.executable, "-m", "pytest", *BP5_TEST_FILES, "-q"],
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
    checks = []
    dockerfile_candidates = [
        project_root / "src" / "services" / "docker" / "bp5_driver_service" / "Dockerfile",
        project_root / "docker" / "bp5_driver_service" / "Dockerfile",
    ]
    if any(p.exists() for p in dockerfile_candidates):
        found = next(p for p in dockerfile_candidates if p.exists())
        checks.append(CheckResult("dockerfile_present", CheckStatus.PASS, f"Found at {found}."))
    else:
        checks.append(
            CheckResult(
                "dockerfile_present",
                CheckStatus.PENDING,
                "No Dockerfile yet for bp5_driver_service.",
            )
        )

    ci_path = project_root / ".github" / "workflows" / "ci.yml"
    if ci_path.exists() and "bp5_driver_service" in ci_path.read_text(encoding="utf-8"):
        checks.append(
            CheckResult(
                "ci_workflow_present", CheckStatus.PASS, f"bp5_driver_service referenced in {ci_path}."
            )
        )
    else:
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PENDING,
                "No .github/workflows/ci.yml entry for bp5_driver_service yet.",
            )
        )
    return checks


def assess_bp5_deployment_readiness(
    project_root: Optional[Path] = None, run_tests: bool = True
) -> BP5ReadinessVerdict:
    if project_root is None:
        project_root = resolve_project_root()

    config_path = project_root / "configs" / BP5_CONFIG_FILE
    if not config_path.exists():
        checks = [
            CheckResult(
                "bp5_config_exists",
                CheckStatus.FAIL,
                f"configs/{BP5_CONFIG_FILE} not found - no BP5 gates have run yet.",
            )
        ]
        return BP5ReadinessVerdict(
            bp_id=BP_ID,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            checks=checks,
            artifact_ready=False,
            service_ready=False,
            fully_deployable=False,
        )

    checks: list = [CheckResult("bp5_config_exists", CheckStatus.PASS, f"Found at {config_path}.")]
    # Loaded for parity with every other readiness module even though this module's own checks
    # read real artifacts directly rather than a config block - kept so a YAML parse failure is
    # itself surfaced as a concrete FAIL rather than silently ignored.
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as exc:
        checks.append(
            CheckResult("bp5_config_parses", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}")
        )

    gate5_checks, gate5_ready = _check_gate5_reports(project_root)
    checks.extend(gate5_checks)

    gate7_checks, gate7_ready = _check_gate7_rollup_manifest(project_root)
    checks.extend(gate7_checks)

    artifact_ready = gate5_ready and gate7_ready

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

    return BP5ReadinessVerdict(
        bp_id=BP_ID,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        artifact_ready=artifact_ready,
        service_ready=service_ready,
        fully_deployable=fully_deployable,
    )


def _write_report(verdict: BP5ReadinessVerdict, project_root: Path) -> tuple:
    out_dir = project_root / "reports" / BP5_FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bp5_deployment_readiness_verdict.json"
    md_path = out_dir / "bp5_deployment_readiness_verdict.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verdict.to_dict(), f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(verdict.to_markdown())
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer360 Navigator BP5 deployment-readiness verdict.")
    parser.add_argument("--no-run-tests", action="store_true", help="Skip executing the pytest suite.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON+MD under reports/bp5_.../")
    args = parser.parse_args()

    project_root = resolve_project_root()
    verdict = assess_bp5_deployment_readiness(project_root, run_tests=not args.no_run_tests)
    print(verdict.to_markdown())
    if args.write_report:
        json_path, md_path = _write_report(verdict, project_root)
        print(f"[SAVED] {json_path}")
        print(f"[SAVED] {md_path}")
    return 0 if verdict.service_ready else 1


if __name__ == "__main__":
    sys.exit(main())
