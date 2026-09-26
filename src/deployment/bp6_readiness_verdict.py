"""
src/deployment/bp6_readiness_verdict.py — Customer360 Navigator

BP6 (GenAI Resolution Assistant) deployment-readiness verdict module (Hardening pass, BP6
variant). A pure read-only audit, same honesty spirit as readiness_verdict.py,
bp4_readiness_verdict.py and bp5_readiness_verdict.py: it inspects the REAL artifacts BP6's own
gates already wrote to disk (or does not find them, and says so honestly as PENDING/FAIL) and
produces an itemized, structured verdict - never a subjective "looks good", never a fabricated
PASS.

Deliberately a SEPARATE standalone sibling module, not an extension of readiness_verdict.py,
bp4_readiness_verdict.py or bp5_readiness_verdict.py. BP6 fits no deployable supervised classifier
at all - unlike BP1/2/3 (joblib champion bundle), unlike BP4 (a persisted Parquet decision-artifact
index), and unlike BP5 (a Gate 3 logistic regression that at least exists, just never as a decision
boundary). Confirmed directly from src/services/bp6_resolution_service.py's own module docstring:
BP6 "fits no persisted model bundle and indexes no static artifact - every real `/resolve` call
performs a real, live, grounded-generation round trip through Google's Gemini API
(`src/genai/bp6_grounded_generation.py`), exactly reproducing Gate 5's own real pipeline, request
by request." There is therefore no model_persistence-style config block, no champion
accuracy/PR-AUC to drift-check, and no Parquet index either. BP6 is instead a retrieval +
grounded-generation governance layer - Gate 2 (PII screening + evidence registry), Gate 3
(retrieval strategy benchmark), and Gate 5 (the real, one-shot, live Gemini call and its resulting
PENDING_HUMAN_REVIEW recommendation artifact) are BP6's own real deployable-readiness evidence, not
a model. Building a "bp6" entry into any of the other three modules would mean fabricating an
artifact-readiness concept BP6 does not have - unacceptable under this project's zero-fabrication
rule - so this module instead audits exactly what BP6's own real, already-committed evidence
actually is, under notebooks/bp6_genai_resolution_assistant/artifacts/ (NOT gitignored - see
.gitignore - so these are real, already-committed evidence, not something a Claude session
generates), the exact same "read the real committed artifacts directly" shape
bp5_readiness_verdict.py itself already established.

What this module actually checks, against BP6's real artifact shapes (every key set below was
read-verified directly against the real on-device files, 2026-09-25, never assumed from another
BP's shape):

  1. configs/bp6_genai_resolution_assistant.yaml exists. Its own real content documents (and this
     module's docstring repeats verbatim) why BP6 has no target_definition/leakage_rules block at
     all: "BP6 deliberately does NOT reuse BP1-4's target_definition/leakage_rules schema ... BP6
     has no supervised target and no training split at any gate - it is a retrieval-and-grounded-
     generation governance layer. genai_governance_policy and upstream_dependency_status replace
     those two keys."

  2. Gate 2 (PII Screening & Evidence Registry) - THREE real artifacts, checked separately so a
     problem with one is never masked by another's PASS:
       a. gate2_pii_screening_report.json exists, parses, and carries its real required keys
          (n_rows_screened, n_rows_flagged, pct_rows_flagged, category_counts,
          pii_categories_checked).
       b. gate2_evidence_source_registry.json exists, parses, and carries its real required keys
          (generated_at_utc, upstream_bps) - upstream_bps itself real-verified to be a dict keyed
          by the five real upstream BP ids (bp1..bp5), each with a real per-BP artifact inventory
          BP6's own retrieval layer draws citations from.
       c. gate2_pii_screened_narrative_text.csv exists on disk (existence only - it is the real,
          already-PII-screened audit-trail CSV that
          src/services/bp6_resolution_service.py's own ResolutionAssistantHandle reads directly at
          service startup; without it the service starts but serves 503 on every generation
          endpoint, exactly like a missing joblib bundle would for BP1-3).

  3. Gate 3 (Retrieval Strategy Benchmark) - gate3_retrieval_strategy_inventory_entry.json exists,
     parses, carries its real required keys (bp_id, gate, compliance_touchpoint, champion_strategy,
     champion_coverage, runner_up_strategy, runner_up_coverage, candidates_evaluated,
     candidates_failed, strategy_a_detail, strategy_b_detail, generated_at_utc), and its own
     bp_id/gate fields real-match ("bp6"/3) - a real drift between this artifact's declared
     identity and its filename/location would be a concrete FAIL, never silently accepted (same
     spirit as bp5_readiness_verdict.py's outcome_field-vs-filename check, adapted to BP6's single-
     artifact Gate 3 shape rather than BP5's two-outcome shape).

  4. Gate 5 (grounded-generation recommendation) -
     gate5_recommendation_pending_human_review.json exists, parses, carries its real required keys
     (bp_id, gate, compliance_touchpoint, customer_message_context, generated_recommendation_text,
     model_used, input_tokens, output_tokens, finish_reason, citation_table, citation_check,
     udaap_check, nist_ai_rmf_risk_category, approval_status, auto_applied,
     human_in_the_loop_required, human_in_the_loop_auto_apply_allowed, generated_at_utc) - AND its
     central governance guardrail survives as its own dedicated check
     (gate5_human_in_the_loop_governance_guardrail): human_in_the_loop_required must be True,
     human_in_the_loop_auto_apply_allowed must be False, auto_applied must be False, and
     approval_status must literally read "PENDING_HUMAN_REVIEW". Per Master Plan paragraph 117
     (quoted in bp6_resolution_service.py's own module docstring): "Every recommendation is
     PENDING_HUMAN_REVIEW and never auto-applied." A real artifact that ever drifted from this - an
     auto_applied=True, or a missing human_in_the_loop_required - would be a concrete, structural
     FAIL of BP6's single most important governance property, never silently dropped, exactly the
     same non-negotiable-guardrail treatment bp5_readiness_verdict.py gives its own
     association_not_causation_disclaimer.

  5. Gate 7 executive rollup manifest (executive_rollup_manifest.json) - parses, has bp_id=="bp6",
     and its own real output_paths (dashboard_html/report_docx/workbook_xlsx/deck_pptx) all exist
     on disk with byte sizes matching what the manifest itself recorded in output_sizes_bytes
     (drift/tamper detection, same spirit as bp5_readiness_verdict.py's own Gate 7 check). This
     module additionally, separately checks that the manifest's own
     human_in_the_loop_required field is present at all (gate7_human_in_the_loop_required_surfaced)
     - real-confirmed True in the real committed manifest - and reports its real value as an
     informational PASS detail rather than silently dropping it on the way from Gate 5 into the
     executive rollup: BP6's central governance guardrail must survive every hop of this project's
     own real artifact chain, not just the gate that first produced it.

  6. src/services/bp6_resolution_service.py imports cleanly, exposes a FastAPI `app`, and that app
     serves the required routes with the required HTTP methods (grep-verified against the real
     file): GET "/", GET "/health", POST "/resolve", POST "/resolve/self-test" - never a bare
     "/predict", since BP6 makes a real, live, one-shot Gemini call per request, not a persisted-
     model prediction.

  7. The runtime packages bp6_resolution_service.py actually imports AT MODULE LEVEL
     (fastapi, pydantic - grep-verified: `from fastapi import FastAPI, HTTPException` and
     `from pydantic import BaseModel, Field`, nothing else at module scope) are declared in
     pyproject.toml. The service's own real genai calls (`from genai.bp6_grounded_generation import
     ...`, and inside THAT module, `from google import genai` for the real `google-genai` SDK) are
     all deliberately LAZY, function-scoped imports - grep-verified - so the service still starts
     and answers /health even when google-genai is not installed or GEMINI_API_KEY is not set; it
     only serves 503 on the generation endpoints in that case (this module's own docstring: "if the
     real ... GEMINI_API_KEY [is] not present, this service still starts (so it can be
     health-checked) but serves 503 on every generation endpoint - never a mock/stub/fabricated
     recommendation"). Because of this, google-genai is correctly NOT required in
     REQUIRED_RUNTIME_PACKAGES below - requiring it would misrepresent what actually gates this
     service's importability.

  8. A dedicated, non-blocking check for whether the real external secret this service needs at
     call time - GEMINI_API_KEY (grep-verified exact env var name, both in
     bp6_grounded_generation.py's own `api_key_env_var: str = "GEMINI_API_KEY"` default and in
     src/services/docker/bp6_resolution_service/docker-compose.yml's own
     `GEMINI_API_KEY=${GEMINI_API_KEY:?GEMINI_API_KEY must be set ...}` line) - is set in the
     current process. PASS if set, WARN (never FAIL) if not: this is a real external secret this
     readiness check cannot and must not require to exist in every environment it runs in (CI
     itself treats it as an environment concern, not a hard-coded one - its own docker-validate job
     passes `GEMINI_API_KEY=ci-smoke-test-placeholder-not-real` as a real, already-committed
     precedent for exactly this treatment, grep-verified in .github/workflows/ci.yml).

  9. tests/services/test_bp6_resolution_service.py exists, and (optionally) actually passes via a
     real pytest subprocess - never a fabricated pass/fail count.

  10. Docker and CI presence - honestly PENDING if not found, PASS if found; both were in fact
      already delivered for BP6 as of this module's writing
      (src/services/docker/bp6_resolution_service/Dockerfile and a docker-validate CI job entry
      referencing bp6_resolution_service and a real GEMINI_API_KEY placeholder), so this check is
      expected to PASS today, not PENDING - but the check itself makes no such assumption and
      reports whatever it actually finds on disk.

Usage (from the project root, after `pip install -e .`):
    python -m deployment.bp6_readiness_verdict
    python -m deployment.bp6_readiness_verdict --write-report
"""

