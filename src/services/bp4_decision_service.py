"""
src/services/bp4_decision_service.py — Customer360 Navigator

BP4 (Customer Journey Analytics) read-only decision-records lookup/query FastAPI service -
Hardening Step 3. Self-contained and independently deployable (run with
`uvicorn services.bp4_decision_service:app`), matching BP1/BP2/BP3's own one-service-file-per-
problem pattern.

BP4 is architecturally different from BP1/BP2/BP3: it fits no supervised model, so this is NOT an
inference endpoint. It loads the real, typed, CLUSTER_KEY-sorted Parquet index persisted by
notebooks/bp4_customer_journey_analytics/bp4_customer_journey_analytics_decision_artifact_persistence.ipynb
(Hardening Step 2) at startup and serves read-only lookup/query endpoints over BP4's real
per-issue-cluster review-priority decision/reporting records - never a prediction, never a
fabricated result.

Deliberately standalone: this file does NOT import src/services/service_common.py (its
ModelBundleHandle/HealthResponse are model-bundle-shaped and BP1/BP2/BP3-specific) to avoid any
risk of colliding with concurrent edits to that shared module. Project-root resolution is
reimplemented here, identically to service_common.py's own version, rather than imported.

Zero-fabrication rule applies here exactly as it does to BP1/2/3's inference services: if the real
Parquet artifact is not present on disk (the user has not yet run the Hardening Step 2 persistence
notebook for real), this service still starts (so it can be health-checked) but serves 503 on every
query endpoint - never a mock/empty/synthetic result presented as real.

Real BP4 issue-cluster key note: 'Company' real-contains a literal '/' character in 291 of the
37,160 real rows (e.g. 'AES/PHEAA') - live-verified against the real Gate 5 artifact. A path-
segment route for the composite key would break on those real rows, so the exact-match lookup
endpoint below takes the key as query parameters, never path segments.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import polars as pl
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

BP_ID = "bp4"
CLUSTER_KEY = ["Company", "Product", "Sub-product", "Issue", "Sub-issue"]
VALID_TIERS = ("HIGH", "MEDIUM", "LOW", "NONE")
MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 50


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every service/notebook in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) - reimplemented here (not imported from
    service_common.py) so this file has zero dependency on that shared module."""
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


def _default_parquet_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp4_customer_journey_analytics" / "bp4_decision_artifact_index.parquet"


def _default_metadata_path() -> Path:
    project_root = resolve_project_root()
    return project_root / "models" / "bp4_customer_journey_analytics" / "bp4_decision_artifact_metadata.json"


class DecisionArtifactHandle:
    """Loads (or fails to load) the real persisted Parquet decision-artifact index at service
    startup, and holds the result for the lifetime of the process. Never raises past __init__ - a
    missing or corrupt artifact is recorded as `self.error`, not thrown, so the service can still
    start, serve an honest /health response, and return 503 on every query endpoint - never crash
    at import time with no way to even ask the service what is wrong (same pattern as BP1/BP2/BP3's
    ModelBundleHandle in service_common.py, reimplemented standalone here)."""

    def __init__(self, bp_id: str, parquet_path: Path, metadata_path: Optional[Path] = None):
        self.bp_id = bp_id
        self.parquet_path = parquet_path
        self.metadata_path = metadata_path
        self.frame: Optional[pl.DataFrame] = None
        self.metadata: Optional[dict[str, Any]] = None
        self.error: Optional[str] = None
        self._load()

    def _load(self) -> None:
        if not self.parquet_path.exists():
            self.error = (
                f"Decision-artifact Parquet index not found at {self.parquet_path}. Run the "
                f"{self.bp_id}_customer_journey_analytics_decision_artifact_persistence.ipynb "
                "notebook for real first."
            )
            return
        try:
            self.frame = pl.read_parquet(self.parquet_path)
        except Exception as e:  # noqa: BLE001 - any parquet-read failure means "not loaded", never a crash
            self.error = f"Decision-artifact Parquet index at {self.parquet_path} failed to load: {e}"
            return

        missing_cols = [c for c in CLUSTER_KEY if c not in self.frame.columns]
        if missing_cols:
            self.error = f"Loaded Parquet is missing real CLUSTER_KEY column(s): {missing_cols}"
            self.frame = None
            return

        if self.metadata_path is not None and self.metadata_path.exists():
            import json

            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except (OSError, ValueError):
                # Metadata sidecar is documentation, not required to serve queries - a missing or
                # unreadable sidecar must never block an artifact that loaded successfully.
                self.metadata = None

    @property
    def is_loaded(self) -> bool:
        return self.frame is not None


