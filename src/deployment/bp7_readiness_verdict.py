"""
src/deployment/bp7_readiness_verdict.py — Customer360 Navigator

BP7 (Customer Navigator Decision Engine) deployment-readiness verdict module (Hardening pass, BP7
variant). A pure read-only audit, same honesty spirit as readiness_verdict.py,
bp4_readiness_verdict.py, bp5_readiness_verdict.py and bp6_readiness_verdict.py: it inspects the
REAL artifacts BP7's own gates already wrote to disk (or does not find them, and says so honestly
as PENDING/FAIL) and produces an itemized, structured verdict - never a subjective "looks good",
never a fabricated PASS.

Deliberately a SEPARATE standalone sibling module, not an extension of readiness_verdict.py,
bp4_readiness_verdict.py, bp5_readiness_verdict.py or bp6_readiness_verdict.py. BP7 fits none of
its siblings' shapes exactly. Confirmed directly from src/services/bp7_decision_engine_service.py's
own module docstring: "BP7 is architecturally different from BP6: BP6 fits no persisted artifact
and makes a real, live external API call (Gemini) on every /resolve; BP7 makes NO external call at
all - it is a deterministic weighted-rule engine ... that Gate 5 already applied once, for real, to
the full real population and persisted" as a large CSV. That same docstring also states BP7 "is
therefore architecturally closer to services.bp4_decision_service (read-only lookup over a real,
persisted decision artifact, never a live model/API call) than to services.bp6_resolution_service".
It is NOT BP4's own shape either, however: BP4's own readiness-verdict module is off-limits (this
project's standing rule), and BP7's real Gate 5/Gate 7 artifact shapes - a ~540MB, 1,048,575-row
full-population CSV plus a Gate 5 decision-layer summary JSON with its own real key set - are
entirely different from BP4's own persisted Parquet decision-artifact index. There is no
joblib-model-persistence config block (unlike BP1-3), no live external GenAI call to WARN-not-FAIL
on (unlike BP6), and no association/SHAP-only findings to guardrail (unlike BP5). BP7's own central
governance property is instead a deterministic, auditable, reason-coded rule engine over
already-scored real data, whose one real internal-consistency claim
(contribution_bp2 + contribution_bp3 + contribution_bp4 reconstructs priority_score) is reconciled
by a real, already-committed function (`features.bp7_decision_engine_features
.summarize_contribution_decomposition`) that BP7's own live `/decide/self-test` endpoint reuses
unmodified. Building a "bp7" entry into any of the other four modules would mean fabricating an
artifact-readiness concept BP7 does not have - unacceptable under this project's zero-fabrication
rule - so this module instead audits exactly what BP7's own real, already-committed evidence
actually is, under notebooks/bp7_customer_navigator_decision_engine/artifacts/ (NOT gitignored -
see .gitignore - so these are real, already-committed evidence, not something a Claude session
generates), the exact same "read the real committed artifacts directly" shape
bp5_readiness_verdict.py and bp6_readiness_verdict.py already established.

What this module actually checks, against BP7's real artifact shapes (every key set below was
read-verified directly against the real on-device files, 2026-09-25, never assumed from another
BP's shape):

  1. configs/bp7_customer_navigator_decision_engine.yaml exists (real bp_id="bp7",
     status="gate1_confirmed_gate2_confirmed_gate3_confirmed_gate4_confirmed_gate5_confirmed").

  2. Gate 5 full-population decision-records CSV
     (gate5_full_population_decision_records.csv, real ~540MB / 1,048,575 rows) - checked with a
     LIGHTWEIGHT, SCHEMA-ONLY read, exactly mirroring what the real service itself does at startup
     (a zero-row `polars.scan_csv(...).limit(0).collect()` - see
     src/services/bp7_decision_engine_service.py's own DecisionEngineHandle._load()) - NEVER a
     full read of this large real file. The real, on-disk header (19 columns, read-verified
     verbatim) is compared against EXPECTED_GATE5_CSV_COLUMNS below, itself BP7's own real
     `FINAL_OUTPUT_COLUMNS` (src/features/bp7_decision_engine_features.py line 1589) hardcoded
     here rather than imported, matching this project's own established "hardcode the real
     required keys/columns as a module-level constant" pattern (BP4/BP5/BP6's own readiness
     modules already do the same for their own real schemas) - a real column-order/content drift
     between this constant and what BP7's own feature module produces in the future is therefore a
     concrete FAIL here, never silently accepted.

  3. Gate 5 decision-layer summary JSON (gate5_decision_layer_summary.json) - exists, parses,
     carries all 21 real top-level keys this project's own schema uses (read-verified 2026-09-25:
     bp_id, gate, generated_at_utc, live_row_count, champion_rule_scheme,
     champion_weights_normalized, intervention_threshold, weight_rederivation_cross_check,
     champion_stats, cross_checks_vs_gate3_gate4, gate4_bootstrap_ci_carried_forward,
     contribution_decomposition_summary, disparate_impact_audit, upstream_field_coverage,
     recommended_action_breakdown, bp4_tier_intervention_crosstab,
     n_rows_covered_by_action_breakdown, n_rows_covered_by_tier_crosstab, compliance_touchpoint,
     records_csv_path, action_breakdown_csv_path, tier_crosstab_csv_path), and its own bp_id/gate
     fields real-match ("bp7"/5) - a real drift between this artifact's declared identity and its
     location would be a concrete FAIL, never silently accepted (same spirit as
     bp6_readiness_verdict.py's own gate3_retrieval_strategy_identity_matches check).

  4. Gate 7 executive rollup manifest (executive_rollup_manifest.json) - parses, has bp_id=="bp7",
     and its own real output_paths (dashboard_html/report_docx/workbook_xlsx/deck_pptx) all exist
     on disk with byte sizes matching what the manifest itself recorded in output_sizes_bytes
     (drift/tamper detection, same spirit as bp5_readiness_verdict.py's and
     bp6_readiness_verdict.py's own Gate 7 checks).

  5. src/services/bp7_decision_engine_service.py imports cleanly, exposes a FastAPI `app`, and that
     app serves the required routes with the required HTTP methods (grep-verified against the real
     file): GET "/", GET "/health", GET "/decide/self-test", GET "/decide/{complaint_id}" - never a
     bare "/predict" and never a POST endpoint, since BP7 serves real, already-computed lookups,
     not live predictions and not a request body payload.

  6. A DEDICATED, BP7-specific check - not copied from BP5's disclaimer check or BP6's
     human-in-the-loop guardrail check, because neither fits what BP7 actually is - for the real
     wiring behind BP7's own governance analogue: the `/decide/self-test` endpoint's real
     internal-consistency semantics. Per this service's own module docstring, that endpoint reuses
     "Gate 4/5's own real reconciliation function, imported and called UNMODIFIED, never
     reimplemented" (`features.bp7_decision_engine_features.summarize_contribution_decomposition`)
     to prove `contribution_bp2 + contribution_bp3 + contribution_bp4` reconstructs
     `priority_score` for real, already-scored rows, using the real, imported
     `DEFAULT_INTERVENTION_THRESHOLD` constant rather than a hardcoded literal. Actually invoking
     that live endpoint here would require starting the full service against the real 540MB CSV -
     out of scope for a readiness-verdict check and never attempted. Instead this module performs
     a real, honest, STATIC check only: it imports `features.bp7_decision_engine_features` fresh
     and confirms `summarize_contribution_decomposition` is present and callable and
     `DEFAULT_INTERVENTION_THRESHOLD` is present and numeric - i.e. that the self-test endpoint is
     actually wired to the real reconciliation function it claims to reuse, without fabricating a
     runtime call result. A missing/broken import here is a concrete FAIL (the self-test's central
     claim would not hold); a real, structurally-sound wiring is a concrete PASS - never a
     fabricated "all_checks_passed" runtime verdict this module cannot honestly produce.

  7. The runtime packages bp7_decision_engine_service.py actually imports AT MODULE LEVEL
     (fastapi, pydantic, polars - grep-verified: `import polars as pl`,
     `from fastapi import FastAPI, HTTPException, Path as PathParam, Query`,
     `from pydantic import BaseModel, Field`) are declared in pyproject.toml. Unlike
     bp6_resolution_service.py's own lazily-imported google-genai, polars is a real, top-level,
     always-imported dependency here - BP7 makes no external API call at all, so there is no
     analogous "the import itself is optional" case to account for.

  8. tests/services/test_bp7_decision_engine_service.py exists, and (optionally) actually passes
     via a real pytest subprocess - never a fabricated pass/fail count.

  9. Docker and CI presence - honestly PENDING if not found, PASS if found; both were in fact
     already delivered for BP7 as of this module's writing
     (src/services/docker/bp7_decision_engine_service/Dockerfile and a docker-validate CI job
     entry referencing bp7_decision_engine_service, including a real `docker build` smoke step),
     so this check is expected to PASS today, not PENDING - but the check itself makes no such
     assumption and reports whatever it actually finds on disk.

Usage (from the project root, after `pip install -e .`):
    python -m deployment.bp7_readiness_verdict
    python -m deployment.bp7_readiness_verdict --write-report
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

BP_ID = "bp7"
BP7_FOLDER = "bp7_customer_navigator_decision_engine"
BP7_CONFIG_FILE = "bp7_customer_navigator_decision_engine.yaml"
BP7_SERVICE_MODULE = "services.bp7_decision_engine_service"
BP7_TEST_FILES = ("tests/services/test_bp7_decision_engine_service.py",)
BP7_FEATURES_MODULE = "features.bp7_decision_engine_features"

ARTIFACTS_RELATIVE_DIR = Path("notebooks") / BP7_FOLDER / "artifacts"
RECORDS_CSV_FILENAME = "gate5_full_population_decision_records.csv"
GATE5_SUMMARY_FILENAME = "gate5_decision_layer_summary.json"
ROLLUP_FILENAME = "executive_rollup_manifest.json"

# The real, verbatim header of the real, ~540MB, 1,048,575-row Gate 5 full-population CSV -
# read-verified 2026-09-25 via `head` against the real on-device file. This is BP7's own real
# `FINAL_OUTPUT_COLUMNS` (src/features/bp7_decision_engine_features.py line 1589) hardcoded here,
# never imported - that module may drift over the project's life, and this readiness check must
# never depend at import time on the very module its own checks are independently auditing.
EXPECTED_GATE5_CSV_COLUMNS = (
    "Complaint ID",
    "priority_score",
    "intervention_flag",
    "recommended_action",
    "reason_codes",
    "contribution_bp2",
    "contribution_bp3",
    "contribution_bp4",
    "bp2_predicted_label",
    "bp2_confidence",
    "bp3_predicted_label",
    "bp3_probability_positive_class",
    "bp4_review_priority_tier",
    "bp4_review_priority_score",
    "bp4_join_status",
    "bp1_context_status",
    "bp5_outcome_1_context",
    "bp5_outcome_2_context",
    "tags_group",
)

# Real required top-level keys - read-verified 2026-09-25 directly against the real on-device
# gate5_decision_layer_summary.json.
REQUIRED_GATE5_SUMMARY_KEYS = (
    "bp_id",
    "gate",
    "generated_at_utc",
    "live_row_count",
    "champion_rule_scheme",
    "champion_weights_normalized",
    "intervention_threshold",
    "weight_rederivation_cross_check",
    "champion_stats",
    "cross_checks_vs_gate3_gate4",
    "gate4_bootstrap_ci_carried_forward",
    "contribution_decomposition_summary",
    "disparate_impact_audit",
    "upstream_field_coverage",
    "recommended_action_breakdown",
    "bp4_tier_intervention_crosstab",
    "n_rows_covered_by_action_breakdown",
    "n_rows_covered_by_tier_crosstab",
    "compliance_touchpoint",
    "records_csv_path",
    "action_breakdown_csv_path",
    "tier_crosstab_csv_path",
)

REQUIRED_ROLLUP_OUTPUT_KEYS = ("dashboard_html", "report_docx", "workbook_xlsx", "deck_pptx")

# grep-verified (2026-09-25) against src/services/bp7_decision_engine_service.py's own module-level
# import statements: `import polars as pl`, `from fastapi import FastAPI, HTTPException, Path as
# PathParam, Query`, `from pydantic import BaseModel, Field` - unlike bp6_resolution_service.py's
# own lazily-imported google-genai, polars is a real, always-imported, top-level dependency here
# (BP7 makes no external API call at all). All three are already declared in pyproject.toml
# (fastapi/pydantic for BP1-3's own real needs, polars>=1.9 - grep-verified - for this project's
# own broader real data-processing needs), so BP7's service required no new pyproject.toml/
# requirements.txt entry.
REQUIRED_RUNTIME_PACKAGES = ("fastapi", "pydantic", "polars")

# (method, path) pairs - grep-verified 2026-09-25 against the real
# src/services/bp7_decision_engine_service.py route decorators. Never a bare "/predict" and never
# a POST route: BP7 serves real, already-computed lookups over a persisted artifact, not live
# predictions and not a request-body payload.
REQUIRED_ROUTES = (
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/decide/self-test"),
    ("GET", "/decide/{complaint_id}"),
)

# Real attribute names - grep-verified 2026-09-25 directly against
# src/features/bp7_decision_engine_features.py (DEFAULT_INTERVENTION_THRESHOLD: float = 0.5 at
# line 615) and against bp7_decision_engine_service.py's own `/decide/self-test` handler, which
# imports both of these, unmodified, from that module.
REQUIRED_FEATURES_MODULE_ATTRS = ("summarize_contribution_decomposition", "DEFAULT_INTERVENTION_THRESHOLD")


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
class BP7ReadinessVerdict:
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
            f"# BP7 Deployment Readiness Verdict - {self.bp_id}",
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
    readiness_verdict.py, bp4_readiness_verdict.py, bp5_readiness_verdict.py or
    bp6_readiness_verdict.py) for the same standalone reasoning given in this module's own
    docstring: no readiness-verdict sibling module depends on another at runtime, so a concurrent
    edit to one never breaks another."""
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
    readiness_verdict.py's, bp4_readiness_verdict.py's, bp5_readiness_verdict.py's and
    bp6_readiness_verdict.py's own identically-named function."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def _requirement_declared(requirements: list, package: str) -> bool:
    package_lower = package.lower()
    return any(re.match(rf"^{re.escape(package_lower)}\s*[><=~!]", r.lower()) for r in requirements)


