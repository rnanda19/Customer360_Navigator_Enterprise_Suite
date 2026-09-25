"""
src/services/bp5_driver_service.py — Customer360 Navigator

BP5 (Root-Cause & Driver Analytics) read-only reporting FastAPI service - Hardening pass (BP5 has
never had a FastAPI service or Docker packaging before this file, unlike BP1-4 and BP6). Self-
contained and independently deployable (run with `uvicorn services.bp5_driver_service:app`),
matching BP1/BP2/BP3/BP4/BP6's own one-service-file-per-problem pattern. Named
`bp5_driver_service.py` to match `src/models/bp5_driver_association.py`'s own "driver" naming
convention for this BP.

BP5 is architecturally different from BP1/BP2/BP3 (no supervised classifier is served - this is
NOT an inference endpoint) AND different from BP4 (BP4 wraps a Parquet decision-artifact INDEX
persisted to models/ by its own dedicated Hardening Step 2 persistence notebook; BP5 has no such
persistence notebook and models/bp5_root_cause_driver_analytics/ holds only a .gitkeep - live-
verified). Instead this service reads directly from BP5's own real, statically-committed Gate 5
prioritized root-cause report JSON artifacts and Gate 7 executive rollup manifest under
notebooks/bp5_root_cause_driver_analytics/artifacts/ - the same "COPY the real committed
notebooks/**/artifacts/ JSON directly, no models/ persistence step" shape BP6's own service already
established (notebooks/**/artifacts/ is NOT gitignored - see .gitignore - so these are real,
already-committed evidence, not something a Claude session generates).

BP5 fits no supervised classifier for a decision boundary (its Gate 3 logistic regression exists
only to drive SHAP and coefficient-based association findings, per its own module docstring in
src/models/bp5_driver_association.py) and makes no GenAI call (confirmed: BP5 never uses GenAI,
unlike BP6). This is a deterministic, read-only, ASSOCIATION-ONLY reporting service - it serves
BP5's own real, already-computed Gate 5/Gate 7 findings verbatim, including their own real
association-not-causation disclaimer text, never reshaping or re-deriving a causal claim from them.

Deliberately standalone: this file does NOT import src/services/service_common.py (its
ModelBundleHandle/HealthResponse are model-bundle-shaped and BP1/BP2/BP3-specific) - project-root
resolution is reimplemented here, identically to service_common.py's own version and to
bp4_decision_service.py's and bp6_resolution_service.py's own standalone copies, rather than
imported (matching this project's own established per-service-file precedent for a service with no
model bundle).

Zero-fabrication rule applies here exactly as it does to every other BP's service: if a real Gate 5
report or the Gate 7 rollup manifest is not present on disk for a given outcome, this service still
starts (so it can be health-checked) but serves 503 on the query endpoint(s) it needs that artifact
for - never a mock/empty/synthetic result presented as real.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

BP_ID = "bp5"
ARTIFACTS_RELATIVE_DIR = Path("notebooks") / "bp5_root_cause_driver_analytics" / "artifacts"

VALID_OUTCOMES = (
    "outcome_1_intervention_required",
    "outcome_2_timely_response_failure",
)

REPORT_FILENAMES: dict[str, str] = {
    "outcome_1_intervention_required": (
        "gate5_prioritized_root_cause_report_outcome_1_intervention_required.json"
    ),
    "outcome_2_timely_response_failure": (
        "gate5_prioritized_root_cause_report_outcome_2_timely_response_failure.json"
    ),
}

ROLLUP_FILENAME = "executive_rollup_manifest.json"


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every service/notebook in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) - reimplemented here (not imported from
    service_common.py) so this file has zero dependency on that shared module, matching BP4's and
    BP6's own standalone precedent for a service with no model bundle."""
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
        "Customer360_Navigator_Enterprise_Suite folder before starting this service."
    )


def _default_artifacts_dir() -> Path:
    return resolve_project_root() / ARTIFACTS_RELATIVE_DIR