from __future__ import annotations

import argparse
import contextlib
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

BP_ID = "bp6"
BP6_FOLDER = "bp6_genai_resolution_assistant"
BP6_CONFIG_FILE = "bp6_genai_resolution_assistant.yaml"
BP6_SERVICE_MODULE = "services.bp6_resolution_service"
BP6_TEST_FILES = ("tests/services/test_bp6_resolution_service.py",)

ARTIFACTS_RELATIVE_DIR = Path("notebooks") / BP6_FOLDER / "artifacts"
ROLLUP_FILENAME = "executive_rollup_manifest.json"

# Real Gate 2 artifact filenames - read-verified 2026-09-25 directly against the real on-device
# notebooks/bp6_genai_resolution_assistant/artifacts/ directory listing.
GATE2_PII_REPORT_FILENAME = "gate2_pii_screening_report.json"
GATE2_EVIDENCE_REGISTRY_FILENAME = "gate2_evidence_source_registry.json"
GATE2_PII_SCREENED_CSV_FILENAME = "gate2_pii_screened_narrative_text.csv"

GATE3_RETRIEVAL_INVENTORY_FILENAME = "gate3_retrieval_strategy_inventory_entry.json"
GATE5_RECOMMENDATION_FILENAME = "gate5_recommendation_pending_human_review.json"

