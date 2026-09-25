"""
src/deployment/readiness_verdict.py — Customer360 Navigator

Deployment-readiness verdict module (Hardening Step 4). A pure read-only audit: inspects the REAL
artifacts earlier steps already wrote to disk (or does not find them, and says so) for one BP, and
produces an itemized, structured verdict - never a subjective "looks good". Runs no notebook and
touches no real customer-complaint data itself; every check either reads a real file already on
disk, recomputes a real hash/import over it, or (for the test-suite check) runs the project's own
already-existing pytest suite as a subprocess - never fabricates a pass/fail count or an accuracy
figure. Safe to run at any time, as many times as needed, with no side effects beyond writing its
own verdict report when asked to.

Deliberately scoped to what Steps 1-3 actually built: model persistence (Step 2) and the FastAPI
inference services (Step 3). Containerization (Step 5) and CI (Step 6) are later steps in this same
hardening pass - this module checks for their artifacts honestly (PENDING today, not a failure of
THIS step) rather than pretending they're already in scope.

Usage (from the project root, after `pip install -e .`):
    python -m deployment.readiness_verdict --bp bp1
    python -m deployment.readiness_verdict --bp bp1 --bp bp2 --write-report
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

from models.model_persistence import load_model_bundle
from utils.performance_setup import resolve_project_root

# ---------------------------------------------------------------------------
# BP registry - the only place a new BP's readiness wiring needs to be added.
# ---------------------------------------------------------------------------
SUPPORTED_BPS: dict[str, dict[str, object]] = {
    "bp1": {
        "folder": "bp1_customer_intent_classification",
        "config_file": "bp1_customer_intent_classification.yaml",
        "service_module": "services.bp1_inference_service",
        "champion_config_block": "gate3_model_benchmark",
        "champion_metric_key": "held_out_test_accuracy",
        "persistence_metric_key": "fresh_refit_test_accuracy",
        "persistence_reload_diff_key": "reload_accuracy_diff",
        "metric_label": "accuracy",
        "test_files": (
            "tests/shared/test_model_persistence.py",
            "tests/services/test_bp1_inference_service.py",
        ),
    },
    "bp2": {
        "folder": "bp2_customer_friction_classification",
        "config_file": "bp2_customer_friction_classification.yaml",
        "service_module": "services.bp2_inference_service",
        "champion_config_block": "gate5_decision_layer",
        "champion_metric_key": "overall_test_accuracy_recomputed",
        "persistence_metric_key": "fresh_refit_test_accuracy",
        "persistence_reload_diff_key": "reload_accuracy_diff",
        "metric_label": "accuracy",
        "test_files": (
            "tests/shared/test_model_persistence.py",
            "tests/services/test_bp2_inference_service.py",
        ),
    },
    "bp3": {
        "folder": "bp3_complaint_escalation_prediction",
        "config_file": "bp3_complaint_escalation_prediction.yaml",
        "service_module": "services.bp3_inference_service",
        "champion_config_block": "gate5_decision_layer",
        "champion_metric_key": "held_out_test_pr_auc_recomputed",
        "persistence_metric_key": "fresh_refit_test_pr_auc",
        "persistence_reload_diff_key": "reload_pr_auc_diff",
        "metric_label": "PR-AUC",
        "test_files": (
            "tests/shared/test_model_persistence.py",
            "tests/services/test_bp3_inference_service.py",
        ),
    },
}

ACCURACY_TOLERANCE = 1e-4  # cross-artifact float-compare tolerance (real floats, real rounding)
RELOAD_DIFF_TOLERANCE = 1e-6
REQUIRED_ROUTES = ("/", "/health", "/predict")


class CheckStatus(str, Enum):
    # Not a credential - a check-result enum value bandit's hardcoded-password heuristic
    # flags on the literal name "PASS". Suppressed on the line itself, below.
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
        # Accept either a CheckStatus enum member (convenient at call sites) or a plain string,
        # but always STORE the plain .value - otherwise str(CheckStatus.PASS) prints the ugly
        # "CheckStatus.PASS" (a real str/Enum mixin gotcha, not a design choice) in every report.
        if isinstance(self.status, CheckStatus):
            self.status = self.status.value


@dataclasses.dataclass
class ReadinessVerdict:
    bp_id: str
    generated_at_utc: str
    checks: list
    model_artifact_ready: bool
    service_ready: bool
    fully_deployable: bool

    def to_dict(self) -> dict:
        return {
            "bp_id": self.bp_id,
            "generated_at_utc": self.generated_at_utc,
            "checks": [dataclasses.asdict(c) for c in self.checks],
            "model_artifact_ready": self.model_artifact_ready,
            "service_ready": self.service_ready,
            "fully_deployable": self.fully_deployable,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Deployment Readiness Verdict - {self.bp_id}",
            "",
            f"Generated: {self.generated_at_utc}",
            "",
            f"- **Model artifact ready**: {'YES' if self.model_artifact_ready else 'NO'}",
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


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_pyproject_dependencies(pyproject_path: Path) -> list:
    """Intentionally NOT a general TOML parser - this project's pyproject.toml has one simple
    `dependencies = [...]` array of quoted strings, and adding a real TOML-parsing dependency
    just for this diagnostic check would be its own new dependency to track. A line-scoped regex
    over that known, simple shape is honest about what it does and doesn't handle."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def _requirement_declared(requirements: list, package: str) -> bool:
    package_lower = package.lower()
    return any(re.match(rf"^{re.escape(package_lower)}\s*[><=~!]", r.lower()) for r in requirements)


