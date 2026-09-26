"""
src/services/bp7_decision_engine_service.py — Customer360 Navigator

BP7 (Customer Navigator Decision Engine) real-time decision-record lookup FastAPI service — Gate 6
(Productization, Monitoring & Governance) deliverable. Self-contained and independently deployable
(run with `uvicorn services.bp7_decision_engine_service:app`), matching BP1-6's own
one-service-file-per-problem pattern.

Per Master Plan paragraph 205 ("Per-BP governance set, required before Gate 6 sign-off:
MODEL_CARD.md, CHANGELOG.md, and — for BP6/BP7 — a runnable FastAPI service with a live self-test
proving API output matches direct computation."), this file is itself part of BP7's Gate 6
deliverable, not an optional Hardening extra (Section 18.1's "Optional FastAPI + Docker + MLflow"
does not apply to BP6/BP7 — theirs is mandatory).

BP7 is architecturally different from BP6: BP6 fits no persisted artifact and makes a real, live
external API call (Gemini) on every `/resolve`; BP7 makes NO external call at all — it is a
deterministic weighted-rule engine (`features.bp7_decision_engine_features.score_priority_rule`)
that Gate 5 already applied once, for real, to the full real population and persisted at
`notebooks/bp7_customer_navigator_decision_engine/artifacts/gate5_full_population_decision_records.csv`
(one row per real `Complaint ID`: `priority_score`/`intervention_flag`/`recommended_action`/
`reason_codes` plus every real upstream field that fed it — `FINAL_OUTPUT_COLUMNS`, unchanged).
This service is therefore architecturally closer to `services.bp4_decision_service` (read-only
lookup over a real, persisted decision artifact, never a live model/API call) than to
`services.bp6_resolution_service` — see BP4's own module docstring for the shared "reads a real
persisted artifact, never predicts or generates" rationale, reused here for the identical reason.

Deliberately standalone: does NOT import `src/services/service_common.py` (its ModelBundleHandle/
HealthResponse are model-bundle-shaped, BP1/BP2/BP3-specific) — reimplements project-root
resolution locally, identically, matching BP4's and BP6's own established precedent for a service
with no model bundle.

Point-lookup strategy — never an eager full-file load: the real Gate 5 CSV is large (~540MB,
1,048,575 rows). `GET /decide/{complaint_id}` runs a real, per-request `polars.scan_csv(...)
.filter(...)` LAZY scan against it (never loaded whole into memory at startup). At STARTUP, this
service only checks the file's real existence and its real schema (column names, via a zero-row
`.limit(0).collect()` — never a full read), plus loads Gate 5's own already-computed summary JSON
(`gate5_decision_layer_summary.json`) for the `/health` response's population-level real statistics
(row count, champion rule scheme, weights, threshold) — REUSED, never recomputed: re-deriving those
at every service startup would mean re-scoring the full 1,048,575-row population on every restart,
which Gate 5's own notebook already did once, for real, and persisted.

Zero-fabrication rule applies here exactly as everywhere else in this project: if the real Gate 5
CSV (or its summary JSON) is not present on disk, this service still starts (so it can be
health-checked) but serves 503 on `/decide` and `/decide/self-test` — never a mock/fabricated
decision record.

On the self-test's own honesty (BP7 has no external API call to test, unlike BP6's real Gemini
call — see that module's own docstring for the contrast this service deliberately does NOT copy):
`GET /decide/self-test` performs a REAL internal-consistency check on `sample_size` real,
already-scored rows read from the real Gate 5 CSV (deterministic — the first `sample_size` rows in
the file's own on-disk order, never random/unseeded; re-running against the same unchanged artifact
always samples the identical rows). It reuses
`features.bp7_decision_engine_features.summarize_contribution_decomposition` (Gate 4/5's own real
reconciliation function, imported and called UNMODIFIED, never reimplemented) to independently
verify `contribution_bp2 + contribution_bp3 + contribution_bp4` reconstructs `priority_score`
exactly for every sampled row — plus two further real, structural checks this endpoint performs
directly on the fetched rows: (a) `intervention_flag == (priority_score >=
DEFAULT_INTERVENTION_THRESHOLD)` for every row (the real, imported threshold constant, never a
hardcoded literal), and (b) every row's own `recommended_action` is one of the known real vocabulary
and structurally consistent with its own `intervention_flag` (`STANDARD_QUEUE` iff not flagged, one
of the three escalation/priority actions iff flagged, `UNSCORED_MISSING_UPSTREAM_INPUT` iff
`priority_score` is null). It also fetches the SAME sampled `Complaint ID`s via two
independently-constructed lazy-scan calls and asserts the two reads are field-for-field identical,
proving this service's own read path introduces no drift versus the real artifact on disk.

This is disclosed here, and again in the endpoint's own docstring and response, so it is never
mistaken for a claim that `score_priority_rule` itself was re-run end-to-end from upstream inputs:
the real Gate 5 CSV does not carry `bp4_recurring_flag`/`bp4_high_volume_flag` per row (only the
already-computed `reason_codes` string that encodes them), so a full, from-scratch re-derivation of
`reason_codes`/`recommended_action` via `score_priority_rule` is not reproducible from this artifact
alone — never attempted here with a fabricated stand-in for those two missing columns. The checks
above are the honest, real thing this service CAN verify from what it actually serves.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import polars as pl
from fastapi import Depends, FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi import Query
from pydantic import BaseModel, Field

from services.service_auth import require_api_key

BP_ID = "bp7"
DEFAULT_SELF_TEST_SAMPLE_SIZE = 25
MAX_SELF_TEST_SAMPLE_SIZE = 500

# The real, full recommended_action vocabulary `features.bp7_decision_engine_features
# ._recommended_action_expr()` can produce (verified live against that real function's own source,
# never guessed) - used below only for the self-test's structural-consistency check, never to gate
# `/decide` itself (which returns whatever real value the persisted artifact actually holds, even
# if this vocabulary were ever to drift).
KNOWN_RECOMMENDED_ACTIONS = frozenset(
    {
        "UNSCORED_MISSING_UPSTREAM_INPUT",
        "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
        "ESCALATE_SENIOR_REVIEWER",
        "PRIORITY_QUEUE_REVIEW",
        "STANDARD_QUEUE",
    }
)


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every service/notebook in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) — reimplemented here (not imported from
    service_common.py), matching BP4's and BP6's own precedent for a service with no model
    bundle."""
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