# Real required keys - read-verified 2026-09-25 directly against the real on-device
# gate2_pii_screening_report.json.
REQUIRED_GATE2_PII_REPORT_KEYS = (
    "n_rows_screened",
    "n_rows_flagged",
    "pct_rows_flagged",
    "category_counts",
    "pii_categories_checked",
)

# Real required keys - read-verified 2026-09-25 directly against the real on-device
# gate2_evidence_source_registry.json (top level only; upstream_bps' own per-BP shape is BP1-5's
# own artifact-inventory concern, not re-validated field-by-field here).
REQUIRED_GATE2_EVIDENCE_REGISTRY_KEYS = ("generated_at_utc", "upstream_bps")

# Real upstream BP ids the evidence registry is confirmed (2026-09-25) to key upstream_bps by.
EXPECTED_EVIDENCE_REGISTRY_UPSTREAM_BP_IDS = ("bp1", "bp2", "bp3", "bp4", "bp5")

# Real required keys - read-verified 2026-09-25 directly against the real on-device
# gate3_retrieval_strategy_inventory_entry.json.
REQUIRED_GATE3_KEYS = (
    "bp_id",
    "gate",
    "compliance_touchpoint",
    "champion_strategy",
    "champion_coverage",
    "runner_up_strategy",
    "runner_up_coverage",
    "candidates_evaluated",
    "candidates_failed",
    "strategy_a_detail",
    "strategy_b_detail",
    "generated_at_utc",
)

# Real required keys - read-verified 2026-09-25 directly against the real on-device
# gate5_recommendation_pending_human_review.json.
REQUIRED_GATE5_KEYS = (
    "bp_id",
    "gate",
    "compliance_touchpoint",
    "customer_message_context",
    "generated_recommendation_text",
    "model_used",
    "input_tokens",
    "output_tokens",
    "finish_reason",
    "citation_table",
    "citation_check",
    "udaap_check",
    "nist_ai_rmf_risk_category",
    "approval_status",
    "auto_applied",
    "human_in_the_loop_required",
    "human_in_the_loop_auto_apply_allowed",
    "generated_at_utc",
)