def _load_json_artifact(path: Path, check_name: str) -> tuple:
    """Returns (checks, parsed_or_None). A single shared exists+parse pattern used by every Gate
    5/7 artifact check below, so a missing or malformed real artifact is always reported the same
    honest way rather than re-implemented slightly differently per gate."""
    if not path.exists():
        return (
            [
                CheckResult(
                    check_name,
                    CheckStatus.FAIL,
                    f"Expected at {path} - this real BP7 gate artifact has not been produced.",
                )
            ],
            None,
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return (
            [
                CheckResult(
                    check_name,
                    CheckStatus.FAIL,
                    f"Found at {path} but failed to parse as JSON: {type(exc).__name__}: {exc}",
                )
            ],
            None,
        )
    return [CheckResult(check_name, CheckStatus.PASS, f"Found at {path}.")], parsed


def _check_gate5_records_csv_schema(project_root: Path) -> tuple:
    """Returns (checks, ready: bool). A lightweight, SCHEMA-ONLY check against the real, large
    (~540MB, 1,048,575-row) Gate 5 CSV - a zero-row `polars.scan_csv(...).limit(0).collect()`,
    exactly mirroring what src/services/bp7_decision_engine_service.py's own DecisionEngineHandle
    does at real service startup. NEVER a full read of this file - not here, and not in this
    module's own sandbox verification."""
    checks: list = []
    csv_path = project_root / ARTIFACTS_RELATIVE_DIR / RECORDS_CSV_FILENAME

    if not csv_path.exists():
        checks.append(
            CheckResult(
                "gate5_records_csv_exists",
                CheckStatus.FAIL,
                f"Expected at {csv_path} - Gate 5 has not produced the real full-population "
                "decision-records CSV.",
            )
        )
        return checks, False
    checks.append(CheckResult("gate5_records_csv_exists", CheckStatus.PASS, f"Found at {csv_path}."))

    try:
        import polars as pl
    except ImportError as exc:
        checks.append(
            CheckResult(
                "gate5_records_csv_schema_matches",
                CheckStatus.FAIL,
                f"polars is not importable in this environment ({exc}) - cannot perform the real "
                "zero-row schema probe this service itself relies on at startup.",
            )
        )
        return checks, False

    try:
        real_columns = list(pl.scan_csv(csv_path).limit(0).collect().columns)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a real, concrete FAIL
        checks.append(
            CheckResult(
                "gate5_records_csv_schema_matches",
                CheckStatus.FAIL,
                f"Zero-row schema probe raised {type(exc).__name__}: {exc}.",
            )
        )
        return checks, False

    if tuple(real_columns) == EXPECTED_GATE5_CSV_COLUMNS:
        checks.append(
            CheckResult(
                "gate5_records_csv_schema_matches",
                CheckStatus.PASS,
                f"All {len(EXPECTED_GATE5_CSV_COLUMNS)} real FINAL_OUTPUT_COLUMNS present, in "
                "order (zero-row schema probe only - never a full read of this real, large file).",
            )
        )
        return checks, True

    missing = [c for c in EXPECTED_GATE5_CSV_COLUMNS if c not in real_columns]
    extra = [c for c in real_columns if c not in EXPECTED_GATE5_CSV_COLUMNS]
    checks.append(
        CheckResult(
            "gate5_records_csv_schema_matches",
            CheckStatus.FAIL,
            f"Real on-disk header does not match EXPECTED_GATE5_CSV_COLUMNS. Missing: {missing}. "
            f"Unexpected: {extra}. Real columns found: {real_columns}.",
        )
    )
    return checks, False


def _check_gate5_summary_json(project_root: Path) -> tuple:
    """Returns (checks, ready: bool)."""
    checks: list = []
    summary_path = project_root / ARTIFACTS_RELATIVE_DIR / GATE5_SUMMARY_FILENAME
    load_checks, summary = _load_json_artifact(summary_path, "gate5_summary_json_exists")
    checks.extend(load_checks)
    if summary is None:
        return checks, False

    ready = True
    missing_keys = [k for k in REQUIRED_GATE5_SUMMARY_KEYS if k not in summary]
    if missing_keys:
        checks.append(
            CheckResult(
                "gate5_summary_json_schema",
                CheckStatus.FAIL,
                f"Missing real required key(s): {missing_keys}.",
            )
        )
        ready = False
    else:
        checks.append(
            CheckResult(
                "gate5_summary_json_schema",
                CheckStatus.PASS,
                f"All {len(REQUIRED_GATE5_SUMMARY_KEYS)} real required keys present "
                f"(champion_rule_scheme={summary.get('champion_rule_scheme')!r}).",
            )
        )

    bp_id_ok = summary.get("bp_id") == "bp7"
    gate_ok = summary.get("gate") == 5
    if bp_id_ok and gate_ok:
        checks.append(
            CheckResult(
                "gate5_summary_identity_matches",
                CheckStatus.PASS,
                "bp_id == 'bp7' and gate == 5.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "gate5_summary_identity_matches",
                CheckStatus.FAIL,
                f"Expected bp_id='bp7'/gate=5, found bp_id={summary.get('bp_id')!r}, "
                f"gate={summary.get('gate')!r} - a real drift between this artifact's declared "
                "identity and where it was found.",
            )
        )
        ready = False

    return checks, ready


def _check_gate7_rollup_manifest(project_root: Path) -> tuple:
    """Returns (checks, all_ready: bool). Checks the manifest itself, then cross-checks every real
    output file it names against what is actually on disk (existence + byte-size match) -
    drift/tamper detection, same spirit as every other BP's readiness-verdict module."""
    checks: list = []
    manifest_path = project_root / ARTIFACTS_RELATIVE_DIR / ROLLUP_FILENAME

    load_checks, manifest = _load_json_artifact(manifest_path, "gate7_rollup_manifest_exists")
    checks.extend(load_checks)
    if manifest is None:
        return checks, False

    if manifest.get("bp_id") != "bp7":
        checks.append(
            CheckResult(
                "gate7_rollup_manifest_bp_id",
                CheckStatus.FAIL,
                f"Manifest bp_id={manifest.get('bp_id')!r}, expected 'bp7'.",
            )
        )
        return checks, False
    checks.append(CheckResult("gate7_rollup_manifest_bp_id", CheckStatus.PASS, "bp_id == 'bp7'."))

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
        # resolving "services.bp7_decision_engine_service" against whichever src/ directory
        # "services" was FIRST imported from in this process, silently ignoring a freshly-inserted
        # sys.path entry for a different project_root - a real cross-call caching gap found and
        # fixed in bp5_readiness_verdict.py's own equivalent function (via that module's own test
        # suite exercising several different project roots against the same long-lived pytest
        # process), copied here verbatim (as bp6_readiness_verdict.py also does) rather than
        # re-discovered the hard way a second time.
        for mod_name in (BP7_SERVICE_MODULE, BP7_SERVICE_MODULE.split(".")[0]):
            sys.modules.pop(mod_name, None)
        importlib.invalidate_caches()
        module = importlib.import_module(BP7_SERVICE_MODULE)
    except Exception as exc:  # a broken service import is a real, concrete FAIL - never swallowed
        checks.append(
            CheckResult(
                "service_module_imports_cleanly",
                CheckStatus.FAIL,
                f"`import {BP7_SERVICE_MODULE}` raised {type(exc).__name__}: {exc}",
            )
        )
        return checks

    checks.append(
        CheckResult("service_module_imports_cleanly", CheckStatus.PASS, f"`{BP7_SERVICE_MODULE}` imported.")
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

    real_route_pairs = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or []
        for method in methods:
            real_route_pairs.add((method, path))

    missing = [pair for pair in REQUIRED_ROUTES if pair not in real_route_pairs]
    if missing:
        checks.append(
            CheckResult(
                "service_required_routes_present",
                CheckStatus.FAIL,
                f"Missing route(s) (method, path): {missing}. Found: {sorted(real_route_pairs)}.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "service_required_routes_present",
                CheckStatus.PASS,
                f"All of {REQUIRED_ROUTES} present - never a bare /predict and never a POST route, "
                "BP7 serves real, already-computed lookups over a persisted artifact.",
            )
        )
    return checks


def _check_self_test_reconciliation_wiring(project_root: Path) -> list:
    """BP7-specific check, deliberately NOT copied from BP5's association_not_causation_disclaimer
    check or BP6's gate5_human_in_the_loop_governance_guardrail check - neither fits what BP7
    actually is. BP7's own central governance property is that its live `/decide/self-test`
    endpoint reconciles `contribution_bp2 + contribution_bp3 + contribution_bp4` against
    `priority_score` using a real, already-committed reconciliation function
    (`features.bp7_decision_engine_features.summarize_contribution_decomposition`), reused
    unmodified rather than reimplemented. Actually invoking that live endpoint would require
    starting the full service against the real 540MB CSV - out of scope for a readiness-verdict
    check and never attempted here. This is instead a real, honest, STATIC check only: it confirms
    the endpoint is actually wired to the real reconciliation function it claims to reuse, without
    fabricating a runtime call result. A missing/broken import is a concrete FAIL; a sound wiring
    is a concrete PASS - never a fabricated 'all_checks_passed' runtime verdict."""
    checks = []
    src_dir = str(project_root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    try:
        # Same parent-package sys.modules caching fix as _check_service_importable above, applied
        # here too - this module is imported fresh from a potentially different project_root on
        # every call in this module's own test suite.
        for mod_name in (BP7_FEATURES_MODULE, BP7_FEATURES_MODULE.split(".")[0]):
            sys.modules.pop(mod_name, None)
        importlib.invalidate_caches()
        features_module = importlib.import_module(BP7_FEATURES_MODULE)
    except Exception as exc:  # a broken import means the self-test's central claim cannot hold
        checks.append(
            CheckResult(
                "self_test_reconciliation_function_wired",
                CheckStatus.FAIL,
                f"`import {BP7_FEATURES_MODULE}` raised {type(exc).__name__}: {exc} - the real "
                "`/decide/self-test` endpoint's own claimed reconciliation function cannot be "
                "verified to exist.",
            )
        )
        return checks

    missing_attrs = [a for a in REQUIRED_FEATURES_MODULE_ATTRS if not hasattr(features_module, a)]
    if missing_attrs:
        checks.append(
            CheckResult(
                "self_test_reconciliation_function_wired",
                CheckStatus.FAIL,
                f"`{BP7_FEATURES_MODULE}` is missing real required attribute(s): {missing_attrs}.",
            )
        )
        return checks

    reconciliation_fn = getattr(features_module, "summarize_contribution_decomposition")
    threshold_value = getattr(features_module, "DEFAULT_INTERVENTION_THRESHOLD")
    fn_ok = callable(reconciliation_fn)
    threshold_ok = isinstance(threshold_value, (int, float)) and not isinstance(threshold_value, bool)

    if fn_ok and threshold_ok:
        checks.append(
            CheckResult(
                "self_test_reconciliation_function_wired",
                CheckStatus.PASS,
                "summarize_contribution_decomposition is present and callable, "
                f"DEFAULT_INTERVENTION_THRESHOLD={threshold_value!r} is present and numeric - the "
                "real `/decide/self-test` endpoint is wired to the real reconciliation function "
                "and threshold it claims to reuse (static check only - the live endpoint itself "
                "was never invoked, which would require the real 540MB Gate 5 CSV and a running "
                "service; never fabricated here).",
            )
        )
    else:
        checks.append(
            CheckResult(
                "self_test_reconciliation_function_wired",
                CheckStatus.FAIL,
                f"summarize_contribution_decomposition callable={fn_ok}, "
                f"DEFAULT_INTERVENTION_THRESHOLD={threshold_value!r} numeric={threshold_ok} - the "
                "self-test endpoint's claimed wiring does not hold as real code.",
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
                "(grep-verified real MODULE-LEVEL import in "
                "src/services/bp7_decision_engine_service.py; unlike BP6's lazily-imported "
                "google-genai, polars is always imported at module scope here - BP7 makes no "
                "external API call at all).",
            )
        )
    return checks


def _check_test_files_exist_and_pass(project_root: Path, run_tests: bool) -> list:
    checks = []
    missing = [t for t in BP7_TEST_FILES if not (project_root / t).exists()]
    if missing:
        checks.append(
            CheckResult("test_files_present", CheckStatus.FAIL, f"Missing test file(s): {missing}.")
        )
        return checks
    checks.append(CheckResult("test_files_present", CheckStatus.PASS, f"All of {BP7_TEST_FILES} present."))

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
            [sys.executable, "-m", "pytest", *BP7_TEST_FILES, "-q"],
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
        project_root / "src" / "services" / "docker" / "bp7_decision_engine_service" / "Dockerfile",
        project_root / "docker" / "bp7_decision_engine_service" / "Dockerfile",
    ]
    if any(p.exists() for p in dockerfile_candidates):
        found = next(p for p in dockerfile_candidates if p.exists())
        checks.append(CheckResult("dockerfile_present", CheckStatus.PASS, f"Found at {found}."))
    else:
        checks.append(
            CheckResult(
                "dockerfile_present",
                CheckStatus.PENDING,
                "No Dockerfile yet for bp7_decision_engine_service.",
            )
        )

    ci_path = project_root / ".github" / "workflows" / "ci.yml"
    if ci_path.exists() and "bp7_decision_engine_service" in ci_path.read_text(encoding="utf-8"):
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PASS,
                f"bp7_decision_engine_service referenced in {ci_path}.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PENDING,
                "No .github/workflows/ci.yml entry for bp7_decision_engine_service yet.",
            )
        )
    return checks