def _load_json(path: Path) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Loads one real JSON artifact, never raising - a missing or corrupt file is reported back as
    an error string, not thrown, so a handle can hold a per-artifact loaded/error state without any
    one missing file preventing the others from loading."""
    if not path.exists():
        return None, f"Real artifact not found at {path}."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError) as e:  # noqa: BLE001 - any read/parse failure means "not loaded"
        return None, f"Real artifact at {path} failed to load: {e}"


class DriverReportHandle:
    """Loads (or fails to load) BP5's real Gate 5 prioritized root-cause reports (one per real
    outcome) and the Gate 7 executive rollup manifest at service startup, and holds the result for
    the lifetime of the process. Never raises past __init__ - each artifact's load state is tracked
    independently (a missing Gate 7 rollup must never block a Gate 5 report that loaded fine, and
    vice versa), so the service can always start, serve an honest /health response, and return 503
    only for the specific query that needs a still-missing real artifact."""

    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.reports: dict[str, Optional[dict[str, Any]]] = {}
        self.report_errors: dict[str, str] = {}
        self.rollup: Optional[dict[str, Any]] = None
        self.rollup_error: Optional[str] = None
        self._load()

    def _load(self) -> None:
        for outcome, filename in REPORT_FILENAMES.items():
            data, error = _load_json(self.artifacts_dir / filename)
            self.reports[outcome] = data
            if error:
                self.report_errors[outcome] = error

        data, error = _load_json(self.artifacts_dir / ROLLUP_FILENAME)
        self.rollup = data
        self.rollup_error = error

    def is_outcome_loaded(self, outcome: str) -> bool:
        return self.reports.get(outcome) is not None

    @property
    def is_rollup_loaded(self) -> bool:
        return self.rollup is not None

    @property
    def n_outcomes_loaded(self) -> int:
        return sum(1 for v in self.reports.values() if v is not None)


_handle: Optional[DriverReportHandle] = None


def _get_handle() -> DriverReportHandle:
    if _handle is None:
        raise HTTPException(status_code=503, detail="BP5 driver-report handle not initialized.")
    return _handle


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    _handle = DriverReportHandle(_default_artifacts_dir())
    yield


app = FastAPI(
    title="Customer360 Navigator - BP5 Root-Cause & Driver Analytics (Reporting)",
    description=(
        "Read-only reporting service over BP5's real, committed Gate 5 prioritized root-cause "
        "reports and Gate 7 executive rollup manifest. Not an ML inference service (BP5's Gate 3 "
        "logistic regression exists only to drive association findings, never a served decision "
        "boundary) and makes no GenAI call. Association only, never causal."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class DriverHealthResponse(BaseModel):
    status: str = Field(
        description="'ok' if both real outcome reports loaded, 'partially_loaded' if only some "
        "did, else 'artifact_not_loaded'."
    )
    bp_id: str
    outcomes_loaded: dict[str, bool]
    rollup_loaded: bool
    n_outcomes_loaded: int
    generated_at_utc: Optional[str] = None
    errors: dict[str, str] = Field(default_factory=dict)


class DriverRecord(BaseModel):
    """One field-level or category-level association finding, as BP5's real Gate 5 report emits
    it. Modeled loosely (Any-typed nested payload) rather than pinned field-by-field, because this
    endpoint returns BP5's real report content verbatim - reshaping it risks silently dropping or
    misrepresenting a real citation."""

    model_config = {"extra": "allow"}


class PrioritizedRootCauseReport(BaseModel):
    outcome_field: str
    association_not_causation_disclaimer: str
    field_level_ranking: list[dict[str, Any]]
    category_level_findings_by_field: dict[str, list[dict[str, Any]]]
    champion_shap_feature_importance: list[dict[str, Any]]
    company_process_field_finding: dict[str, Any]
    champion_validation_snapshot: dict[str, Any]
    barred_field_governance_disclosures: dict[str, Any]
    narrative_text: dict[str, Any]
    min_n_per_category_threshold_used: int
    top_k_fields: int
    top_k_categories_per_field: int
    top_k_shap_features: int


class TopDriversResponse(BaseModel):
    outcome_field: str
    association_not_causation_disclaimer: str
    field_level_ranking: list[dict[str, Any]]


class ExecutiveRollupResponse(BaseModel):
    bp_id: str
    gate: int
    report_name: str
    outcomes: list[str]
    production_recommendation_tier: str
    production_recommendation_tier_code: int
    ecoa_reg_b_disparate_impact_applicability: str
    output_paths: dict[str, str]
    output_sizes_bytes: dict[str, int]
    contains_financial_impact_section: bool
    contains_assumption_based_content: bool
    n_negligible_strength_fields_detected: int
    n_near_zero_precision_outcomes_detected: int
    association_not_causation_disclaimer_carried_forward: bool
    generated_at_utc: str


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp5_root_cause_driver_analytics_reporting",
        "docs": "/docs",
        "health": "/health",
        "outcomes": "/outcomes",
        "report": "/report/{outcome}",
        "top_drivers": "/report/{outcome}/top-drivers",
        "rollup": "/rollup",
        "valid_outcomes": list(VALID_OUTCOMES),
        "note": (
            "Read-only reporting service over BP5's real, committed Gate 5/Gate 7 root-cause "
            "reports - not an ML inference endpoint and not a GenAI service. Association only, "
            "never causal."
        ),
    }


@app.get("/health", response_model=DriverHealthResponse, tags=["meta"])
def health():
    handle = _get_handle()
    outcomes_loaded = {o: handle.is_outcome_loaded(o) for o in VALID_OUTCOMES}
    if handle.n_outcomes_loaded == len(VALID_OUTCOMES):
        status = "ok"
    elif handle.n_outcomes_loaded > 0:
        status = "partially_loaded"
    else:
        status = "artifact_not_loaded"

    errors = dict(handle.report_errors)
    if handle.rollup_error:
        errors["rollup"] = handle.rollup_error

    return DriverHealthResponse(
        status=status,
        bp_id=BP_ID,
        outcomes_loaded=outcomes_loaded,
        rollup_loaded=handle.is_rollup_loaded,
        n_outcomes_loaded=handle.n_outcomes_loaded,
        generated_at_utc=(handle.rollup or {}).get("generated_at_utc"),
        errors=errors,
    )


@app.get("/outcomes", tags=["meta"])
def list_outcomes():
    handle = _get_handle()
    return {
        "valid_outcomes": list(VALID_OUTCOMES),
        "outcomes_loaded": {o: handle.is_outcome_loaded(o) for o in VALID_OUTCOMES},
    }


def _require_valid_outcome(outcome: str) -> None:
    if outcome not in VALID_OUTCOMES:
        raise HTTPException(
            status_code=422, detail=f"outcome must be one of {VALID_OUTCOMES}, got {outcome!r}."
        )


@app.get("/report/{outcome}", response_model=PrioritizedRootCauseReport, tags=["query"])
def get_report(outcome: str):
    """Full real Gate 5 prioritized root-cause report for one real BP5 outcome field, served
    verbatim (field-level ranking, per-category log-odds findings, SHAP feature importance, the
    real Company process-field finding, the champion model's held-out validation snapshot, barred-
    field governance disclosures, and BP5's own real narrative text) - including its own real
    association-not-causation disclaimer, unaltered."""
    _require_valid_outcome(outcome)
    handle = _get_handle()
    report = handle.reports.get(outcome)
    if report is None:
        raise HTTPException(
            status_code=503,
            detail=f"BP5 Gate 5 report for outcome={outcome!r} is not loaded: "
            f"{handle.report_errors.get(outcome, 'unknown error')}",
        )
    return PrioritizedRootCauseReport(**report)


@app.get("/report/{outcome}/top-drivers", response_model=TopDriversResponse, tags=["query"])
def get_top_drivers(outcome: str):
    """Convenience subset of `GET /report/{outcome}` - just the real field-level driver ranking
    and its disclaimer, for a caller that only needs the headline association findings."""
    _require_valid_outcome(outcome)
    handle = _get_handle()
    report = handle.reports.get(outcome)
    if report is None:
        raise HTTPException(
            status_code=503,
            detail=f"BP5 Gate 5 report for outcome={outcome!r} is not loaded: "
            f"{handle.report_errors.get(outcome, 'unknown error')}",
        )
    return TopDriversResponse(
        outcome_field=report["outcome_field"],
        association_not_causation_disclaimer=report["association_not_causation_disclaimer"],
        field_level_ranking=report["field_level_ranking"],
    )


@app.get("/rollup", response_model=ExecutiveRollupResponse, tags=["query"])
def get_rollup():
    """BP5's real Gate 7 executive rollup manifest, served verbatim."""
    handle = _get_handle()
    if handle.rollup is None:
        raise HTTPException(
            status_code=503,
            detail=f"BP5 Gate 7 executive rollup manifest is not loaded: {handle.rollup_error}",
        )
    return ExecutiveRollupResponse(**handle.rollup)