REQUIRED_ROLLUP_OUTPUT_KEYS = ("dashboard_html", "report_docx", "workbook_xlsx", "deck_pptx")

# grep-verified (2026-09-25) against src/services/bp6_resolution_service.py's own module-level
# import statements: `from fastapi import FastAPI, HTTPException`, `from pydantic import
# BaseModel, Field` - no polars, no pandas, no joblib, no scikit-learn, and (deliberately) no
# google-genai: that SDK is only ever imported lazily, inside function bodies, inside
# src/genai/bp6_grounded_generation.py, never at module scope of the service itself. Both fastapi
# and pydantic are already declared in pyproject.toml (added for BP1-3's own real needs), so - like
# BP4's and BP5's services - BP6's service required no new pyproject.toml/requirements.txt entry.
REQUIRED_RUNTIME_PACKAGES = ("fastapi", "pydantic")

# (method, path) pairs - grep-verified 2026-09-25 against the real
# src/services/bp6_resolution_service.py route decorators.
REQUIRED_ROUTES = (
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/resolve"),
    ("POST", "/resolve/self-test"),
)

# grep-verified (2026-09-25) exact env var name this service and its own docker-compose.yml read
# for the real Gemini API key - see bp6_grounded_generation.py's `api_key_env_var: str =
# "GEMINI_API_KEY"` default and docker-compose.yml's `GEMINI_API_KEY=${GEMINI_API_KEY:?...}` line.
GEMINI_API_KEY_ENV_VAR = "GEMINI_API_KEY"


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
class BP6ReadinessVerdict:
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
            f"# BP6 Deployment Readiness Verdict - {self.bp_id}",
            "",
            f"Generated: {self.generated_at_utc}",
            "",
            f"- **Real Gate 2/3/5/7 evidence ready**: {'YES' if self.artifact_ready else 'NO'}",
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
    readiness_verdict.py, bp4_readiness_verdict.py or bp5_readiness_verdict.py) for the same
    standalone reasoning given in this module's own docstring: no readiness-verdict sibling module
    depends on another at runtime, so a concurrent edit to one never breaks another."""
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
    readiness_verdict.py's, bp4_readiness_verdict.py's and bp5_readiness_verdict.py's own
    identically-named function."""
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def _requirement_declared(requirements: list, package: str) -> bool:
    package_lower = package.lower()
    return any(re.match(rf"^{re.escape(package_lower)}\s*[><=~!]", r.lower()) for r in requirements)