# The model-persistence notebooks previously wrote `joblib_relative_path` into the config YAML
# via an f-string embedding `out_path.relative_to(PROJECT_ROOT)` directly - on this project's real
# Windows machine that yields backslash-separated segments (e.g.
# `models\bp3_complaint_escalation_prediction\bp3_champion_bundle.joblib`), written into a
# DOUBLE-QUOTED YAML scalar. YAML double-quoted scalars treat backslash as an escape character, so
# a segment starting with certain letters (here, both segments happened to start with "b") gets
# silently corrupted at YAML-PARSE time into a single control character (`\b` -> backspace 0x08) -
# a real, observed value on this project's own already-real-run BP3 config (2026-09-24), not a
# hypothetical one. The notebooks now write `.as_posix()` (forward slashes, which YAML never
# escapes) going forward, so this corruption cannot recur in a freshly-written config - but a
# config already written before that fix (BP3's real one, right now) still has the corrupted
# escape baked in, and no re-run is needed to read it correctly: the corruption is a reversible,
# deterministic single-character substitution (a real file path never legitimately contains a
# control character), so reversing it before splitting recovers the original path exactly.
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
    """Resolves a `joblib_relative_path` config value to a real filesystem Path, portably: reverses
    any YAML-escape corruption (see the module-level comment above this function), then splits on
    both `/` and `\\` and rejoins via Path.joinpath(*parts) so the check works regardless of which
    OS wrote the string or which OS (Windows locally, Linux in Docker/CI) is running the check."""
    recovered = "".join(
        f"\\{_YAML_SINGLE_CHAR_ESCAPE_REVERSE[ch]}" if ch in _YAML_SINGLE_CHAR_ESCAPE_REVERSE else ch
        for ch in raw_relative_path
    )
    parts = [p for p in re.split(r"[\\/]+", recovered) if p]
    return project_root.joinpath(*parts)