_handle: Optional[DecisionArtifactHandle] = None


def _get_handle() -> DecisionArtifactHandle:
    if _handle is None:
        raise HTTPException(status_code=503, detail="BP4 decision-artifact handle not initialized.")
    return _handle


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    _handle = DecisionArtifactHandle(BP_ID, _default_parquet_path(), _default_metadata_path())
    yield


app = FastAPI(
    title="Customer360 Navigator - BP4 Customer Journey Analytics (Decision Records)",
    description=(
        "Read-only lookup/query service over BP4's real, persisted per-issue-cluster review-"
        "priority decision/reporting records. Not an ML inference service - BP4 fits no model."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class DecisionHealthResponse(BaseModel):
    status: str = Field(description="'ok' if the Parquet index loaded, else 'artifact_not_loaded'.")
    bp_id: str
    parquet_path: Optional[str] = None
    parquet_sha256: Optional[str] = None
    n_rows: Optional[int] = None
    n_columns: Optional[int] = None
    tier_counts: Optional[dict[str, int]] = None
    round_trip_verified: Optional[bool] = None
    generated_at_utc: Optional[str] = None
    error: Optional[str] = None


class ClusterRecord(BaseModel):
    company: str
    product: str
    sub_product: str
    issue: str
    sub_issue: str
    n_complaints_total: int
    first_complaint_date: str
    last_complaint_date: str
    n_active_months: int
    avg_response_lag_days: float
    banking77_coverage_fraction: float
    is_recurring_cluster: bool
    recurring_flag: bool
    elevated_lag_flag: bool
    high_volume_flag: bool
    review_priority_score: int
    review_priority_tier: str
    reason_codes: str
    reason_evidence: str


class ClusterListResponse(BaseModel):
    total_matching: int
    limit: int
    offset: int
    items: list[ClusterRecord]


def _row_to_record(row: dict) -> ClusterRecord:
    return ClusterRecord(
        company=row["Company"],
        product=row["Product"],
        sub_product=row["Sub-product"],
        issue=row["Issue"],
        sub_issue=row["Sub-issue"],
        n_complaints_total=row["n_complaints_total"],
        first_complaint_date=str(row["first_complaint_date"]),
        last_complaint_date=str(row["last_complaint_date"]),
        n_active_months=row["n_active_months"],
        avg_response_lag_days=row["avg_response_lag_days"],
        banking77_coverage_fraction=row["banking77_coverage_fraction"],
        is_recurring_cluster=row["is_recurring_cluster"],
        recurring_flag=row["recurring_flag"],
        elevated_lag_flag=row["elevated_lag_flag"],
        high_volume_flag=row["high_volume_flag"],
        review_priority_score=row["review_priority_score"],
        review_priority_tier=row["review_priority_tier"],
        reason_codes=row["reason_codes"],
        reason_evidence=row["reason_evidence"],
    )


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp4_customer_journey_analytics_decision_records",
        "docs": "/docs",
        "health": "/health",
        "lookup": "/cluster/lookup",
        "list": "/clusters",
        "cluster_key_columns": CLUSTER_KEY,
        "valid_tiers": list(VALID_TIERS),
        "note": "Read-only lookup/query service - not an ML inference endpoint (BP4 fits no model).",
    }


@app.get("/health", response_model=DecisionHealthResponse, tags=["meta"])
def health():
    handle = _get_handle()
    if not handle.is_loaded:
        return DecisionHealthResponse(status="artifact_not_loaded", bp_id=handle.bp_id, error=handle.error)
    meta = handle.metadata or {}
    return DecisionHealthResponse(
        status="ok",
        bp_id=handle.bp_id,
        parquet_path=meta.get("parquet_relative_path", str(handle.parquet_path)),
        parquet_sha256=meta.get("parquet_sha256"),
        n_rows=meta.get("n_rows", handle.frame.height if handle.frame is not None else None),
        n_columns=meta.get("n_columns", len(handle.frame.columns) if handle.frame is not None else None),
        tier_counts=meta.get("tier_counts"),
        round_trip_verified=meta.get("round_trip_verified"),
        generated_at_utc=meta.get("generated_at_utc"),
    )


@app.get("/cluster/lookup", response_model=ClusterRecord, tags=["query"])
def lookup_cluster(
    company: str = Query(..., min_length=1, description="Real 'Company' value (exact match)."),
    product: str = Query(..., min_length=1, description="Real 'Product' value (exact match)."),
    sub_product: str = Query(..., min_length=1, description="Real 'Sub-product' value (exact match)."),
    issue: str = Query(..., min_length=1, description="Real 'Issue' value (exact match)."),
    sub_issue: str = Query(..., min_length=1, description="Real 'Sub-issue' value (exact match)."),
):
    """Exact-match point lookup by the real, full issue-cluster key. Query parameters (never path
    segments) because real 'Company' values contain a literal '/' in 291/37,160 real rows."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP4 decision artifact is not loaded: {handle.error}")

    match = handle.frame.filter(
        (pl.col("Company") == company)
        & (pl.col("Product") == product)
        & (pl.col("Sub-product") == sub_product)
        & (pl.col("Issue") == issue)
        & (pl.col("Sub-issue") == sub_issue)
    )
    if match.height == 0:
        raise HTTPException(status_code=404, detail="No real issue-cluster matches that exact key.")
    return _row_to_record(match.row(0, named=True))


@app.get("/clusters", response_model=ClusterListResponse, tags=["query"])
def list_clusters(
    tier: Optional[str] = Query(None, description=f"Filter by review_priority_tier, one of {VALID_TIERS}."),
    company: Optional[str] = Query(None, description="Filter by exact real 'Company' value."),
    recurring_only: Optional[bool] = Query(None, description="Filter to is_recurring_cluster=True only."),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    """Paginated, filterable listing over the real full population, ordered by the persisted
    CLUSTER_KEY sort order (deterministic paging - two calls with the same filters and offset
    always return the same real page)."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(status_code=503, detail=f"BP4 decision artifact is not loaded: {handle.error}")

    if tier is not None and tier not in VALID_TIERS:
        raise HTTPException(status_code=422, detail=f"tier must be one of {VALID_TIERS}, got {tier!r}.")

    frame = handle.frame
    if tier is not None:
        frame = frame.filter(pl.col("review_priority_tier") == tier)
    if company is not None:
        frame = frame.filter(pl.col("Company") == company)
    if recurring_only:
        frame = frame.filter(pl.col("is_recurring_cluster"))

    total_matching = frame.height
    page = frame.slice(offset, limit)
    items = [_row_to_record(row) for row in page.iter_rows(named=True)]
    return ClusterListResponse(total_matching=total_matching, limit=limit, offset=offset, items=items)


@app.get("/clusters/tiers/{tier}", response_model=ClusterListResponse, tags=["query"])
def list_clusters_by_tier(
    tier: str,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    """Convenience path-based variant of `GET /clusters?tier=...` - safe as a path segment (unlike
    the composite cluster key) since review_priority_tier only ever takes one of 4 fixed real
    values, none containing a '/'."""
    return list_clusters(tier=tier, company=None, recurring_only=None, limit=limit, offset=offset)