def _load_json_artifact(path: Path, check_name: str) -> tuple:
    """Returns (checks, parsed_or_None). A single shared exists+parse pattern used by every
    Gate 2/3/5/7 artifact check below, so a missing or malformed real artifact is always reported
    the same honest way rather than re-implemented slightly differently per gate."""
    if not path.exists():
        return (
            [
                CheckResult(
                    check_name,
                    CheckStatus.FAIL,
                    f"Expected at {path} - this real BP6 gate artifact has not been produced.",
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


def _check_gate2_artifacts(project_root: Path) -> tuple:
    """Returns (checks, all_ready: bool). Checks all three real Gate 2 artifacts separately - a
    problem with one is never masked by another's PASS."""
    checks: list = []
    artifacts_dir = project_root / ARTIFACTS_RELATIVE_DIR
    all_ready = True

    pii_report_path = artifacts_dir / GATE2_PII_REPORT_FILENAME
    pii_checks, pii_report = _load_json_artifact(pii_report_path, "gate2_pii_screening_report_exists")
    checks.extend(pii_checks)
    if pii_report is None:
        all_ready = False
    else:
        missing_keys = [k for k in REQUIRED_GATE2_PII_REPORT_KEYS if k not in pii_report]
        if missing_keys:
            checks.append(
                CheckResult(
                    "gate2_pii_screening_report_schema",
                    CheckStatus.FAIL,
                    f"Missing real required key(s): {missing_keys}.",
                )
            )
            all_ready = False
        else:
            checks.append(
                CheckResult(
                    "gate2_pii_screening_report_schema",
                    CheckStatus.PASS,
                    f"All {len(REQUIRED_GATE2_PII_REPORT_KEYS)} real required keys present "
                    f"(n_rows_flagged={pii_report.get('n_rows_flagged')!r}).",
                )
            )

    registry_path = artifacts_dir / GATE2_EVIDENCE_REGISTRY_FILENAME
    registry_checks, registry = _load_json_artifact(registry_path, "gate2_evidence_source_registry_exists")
    checks.extend(registry_checks)
    if registry is None:
        all_ready = False
    else:
        missing_keys = [k for k in REQUIRED_GATE2_EVIDENCE_REGISTRY_KEYS if k not in registry]
        if missing_keys:
            checks.append(
                CheckResult(
                    "gate2_evidence_source_registry_schema",
                    CheckStatus.FAIL,
                    f"Missing real required key(s): {missing_keys}.",
                )
            )
            all_ready = False
        else:
            upstream_bps = registry.get("upstream_bps") or {}
            missing_upstream = [
                bp for bp in EXPECTED_EVIDENCE_REGISTRY_UPSTREAM_BP_IDS if bp not in upstream_bps
            ]
            if missing_upstream:
                checks.append(
                    CheckResult(
                        "gate2_evidence_source_registry_schema",
                        CheckStatus.FAIL,
                        f"upstream_bps is missing real upstream BP id(s): {missing_upstream}.",
                    )
                )
                all_ready = False
            else:
                checks.append(
                    CheckResult(
                        "gate2_evidence_source_registry_schema",
                        CheckStatus.PASS,
                        f"All {len(REQUIRED_GATE2_EVIDENCE_REGISTRY_KEYS)} real required top-level "
                        f"keys present; upstream_bps covers all "
                        f"{len(EXPECTED_EVIDENCE_REGISTRY_UPSTREAM_BP_IDS)} real upstream BP ids.",
                    )
                )

    pii_csv_path = artifacts_dir / GATE2_PII_SCREENED_CSV_FILENAME
    if pii_csv_path.exists():
        checks.append(
            CheckResult(
                "gate2_pii_screened_narrative_csv_exists",
                CheckStatus.PASS,
                f"Found at {pii_csv_path} (real audit-trail CSV "
                "src/services/bp6_resolution_service.py's own ResolutionAssistantHandle reads "
                "directly at startup).",
            )
        )
    else:
        checks.append(
            CheckResult(
                "gate2_pii_screened_narrative_csv_exists",
                CheckStatus.FAIL,
                f"Expected at {pii_csv_path} - without it the real service starts but serves 503 "
                "on every generation endpoint.",
            )
        )
        all_ready = False

    return checks, all_ready


def _check_gate3_artifact(project_root: Path) -> tuple:
    """Returns (checks, ready: bool)."""
    checks: list = []
    artifacts_dir = project_root / ARTIFACTS_RELATIVE_DIR
    report_path = artifacts_dir / GATE3_RETRIEVAL_INVENTORY_FILENAME
    load_checks, report = _load_json_artifact(report_path, "gate3_retrieval_strategy_inventory_exists")
    checks.extend(load_checks)
    if report is None:
        return checks, False

    ready = True
    missing_keys = [k for k in REQUIRED_GATE3_KEYS if k not in report]
    if missing_keys:
        checks.append(
            CheckResult(
                "gate3_retrieval_strategy_inventory_schema",
                CheckStatus.FAIL,
                f"Missing real required key(s): {missing_keys}.",
            )
        )
        ready = False
    else:
        checks.append(
            CheckResult(
                "gate3_retrieval_strategy_inventory_schema",
                CheckStatus.PASS,
                f"All {len(REQUIRED_GATE3_KEYS)} real required keys present "
                f"(champion_strategy={report.get('champion_strategy')!r}).",
            )
        )

    bp_id_ok = report.get("bp_id") == "bp6"
    gate_ok = report.get("gate") == 3
    if bp_id_ok and gate_ok:
        checks.append(
            CheckResult(
                "gate3_retrieval_strategy_identity_matches",
                CheckStatus.PASS,
                "bp_id == 'bp6' and gate == 3.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "gate3_retrieval_strategy_identity_matches",
                CheckStatus.FAIL,
                f"Expected bp_id='bp6'/gate=3, found bp_id={report.get('bp_id')!r}, "
                f"gate={report.get('gate')!r} - a real drift between this artifact's declared "
                "identity and where it was found.",
            )
        )
        ready = False

    return checks, ready


def _check_gate5_artifact(project_root: Path) -> tuple:
    """Returns (checks, ready: bool). The governance-guardrail check here is BP6's central
    non-negotiable property (Master Plan paragraph 117) and is always evaluated as its own,
    separately-named check, never folded into the schema check."""
    checks: list = []
    artifacts_dir = project_root / ARTIFACTS_RELATIVE_DIR
    report_path = artifacts_dir / GATE5_RECOMMENDATION_FILENAME
    load_checks, report = _load_json_artifact(report_path, "gate5_recommendation_artifact_exists")
    checks.extend(load_checks)
    if report is None:
        return checks, False

    ready = True
    missing_keys = [k for k in REQUIRED_GATE5_KEYS if k not in report]
    if missing_keys:
        checks.append(
            CheckResult(
                "gate5_recommendation_artifact_schema",
                CheckStatus.FAIL,
                f"Missing real required key(s): {missing_keys}.",
            )
        )
        ready = False
    else:
        checks.append(
            CheckResult(
                "gate5_recommendation_artifact_schema",
                CheckStatus.PASS,
                f"All {len(REQUIRED_GATE5_KEYS)} real required keys present "
                f"(model_used={report.get('model_used')!r}).",
            )
        )

    human_in_the_loop_required = report.get("human_in_the_loop_required")
    human_in_the_loop_auto_apply_allowed = report.get("human_in_the_loop_auto_apply_allowed")
    auto_applied = report.get("auto_applied")
    approval_status = report.get("approval_status")

    guardrail_holds = (
        human_in_the_loop_required is True
        and human_in_the_loop_auto_apply_allowed is False
        and auto_applied is False
        and approval_status == "PENDING_HUMAN_REVIEW"
    )
    if guardrail_holds:
        checks.append(
            CheckResult(
                "gate5_human_in_the_loop_governance_guardrail",
                CheckStatus.PASS,
                "human_in_the_loop_required=True, human_in_the_loop_auto_apply_allowed=False, "
                "auto_applied=False, approval_status='PENDING_HUMAN_REVIEW' - Master Plan "
                "paragraph 117's guardrail ('every recommendation is PENDING_HUMAN_REVIEW and "
                "never auto-applied') holds for this real artifact.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "gate5_human_in_the_loop_governance_guardrail",
                CheckStatus.FAIL,
                "BP6's central governance guardrail does not hold on this real artifact: "
                f"human_in_the_loop_required={human_in_the_loop_required!r}, "
                f"human_in_the_loop_auto_apply_allowed={human_in_the_loop_auto_apply_allowed!r}, "
                f"auto_applied={auto_applied!r}, approval_status={approval_status!r}. Per Master "
                "Plan paragraph 117 this is never allowed to silently drift.",
            )
        )
        ready = False

    return checks, ready


def _check_gate7_rollup_manifest(project_root: Path) -> tuple:
    """Returns (checks, all_ready: bool). Checks the manifest itself, then cross-checks every
    real output file it names against what is actually on disk (existence + byte-size match) -
    drift/tamper detection, same spirit as every other BP's readiness-verdict module. Also checks
    that BP6's central human-in-the-loop governance flag survives from Gate 5 into this rollup
    manifest, never silently dropped."""
    checks: list = []
    manifest_path = project_root / ARTIFACTS_RELATIVE_DIR / ROLLUP_FILENAME

    load_checks, manifest = _load_json_artifact(manifest_path, "gate7_rollup_manifest_exists")
    checks.extend(load_checks)
    if manifest is None:
        return checks, False

    if manifest.get("bp_id") != "bp6":
        checks.append(
            CheckResult(
                "gate7_rollup_manifest_bp_id",
                CheckStatus.FAIL,
                f"Manifest bp_id={manifest.get('bp_id')!r}, expected 'bp6'.",
            )
        )
        return checks, False
    checks.append(CheckResult("gate7_rollup_manifest_bp_id", CheckStatus.PASS, "bp_id == 'bp6'."))

    if "human_in_the_loop_required" in manifest:
        checks.append(
            CheckResult(
                "gate7_human_in_the_loop_required_surfaced",
                CheckStatus.PASS,
                f"human_in_the_loop_required={manifest.get('human_in_the_loop_required')!r} is "
                "present in the Gate 7 rollup manifest - BP6's central governance guardrail "
                "survived from Gate 5 into the executive rollup, not silently dropped.",
            )
        )
    else:
        checks.append(
            CheckResult(
                "gate7_human_in_the_loop_required_surfaced",
                CheckStatus.FAIL,
                "human_in_the_loop_required is absent from the Gate 7 rollup manifest - BP6's "
                "central governance guardrail must survive every hop of this project's real "
                "artifact chain, including the executive rollup.",
            )
        )

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


@contextlib.contextmanager
def _isolated_service_import(project_root: Path, module_name: str):
    """Temporarily import `module_name` from `project_root/src`, then restore sys.path AND
    sys.modules to their prior state on exit - success or failure alike. Forces a fresh import
    (popping the module and its parent package from sys.modules first) so a different
    project_root's service module is never served from a stale cache, but - unlike the version of
    this block that shipped before - never leaves that fresh state behind afterward: a cached
    parent "services" package left pointing at a synthetic project_root's (often since-deleted)
    tmp directory broke every later, unrelated `services.*` import in the same process - a real
    bug this module's own test suite caught when several different project_roots were checked
    back to back against the same long-lived pytest process (and, transitively, that a full
    `pytest tests/` run hit whenever tests/deployment/ ran before tests/services/).
    """
    src_dir = str(project_root / "src")
    path_was_absent = src_dir not in sys.path
    if path_was_absent:
        sys.path.insert(0, src_dir)
    parent_name = module_name.split(".")[0]
    saved_modules = {name: sys.modules.get(name) for name in (module_name, parent_name)}
    for name in (module_name, parent_name):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(module_name)
    finally:
        for name, mod in saved_modules.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
        if path_was_absent:
            try:
                sys.path.remove(src_dir)
            except ValueError:
                pass
        importlib.invalidate_caches()


def _check_service_importable(project_root: Path) -> list:
    checks = []
    try:
        with _isolated_service_import(project_root, BP6_SERVICE_MODULE) as module:
            pass
    except Exception as exc:  # a broken service import is a real, concrete FAIL - never swallowed
        checks.append(
            CheckResult(
                "service_module_imports_cleanly",
                CheckStatus.FAIL,
                f"`import {BP6_SERVICE_MODULE}` raised {type(exc).__name__}: {exc}",
            )
        )
        return checks

    checks.append(
        CheckResult("service_module_imports_cleanly", CheckStatus.PASS, f"`{BP6_SERVICE_MODULE}` imported.")
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
                f"All of {REQUIRED_ROUTES} present - never a bare /predict, BP6 makes a real, "
                "live, one-shot Gemini call per request rather than a persisted-model prediction.",
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
                "src/services/bp6_resolution_service.py; google-genai is a real dependency of "
                "src/genai/bp6_grounded_generation.py but only via a lazy, function-scoped import, "
                "so it is deliberately not required here).",
            )
        )
    return checks


def _check_gemini_api_key_env() -> list:
    """Non-blocking: PASS if the real external secret is set in this process, WARN (never FAIL) if
    not. GEMINI_API_KEY is a real external secret this readiness check cannot and must not require
    to exist in every environment it runs in - the project's own CI treats it the same way (its
    docker-validate job passes GEMINI_API_KEY=ci-smoke-test-placeholder-not-real rather than baking
    a real key into any committed file)."""
    if os.environ.get(GEMINI_API_KEY_ENV_VAR):
        return [
            CheckResult(
                "gemini_api_key_env_var_set",
                CheckStatus.PASS,
                f"{GEMINI_API_KEY_ENV_VAR} is set in this process - real /resolve calls can reach "
                "the Google Gemini API.",
            )
        ]
    return [
        CheckResult(
            "gemini_api_key_env_var_set",
            CheckStatus.WARN,
            f"{GEMINI_API_KEY_ENV_VAR} is not set in this process. Never a FAIL: this is a real "
            "external secret operators supply per-environment (see "
            "src/services/docker/bp6_resolution_service/docker-compose.yml's own "
            "GEMINI_API_KEY=${GEMINI_API_KEY:?...} requirement, and this project's own CI "
            "docker-validate job, which passes a real placeholder rather than a real key). The "
            "service itself still starts and serves /health without it; only the generation "
            "endpoints return 503.",
        )
    ]


def _check_test_files_exist_and_pass(project_root: Path, run_tests: bool) -> list:
    checks = []
    missing = [t for t in BP6_TEST_FILES if not (project_root / t).exists()]
    if missing:
        checks.append(
            CheckResult("test_files_present", CheckStatus.FAIL, f"Missing test file(s): {missing}.")
        )
        return checks
    checks.append(CheckResult("test_files_present", CheckStatus.PASS, f"All of {BP6_TEST_FILES} present."))

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
            [sys.executable, "-m", "pytest", *BP6_TEST_FILES, "-q"],
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
        project_root / "src" / "services" / "docker" / "bp6_resolution_service" / "Dockerfile",
        project_root / "docker" / "bp6_resolution_service" / "Dockerfile",
    ]
    if any(p.exists() for p in dockerfile_candidates):
        found = next(p for p in dockerfile_candidates if p.exists())
        checks.append(CheckResult("dockerfile_present", CheckStatus.PASS, f"Found at {found}."))
    else:
        checks.append(
            CheckResult(
                "dockerfile_present",
                CheckStatus.PENDING,
                "No Dockerfile yet for bp6_resolution_service.",
            )
        )

    ci_path = project_root / ".github" / "workflows" / "ci.yml"
    if ci_path.exists() and "bp6_resolution_service" in ci_path.read_text(encoding="utf-8"):
        checks.append(
            CheckResult(
                "ci_workflow_present", CheckStatus.PASS, f"bp6_resolution_service referenced in {ci_path}."
            )
        )
    else:
        checks.append(
            CheckResult(
                "ci_workflow_present",
                CheckStatus.PENDING,
                "No .github/workflows/ci.yml entry for bp6_resolution_service yet.",
            )
        )
    return checks


def assess_bp6_deployment_readiness(
    project_root: Optional[Path] = None, run_tests: bool = True
) -> BP6ReadinessVerdict:
    if project_root is None:
        project_root = resolve_project_root()

    config_path = project_root / "configs" / BP6_CONFIG_FILE
    if not config_path.exists():
        checks = [
            CheckResult(
                "bp6_config_exists",
                CheckStatus.FAIL,
                f"configs/{BP6_CONFIG_FILE} not found - no BP6 gates have run yet.",
            )
        ]
        return BP6ReadinessVerdict(
            bp_id=BP_ID,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            checks=checks,
            artifact_ready=False,
            service_ready=False,
            fully_deployable=False,
        )

    checks: list = [CheckResult("bp6_config_exists", CheckStatus.PASS, f"Found at {config_path}.")]
    # Loaded for parity with every other readiness module even though this module's own checks
    # read real artifacts directly rather than a config block - kept so a YAML parse failure is
    # itself surfaced as a concrete FAIL rather than silently ignored.
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as exc:
        checks.append(CheckResult("bp6_config_parses", CheckStatus.FAIL, f"{type(exc).__name__}: {exc}"))

    gate2_checks, gate2_ready = _check_gate2_artifacts(project_root)
    checks.extend(gate2_checks)

    gate3_checks, gate3_ready = _check_gate3_artifact(project_root)
    checks.extend(gate3_checks)

    gate5_checks, gate5_ready = _check_gate5_artifact(project_root)
    checks.extend(gate5_checks)

    gate7_checks, gate7_ready = _check_gate7_rollup_manifest(project_root)
    checks.extend(gate7_checks)

    artifact_ready = gate2_ready and gate3_ready and gate5_ready and gate7_ready

    service_checks = _check_service_importable(project_root)
    checks.extend(service_checks)

    dependency_checks = _check_dependencies_declared(project_root)
    checks.extend(dependency_checks)

    # Informational only - never gates artifact_ready/service_ready/fully_deployable (see
    # _check_gemini_api_key_env's own docstring for why a real external secret can never be
    # required by this check).
    checks.extend(_check_gemini_api_key_env())

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

    return BP6ReadinessVerdict(
        bp_id=BP_ID,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        artifact_ready=artifact_ready,
        service_ready=service_ready,
        fully_deployable=fully_deployable,
    )


def _write_report(verdict: BP6ReadinessVerdict, project_root: Path) -> tuple:
    out_dir = project_root / "reports" / BP6_FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "bp6_deployment_readiness_verdict.json"
    md_path = out_dir / "bp6_deployment_readiness_verdict.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(verdict.to_dict(), f, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(verdict.to_markdown())
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer360 Navigator BP6 deployment-readiness verdict.")
    parser.add_argument("--no-run-tests", action="store_true", help="Skip executing the pytest suite.")
    parser.add_argument("--write-report", action="store_true", help="Write JSON+MD under reports/bp6_.../")
    args = parser.parse_args()

    project_root = resolve_project_root()
    verdict = assess_bp6_deployment_readiness(project_root, run_tests=not args.no_run_tests)
    print(verdict.to_markdown())
    if args.write_report:
        json_path, md_path = _write_report(verdict, project_root)
        print(f"[SAVED] {json_path}")
        print(f"[SAVED] {md_path}")
    return 0 if verdict.service_ready else 1


if __name__ == "__main__":
    sys.exit(main())