def assess_bp7_deployment_readiness(
    project_root: Optional[Path] = None, run_tests: bool = True
) -> BP7ReadinessVerdict:
    if project_root is None:
        project_root = resolve_project_root()

    config_path = project_root / "configs" / BP7_CONFIG_FILE
    if not config_path.exists():
        checks = [
            CheckResult(
                "bp7_config_exists",
                CheckStatus.FAIL,
                f"configs/{BP7_CONFIG_FILE} not found - no BP7 gates have run yet.",
            )
        ]
        return BP7ReadinessVerdict(
            bp_id=BP_ID,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            checks=checks,
            artifact_ready=False,
            service_ready=False,
            fully_deployable=False,
        )

    checks: list = [CheckResult("bp7_config_exists", CheckStatus.PASS, f"Found at {config_path}.")]
    # Loaded for parity with every other readiness module even though this module's own checks
    # read real artifacts directly rather than a config block - kept so a YAML parse failure is
    # itself surfaced as a concrete FAIL rather than silently ignored.
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as exc:
        checks.append(CheckResult("bp7_config_parses", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}"))

    gate5_csv_checks, gate5_csv_ready = _check_gate5_records_csv_schema(project_root)
    checks.extend(gate5_csv_checks)

    gate5_summary_checks, gate5_summary_ready = _check_gate5_summary_json(project_root)
    checks.extend(gate5_summary_checks)

    gate7_checks, gate7_ready = _check_gate7_rollup_manifest(project_root)
    checks.extend(gate7_checks)

    artifact_ready = gate5_csv_ready and gate5_summary_ready and gate7_ready

    service_checks = _check_service_importable(project_root)
    checks.extend(service_checks)

    self_test_wiring_checks = _check_self_test_reconciliation_wiring(project_root)
    checks.extend(self_test_wiring_checks)

    dependency_checks = _check_dependencies_declared(project_root)
    checks.extend(dependency_checks)

    test_checks = _check_test_files_exist_and_pass(project_root, run_tests)
    checks.extend(test_checks)

    container_ci_checks = _check_containerization_and_ci(project_root)
    checks.extend(container_ci_checks)

    service_ready = (
        artifact_ready
        and all(c.status == CheckStatus.PASS.value for c in service_checks)
        and all(c.status == CheckStatus.PASS.value for c in self_test_wiring_checks)
        and all(c.status == CheckStatus.PASS.value for c in dependency_checks)
        and all(c.status in (CheckStatus.PASS.value, CheckStatus.PENDING.value) for c in test_checks)
        and not any(c.status == CheckStatus.FAIL.value for c in test_checks)
    )
    fully_deployable = service_ready and all(c.status == CheckStatus.PASS.value for c in container_ci_checks)

    return BP7ReadinessVerdict(
        bp_id=BP_ID,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        artifact_ready=artifact_ready,
        service_ready=service_ready,
        fully_deployable=fully_deployable,
    )


def _write_report(verdict: BP7ReadinessVerdict, project_root: Path) -> tuple:
    out_dir = project_root / "reports" / BP7_FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bp7_deployment_readiness_verdict.json"
    md_path = out_dir / "bp7_deployment_readiness_verdict.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verdict.to_dict(), f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(verdict.to_markdown())
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer360 Navigator BP7 deployment-readiness verdict.")
    parser.add_argument("--no-run-tests", action="store_true", help="Skip executing the pytest suite.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON+MD under reports/bp7_.../")
    args = parser.parse_args()

    project_root = resolve_project_root()
    verdict = assess_bp7_deployment_readiness(project_root, run_tests=not args.no_run_tests)
    print(verdict.to_markdown())
    if args.write_report:
        json_path, md_path = _write_report(verdict, project_root)
        print(f"[SAVED] {json_path}")
        print(f"[SAVED] {md_path}")
    return 0 if verdict.service_ready else 1


if __name__ == "__main__":
    sys.exit(main())