def _default_records_csv_path(project_root: Path) -> Path:
    return (
        project_root
        / "notebooks"
        / "bp7_customer_navigator_decision_engine"
        / "artifacts"
        / "gate5_full_population_decision_records.csv"
    )


def _default_summary_json_path(project_root: Path) -> Path:
    return (
        project_root
        / "notebooks"
        / "bp7_customer_navigator_decision_engine"
        / "artifacts"
        / "gate5_decision_layer_summary.json"
    )


class DecisionEngineHandle:
    """Loads (or fails to load) BP7's real, static Gate 5 prerequisites at service startup — the
    real, persisted full-population decision-records CSV path (schema-checked, never fully read)
    and Gate 5's own real summary JSON (fully read — it is small). Never raises past __init__ — any
    missing/invalid prerequisite is recorded as `self.error`, not thrown, so the service can still
    start, serve an honest /health response, and return 503 on every query endpoint — same pattern
    as every other BP's own service handle in this project (`ModelBundleHandle`,
    `DecisionArtifactHandle`, `ResolutionAssistantHandle`)."""

    def __init__(self, records_csv_path: Path, summary_json_path: Path):
        self.records_csv_path = records_csv_path
        self.summary_json_path = summary_json_path
        self.schema_columns: Optional[list[str]] = None
        self.summary: Optional[dict[str, Any]] = None
        self.error: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if not self.records_csv_path.exists():
            self.error = (
                f"{self.records_csv_path} does not exist. Run BP7 Gate 5 for real first "
                "(bp7_customer_navigator_decision_engine_g5_decision_layer_reporting.ipynb)."
            )
            return
        if not self.summary_json_path.exists():
            self.error = f"{self.summary_json_path} does not exist. Run BP7 Gate 5 for real first."
            return

        try:
            schema_probe = pl.scan_csv(self.records_csv_path).limit(0).collect()
        except Exception as e:  # noqa: BLE001 - any parse failure means "not loaded", never a crash
            self.error = f"Gate 5 records CSV at {self.records_csv_path} failed schema probe: {e}"
            return
        if "Complaint ID" not in schema_probe.columns:
            self.error = f"{self.records_csv_path} is missing the required 'Complaint ID' column."
            return

        import json

        try:
            with open(self.summary_json_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except (OSError, ValueError) as e:
            self.error = f"Gate 5 summary JSON at {self.summary_json_path} failed to load: {e}"
            return

        self.schema_columns = list(schema_probe.columns)
        self.summary = summary

    @property
    def is_loaded(self) -> bool:
        return self.schema_columns is not None and self.summary is not None


_handle: Optional[DecisionEngineHandle] = None


def _get_handle() -> DecisionEngineHandle:
    if _handle is None:
        raise HTTPException(status_code=503, detail="BP7 decision-engine handle not initialized.")
    return _handle


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    project_root = resolve_project_root()
    _handle = DecisionEngineHandle(
        _default_records_csv_path(project_root), _default_summary_json_path(project_root)
    )
    yield


app = FastAPI(
    title="Customer360 Navigator - BP7 Customer Navigator Decision Engine",
    description=(
        "Read-only lookup service over BP7's real, persisted, full-population priority-decision "
        "records (Gate 5's own deterministic weighted-rule output) - never a live model/API call, "
        "never a prediction, never a fabricated result."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class DecisionEngineHealthResponse(BaseModel):
    status: str = Field(description="'ok' if the real Gate 5 artifacts loaded, else 'not_configured'.")
    bp_id: str
    live_row_count: Optional[int] = None
    champion_rule_scheme: Optional[str] = None
    champion_weights_normalized: Optional[dict[str, float]] = None
    intervention_threshold: Optional[float] = None
    records_csv_path: Optional[str] = None
    records_csv_columns: Optional[list[str]] = None
    generated_at_utc: Optional[str] = None
    error: Optional[str] = None


class DecisionRecord(BaseModel):
    complaint_id: int
    priority_score: Optional[float] = None
    intervention_flag: bool
    recommended_action: str
    reason_codes: str
    contribution_bp2: Optional[float] = None
    contribution_bp3: Optional[float] = None
    contribution_bp4: Optional[float] = None
    bp2_predicted_label: Optional[str] = None
    bp2_confidence: Optional[float] = None
    bp3_predicted_label: Optional[str] = None
    bp3_probability_positive_class: Optional[float] = None
    bp4_review_priority_tier: Optional[str] = None
    bp4_review_priority_score: Optional[int] = None
    bp4_join_status: Optional[str] = None
    bp1_context_status: Optional[str] = None
    bp5_outcome_1_context: Optional[str] = None
    bp5_outcome_2_context: Optional[str] = None
    tags_group: Optional[str] = None


class SelfTestRowCheck(BaseModel):
    complaint_id: int
    contribution_reconstruction_exact: bool
    intervention_flag_matches_threshold_rule: bool
    recommended_action_structurally_consistent: bool
    dual_read_identical: bool


class SelfTestResponse(BaseModel):
    all_checks_passed: bool = Field(
        description=(
            "True iff every real, sampled row passed all four internal-consistency checks below. "
            "See the module docstring for why this - not a live re-derivation via score_priority_rule "
            "- is the honest proof BP7's no-external-API self-test can make."
        )
    )
    sample_size_requested: int
    n_rows_checked: int
    contribution_decomposition_summary: dict[str, Any]
    row_checks: list[SelfTestRowCheck]
    real_external_api_call_made: bool = False


def _row_to_record(row: dict[str, Any]) -> DecisionRecord:
    return DecisionRecord(
        complaint_id=row["Complaint ID"],
        priority_score=row.get("priority_score"),
        intervention_flag=bool(row["intervention_flag"]),
        recommended_action=row["recommended_action"],
        reason_codes=row["reason_codes"],
        contribution_bp2=row.get("contribution_bp2"),
        contribution_bp3=row.get("contribution_bp3"),
        contribution_bp4=row.get("contribution_bp4"),
        bp2_predicted_label=row.get("bp2_predicted_label"),
        bp2_confidence=row.get("bp2_confidence"),
        # Real Gate 5 CSV stores bp3_predicted_label as BP3's real int64 binary label (0/1),
        # not a string like BP2's categorical friction tier - cast explicitly so the API's
        # documented `Optional[str]` contract (matching bp2_predicted_label's shape) holds for
        # both upstream fields, rather than letting pydantic reject the real int value outright.
        bp3_predicted_label=(
            str(row["bp3_predicted_label"]) if row.get("bp3_predicted_label") is not None else None
        ),
        bp3_probability_positive_class=row.get("bp3_probability_positive_class"),
        bp4_review_priority_tier=row.get("bp4_review_priority_tier"),
        bp4_review_priority_score=row.get("bp4_review_priority_score"),
        bp4_join_status=row.get("bp4_join_status"),
        bp1_context_status=row.get("bp1_context_status"),
        bp5_outcome_1_context=row.get("bp5_outcome_1_context"),
        bp5_outcome_2_context=row.get("bp5_outcome_2_context"),
        tags_group=row.get("tags_group"),
    )


def _fetch_complaint_row(handle: DecisionEngineHandle, complaint_id: int) -> Optional[dict[str, Any]]:
    """One real, per-request lazy-scan point lookup against the real Gate 5 CSV - never an eager
    full-file load (see module docstring)."""
    match = pl.scan_csv(handle.records_csv_path).filter(pl.col("Complaint ID") == complaint_id).collect()
    if match.height == 0:
        return None
    return match.row(0, named=True)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp7_customer_navigator_decision_engine",
        "docs": "/docs",
        "health": "/health",
        "decide": "/decide/{complaint_id}",
        "self_test": "/decide/self-test",
        "note": (
            "Read-only lookup service over BP7's real, persisted, full-population priority-decision "
            "records - not a live model/API inference endpoint. BP7 makes no external network call "
            "anywhere, unlike BP6."
        ),
    }


@app.get("/health", response_model=DecisionEngineHealthResponse, tags=["meta"])
def health():
    handle = _get_handle()
    if not handle.is_loaded:
        return DecisionEngineHealthResponse(status="not_configured", bp_id=BP_ID, error=handle.error)
    summary = handle.summary or {}
    return DecisionEngineHealthResponse(
        status="ok",
        bp_id=BP_ID,
        live_row_count=summary.get("live_row_count"),
        champion_rule_scheme=summary.get("champion_rule_scheme"),
        champion_weights_normalized=summary.get("champion_weights_normalized"),
        intervention_threshold=summary.get("intervention_threshold"),
        records_csv_path=str(handle.records_csv_path),
        records_csv_columns=handle.schema_columns,
        generated_at_utc=summary.get("generated_at_utc"),
    )


@app.get(
    "/decide/self-test",
    response_model=SelfTestResponse,
    tags=["query", "governance"],
    dependencies=[Depends(require_api_key)],
)
def decide_self_test(
    sample_size: int = Query(
        DEFAULT_SELF_TEST_SAMPLE_SIZE,
        ge=1,
        le=MAX_SELF_TEST_SAMPLE_SIZE,
        description="Number of real, already-scored rows to internal-consistency-check.",
    )
):
    """Master Plan paragraph 205's required BP6/BP7 Gate 6 deliverable, adapted for BP7's
    no-external-API nature (see module docstring for the full rationale): a REAL internal-
    consistency check over `sample_size` real rows read from the real, persisted Gate 5 CSV -
    never a mock, never a fabricated pass. Makes ZERO external network calls (BP7 makes none
    anywhere) - the honest analogue here is proving this service's own read/serve path introduces
    no drift versus the real artifact on disk, and that every served row is internally consistent
    with its own real, already-computed fields."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP7 decision engine is not configured: {handle.error}")

    # Two independently-constructed lazy scans over the same real artifact - deterministic (the
    # file's own on-disk order, never random/unseeded) - proving the read path is reproducible.
    sample_a = pl.scan_csv(handle.records_csv_path).limit(sample_size).collect()
    sample_b = pl.scan_csv(handle.records_csv_path).limit(sample_size).collect()
    if sample_a.height == 0:
        raise HTTPException(status_code=503, detail="Real Gate 5 records CSV contains zero rows.")

    # Reuse (never reinvent) Gate 4/5's own real reconciliation function.
    from features.bp7_decision_engine_features import (
        DEFAULT_INTERVENTION_THRESHOLD,
        summarize_contribution_decomposition,
    )

    threshold = float((handle.summary or {}).get("intervention_threshold", DEFAULT_INTERVENTION_THRESHOLD))
    decomposition_summary = summarize_contribution_decomposition(sample_a)

    row_checks: list[SelfTestRowCheck] = []
    for row_a, row_b in zip(sample_a.iter_rows(named=True), sample_b.iter_rows(named=True)):
        dual_read_identical = row_a == row_b

        priority_score = row_a["priority_score"]
        intervention_flag = bool(row_a["intervention_flag"])
        if priority_score is None:
            intervention_matches_rule = intervention_flag is False
        else:
            intervention_matches_rule = intervention_flag == (priority_score >= threshold)

        # An unscored row (priority_score is null, structurally UNSCORED_MISSING_UPSTREAM_INPUT)
        # has no contribution_bp2/3/4 to reconstruct - vacuously consistent, matching
        # summarize_contribution_decomposition()'s own aggregate semantics above (it excludes null
        # rows from the reconstruction-error check entirely, never counts one as a failure).
        if priority_score is None:
            contribution_exact = True
        else:
            contrib_sum = (
                (row_a["contribution_bp2"] or 0.0)
                + (row_a["contribution_bp3"] or 0.0)
                + (row_a["contribution_bp4"] or 0.0)
            )
            contribution_exact = abs(contrib_sum - priority_score) < 1e-6

        recommended_action = row_a["recommended_action"]
        action_is_known = recommended_action in KNOWN_RECOMMENDED_ACTIONS
        if priority_score is None:
            action_consistent = recommended_action == "UNSCORED_MISSING_UPSTREAM_INPUT"
        elif intervention_flag:
            action_consistent = recommended_action in (
                "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
                "ESCALATE_SENIOR_REVIEWER",
                "PRIORITY_QUEUE_REVIEW",
            )
        else:
            action_consistent = recommended_action == "STANDARD_QUEUE"

        row_checks.append(
            SelfTestRowCheck(
                complaint_id=row_a["Complaint ID"],
                contribution_reconstruction_exact=contribution_exact,
                intervention_flag_matches_threshold_rule=intervention_matches_rule,
                recommended_action_structurally_consistent=action_is_known and action_consistent,
                dual_read_identical=dual_read_identical,
            )
        )

    all_checks_passed = decomposition_summary["reconstruction_exact_within_tolerance"] and all(
        (
            rc.contribution_reconstruction_exact
            and rc.intervention_flag_matches_threshold_rule
            and rc.recommended_action_structurally_consistent
            and rc.dual_read_identical
        )
        for rc in row_checks
    )

    return SelfTestResponse(
        all_checks_passed=all_checks_passed,
        sample_size_requested=sample_size,
        n_rows_checked=sample_a.height,
        contribution_decomposition_summary=decomposition_summary,
        row_checks=row_checks,
    )


@app.get(
    "/decide/{complaint_id}",
    response_model=DecisionRecord,
    tags=["query"],
    dependencies=[Depends(require_api_key)],
)
def decide(complaint_id: int = PathParam(..., description="Real, unique CFPB 'Complaint ID'.")):
    """Real, read-only point lookup of one real complaint's already-computed
    priority_score/intervention_flag/recommended_action/reason_codes (Gate 5's own real,
    full-population output) - never a live re-score, never a fabricated result for an unknown ID.
    Registered AFTER `/decide/self-test` above so that literal path is matched first (Starlette/
    FastAPI route matching is order-dependent - a `/decide/{complaint_id}` route registered first
    would otherwise swallow `/decide/self-test` by parsing "self-test" as an int and 422'ing)."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP7 decision engine is not configured: {handle.error}")
    row = _fetch_complaint_row(handle, complaint_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"No real decision record for Complaint ID {complaint_id}."
        )
    return _row_to_record(row)