def _check_model_persistence_block(project_root: Path, bp_config: dict, config_yaml: dict) -> tuple:
    """Returns (checks, model_bundle_path_or_None, model_artifact_ready: bool)."""
    checks = []
    block = config_yaml.get("model_persistence")
    if block is None:
        checks.append(
            CheckResult(
                "model_persistence_config_block",
                CheckStatus.PENDING,
                f"No `model_persistence:` block in configs/{bp_config['config_file']} yet - "
                f"run notebooks/{bp_config['folder']}/{bp_config['folder']}_model_persistence.ipynb "
                "for real first (Hardening Step 2).",
            )
        )
        return checks, None, False
    checks.append(
        CheckResult(
            "model_persistence_config_block",
            CheckStatus.PASS,
            f"Present, champion={block.get('champion_model')!r}, generated_at_utc="
            f"{block.get('generated_at_utc')!r}.",
        )
    )

    joblib_relative_path = block.get("joblib_relative_path")
    bundle_path = (
        _resolve_config_relative_path(project_root, joblib_relative_path) if joblib_relative_path else None
    )
    if bundle_path is None or not bundle_path.exists():
        checks.append(
            CheckResult(
                "joblib_bundle_exists_on_disk",
                CheckStatus.FAIL,
                f"Config records joblib_relative_path={joblib_relative_path!r} but no file exists "
                "there - config and disk have drifted, or the bundle was deleted after the "
                "notebook ran.",
            )
        )
        return checks, None, False
    checks.append(CheckResult("joblib_bundle_exists_on_disk", CheckStatus.PASS, f"Found at {bundle_path}."))

    real_sha256 = _sha256_of(bundle_path)
    recorded_sha256 = block.get("joblib_sha256")
    if real_sha256 != recorded_sha256:
        checks.append(
            CheckResult(
                "joblib_bundle_integrity_sha256",
                CheckStatus.FAIL,
                f"Real file sha256 {real_sha256} does not match config's recorded "
                f"{recorded_sha256} - the file on disk is not the one the notebook actually "
                "persisted (modified, truncated, or corrupted since).",
            )
        )
        return checks, bundle_path, False
    checks.append(
        CheckResult(
            "joblib_bundle_integrity_sha256",
            CheckStatus.PASS,
            f"{real_sha256} matches config.",
        )
    )

    try:
        bundle = load_model_bundle(bundle_path)
        checks.append(
            CheckResult(
                "joblib_bundle_loads_and_passes_contract",
                CheckStatus.PASS,
                f"Loaded via load_model_bundle(); REQUIRED_KEYS contract for bp_id="
                f"{bundle.get('bp_id')!r} satisfied.",
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        checks.append(CheckResult("joblib_bundle_loads_and_passes_contract", CheckStatus.FAIL, str(exc)))
        return checks, bundle_path, False

    # Field names are per-BP (bp1/bp2 persist an accuracy-named pair; bp3's fidelity metric is
    # PR-AUC, never accuracy - see model_persistence.py's module docstring), looked up from the
    # registry rather than hardcoded, so this one check function serves every supported BP without
    # a per-metric branch. Check `name` fields below are deliberately left unchanged (not made
    # metric-specific) since existing tests assert on those exact strings.
    reload_diff_key = bp_config["persistence_reload_diff_key"]
    reload_diff = block.get(reload_diff_key)
    if reload_diff is None or abs(float(reload_diff)) > RELOAD_DIFF_TOLERANCE:
        checks.append(
            CheckResult(
                "reload_fidelity_verified_at_run_time",
                CheckStatus.WARN,
                f"{reload_diff_key}={reload_diff!r} - the persistence notebook's own reload "
                "check did not record a near-zero diff (or the field is missing), so persistence "
                "fidelity was not confirmed at run time.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "reload_fidelity_verified_at_run_time",
                CheckStatus.PASS,
                f"{reload_diff_key}={reload_diff} (within tolerance {RELOAD_DIFF_TOLERANCE}).",
            )
        )

    metric_key = bp_config["persistence_metric_key"]
    metric_label = bp_config["metric_label"]
    gate_block = config_yaml.get(bp_config["champion_config_block"], {})
    gate_recorded_metric = gate_block.get(bp_config["champion_metric_key"])
    fresh_metric = block.get(metric_key)
    if gate_recorded_metric is None or fresh_metric is None:
        checks.append(
            CheckResult(
                "accuracy_consistent_with_gate_record",
                CheckStatus.WARN,
                f"Could not compare {metric_label} - gate_recorded={gate_recorded_metric!r}, "
                f"fresh_refit={fresh_metric!r} (one or both missing from config).",
            )
        )
    elif abs(float(gate_recorded_metric) - float(fresh_metric)) > ACCURACY_TOLERANCE:
        checks.append(
            CheckResult(
                "accuracy_consistent_with_gate_record",
                CheckStatus.FAIL,
                f"Persistence notebook's fresh-refit {metric_label} {fresh_metric} differs from "
                f"{bp_config['champion_config_block']}.{bp_config['champion_metric_key']}="
                f"{gate_recorded_metric} by more than {ACCURACY_TOLERANCE} - possible data or "
                "split drift between the gate run and the persistence run.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "accuracy_consistent_with_gate_record",
                CheckStatus.PASS,
                f"fresh_refit {metric_label}={fresh_metric} vs gate-recorded={gate_recorded_metric} "
                f"(diff <= {ACCURACY_TOLERANCE}).",
            )
        )

    model_artifact_ready = all(
        c.status in (CheckStatus.PASS, CheckStatus.WARN)
        for c in checks
        if c.name != "model_persistence_config_block" or c.status == CheckStatus.PASS
    ) and all(c.status != CheckStatus.FAIL for c in checks)
    return checks, bundle_path, model_artifact_ready


def _check_service_importable(bp_id: str, bp_config: dict, project_root: Path) -> list:
    checks = []
    src_dir = str(project_root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    module_path = bp_config["service_module"]
    try:
        if module_path in sys.modules:
            del sys.modules[module_path]
        module = importlib.import_module(module_path)
    except Exception as exc:  # a broken service import is a real, concrete FAIL - never swallowed
        checks.append(
            CheckResult(
                "service_module_imports_cleanly",
                CheckStatus.FAIL,
                f"`import {module_path}` raised {type(exc).__name__}: {exc}",
            )
        )
        return checks

    checks.append(
        CheckResult(
            "service_module_imports_cleanly",
            CheckStatus.PASS,
            f"`{module_path}` imported.",
        )
    )

    app = getattr(module, "app", None)
    if app is None:
        checks.append(
            CheckResult(
                "service_app_object_present",
                CheckStatus.FAIL,
                "Module has no `app` attribute.",
            )
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
    checks.append(
        CheckResult(
            "service_app_object_present",
            CheckStatus.PASS,
            "`app` is a FastAPI instance.",
        )
    )

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
                f"All of {REQUIRED_ROUTES} present.",
            )
        )
    return checks


def _check_dependencies_declared(project_root: Path) -> list:
    checks = []
    pyproject_deps = _parse_pyproject_dependencies(project_root / "pyproject.toml")
    requirements_lines = (project_root / "requirements.txt").read_text(encoding="utf-8").splitlines()

    for package in ("fastapi", "pydantic", "joblib"):
        declared = _requirement_declared(pyproject_deps, package)
        checks.append(
            CheckResult(
                f"pyproject_declares_{package}",
                CheckStatus.PASS if declared else CheckStatus.FAIL,
                f"{'Found' if declared else 'NOT found'} in pyproject.toml [project.dependencies].",
            )
        )

    httpx_declared = _requirement_declared(requirements_lines, "httpx")
    checks.append(
        CheckResult(
            "requirements_declares_httpx",
            CheckStatus.PASS if httpx_declared else CheckStatus.FAIL,
            f"{'Found' if httpx_declared else 'NOT found'} in requirements.txt (needed for "
            "fastapi.testclient.TestClient to run the service tests).",
        )
    )
    return checks


def _check_test_files_exist_and_pass(bp_config: dict, project_root: Path, run_tests: bool) -> list:
    checks = []
    missing = [t for t in bp_config["test_files"] if not (project_root / t).exists()]
    if missing:
        checks.append(
            CheckResult(
                "test_files_present",
                CheckStatus.FAIL,
                f"Missing test file(s): {missing}.",
            )
        )
        return checks
    checks.append(
        CheckResult(
            "test_files_present",
            CheckStatus.PASS,
            f"All of {bp_config['test_files']} present.",
        )
    )

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
        # No shell=True: args are a fixed list built from this module's own SUPPORTED_BPS
        # registry (never external/untrusted input), and sys.executable is the real
        # interpreter already running this process. Suppressed on the flagged line, below.
        result = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pytest", *bp_config["test_files"], "-q"],
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


def _check_containerization_and_ci(bp_config: dict, project_root: Path) -> list:
    """Steps 5 (Docker) and 6 (CI) haven't happened yet in this hardening pass - PENDING is the
    honest, expected result today, not a failure of Step 4's own scope."""
    checks = []
    dockerfile_candidates = [
        project_root
        / "src"
        / "services"
        / "docker"
        / f"{bp_config['service_module'].split('.')[-1]}"
        / "Dockerfile",
        project_root / "docker" / f"{bp_config['service_module'].split('.')[-1]}" / "Dockerfile",
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
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PASS,
                f"Found workflow(s) in {ci_dir}.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PENDING,
                "No .github/workflows/*.yml yet - Hardening Step 6 (CI wiring) has not started.",
            )
        )
    return checks


def assess_deployment_readiness(
    bp_id: str, project_root: Optional[Path] = None, run_tests: bool = True
) -> ReadinessVerdict:
    if bp_id not in SUPPORTED_BPS:
        raise ValueError(f"Unsupported bp_id {bp_id!r}. Supported: {sorted(SUPPORTED_BPS)}.")
    bp_config = SUPPORTED_BPS[bp_id]

    if project_root is None:
        project_root = resolve_project_root()

    config_path = project_root / "configs" / bp_config["config_file"]
    if not config_path.exists():
        checks = [
            CheckResult(
                "bp_config_exists",
                CheckStatus.FAIL,
                f"configs/{bp_config['config_file']} not found - no gates have run for {bp_id} yet.",
            )
        ]
        return ReadinessVerdict(
            bp_id=bp_id,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            checks=checks,
            model_artifact_ready=False,
            service_ready=False,
            fully_deployable=False,
        )

    with open(config_path, "r", encoding="utf-8") as f:
        config_yaml = yaml.safe_load(f) or {}

    checks: list = [CheckResult("bp_config_exists", CheckStatus.PASS, f"Found at {config_path}.")]

    persistence_checks, _bundle_path, model_artifact_ready = _check_model_persistence_block(
        project_root, bp_config, config_yaml
    )
    checks.extend(persistence_checks)

    service_checks = _check_service_importable(bp_id, bp_config, project_root)
    checks.extend(service_checks)

    dependency_checks = _check_dependencies_declared(project_root)
    checks.extend(dependency_checks)

    test_checks = _check_test_files_exist_and_pass(bp_config, project_root, run_tests)
    checks.extend(test_checks)

    container_ci_checks = _check_containerization_and_ci(bp_config, project_root)
    checks.extend(container_ci_checks)

    service_ready = (
        model_artifact_ready
        and all(c.status == CheckStatus.PASS for c in service_checks)
        and all(c.status == CheckStatus.PASS for c in dependency_checks)
        and all(c.status in (CheckStatus.PASS, CheckStatus.PENDING) for c in test_checks)
        and not any(c.status == CheckStatus.FAIL for c in test_checks)
    )
    fully_deployable = service_ready and all(c.status == CheckStatus.PASS for c in container_ci_checks)

    return ReadinessVerdict(
        bp_id=bp_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        model_artifact_ready=model_artifact_ready,
        service_ready=service_ready,
        fully_deployable=fully_deployable,
    )


def _write_report(verdict: ReadinessVerdict, project_root: Path, bp_config: dict) -> tuple:
    import json

    out_dir = project_root / "reports" / bp_config["folder"]
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "deployment_readiness_verdict.json"
    md_path = out_dir / "deployment_readiness_verdict.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verdict.to_dict(), f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(verdict.to_markdown())
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer360 Navigator deployment-readiness verdict.")
    parser.add_argument("--bp", action="append", choices=sorted(SUPPORTED_BPS), required=True)
    parser.add_argument("--no-run-tests", action="store_true", help="Skip executing the pytest suite.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON+MD under reports/<bp>/.")
    args = parser.parse_args()

    project_root = resolve_project_root()
    overall_ok = True
    for bp_id in args.bp:
        verdict = assess_deployment_readiness(bp_id, project_root, run_tests=not args.no_run_tests)
        print(verdict.to_markdown())
        if args.write_report:
            json_path, md_path = _write_report(verdict, project_root, SUPPORTED_BPS[bp_id])
            print(f"[SAVED] {json_path}")
            print(f"[SAVED] {md_path}")
        if not verdict.service_ready:
            overall_ok = False
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
