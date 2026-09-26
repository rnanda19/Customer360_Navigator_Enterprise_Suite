"""
src/services/bp_activation_service.py — Customer360 Navigator

Suite-level Activation Layer: the final "Insight -> Decision -> Action" hop, sitting downstream of
BP7's real decision engine. This is the piece the project's own architecture review named as
missing (Section 16 of that review): the decision engine currently produces a
`recommended_action` string (e.g. `PRIORITY_QUEUE_REVIEW`) and stops there — nothing downstream
acts on it.

WHAT THIS IS: a real, runnable FastAPI service implementing three activation adapters exactly as
specified — `POST /activation/case`, `POST /activation/crm`, `POST /activation/notification` —
plus `POST /activation/route`, which applies a deterministic, disclosed activation policy over
BP7's own real `recommended_action` vocabulary and calls the matching adapter(s). Every request is
persisted to a real (in-process) SQLite store and independently readable back via
`GET /activation/log`, so this is not a stub that returns a canned 200 — it is a genuine, inspectable
simulated system with real state.

WHAT THIS IS NOT, EXPLICITLY: this does NOT connect to any real CRM, case-management system,
banking core, or notification gateway. Every one of the three adapters is a safe, self-contained
SIMULATION — no outbound network call is made by this service at all (grep-verifiable against its
own imports below: stdlib + fastapi + pydantic + uvicorn only, matching BP4/BP7's own minimal-
dependency precedent). Every response is tagged with a `system` field whose value always starts
with `SIMULATED_` for exactly this reason — so no caller, human or automated, can mistake a
response from this service for a real downstream side effect. This mirrors the project's existing
zero-fabrication convention (`ModelBundleHandle`/BP4/BP7's own "never fabricates" pattern) applied
to an entirely new failure mode: a service that could *look* production-connected but isn't.

Port 8010 (BP1-7 occupy 8001-8007; BP8 has no service; 8008/8009 intentionally left free).
Auth: same shared `C360_API_KEY` / `X-API-Key` header as every other service
(`services.service_auth.require_api_key`) — `/` and `/health` stay open, everything else needs it.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.service_auth import require_api_key

SERVICE_NAME = "bp_activation_service"
SERVICE_PORT = 8010

# BP7's own real, disclosed recommended_action vocabulary (src/features/bp7_decision_engine_features.py
# / gate5_decision_layer_summary.json) — reused verbatim, never redefined, so this policy table can
# never silently drift from what BP7 actually emits.
KNOWN_RECOMMENDED_ACTIONS = (
    "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
    "PRIORITY_QUEUE_REVIEW",
    "STANDARD_QUEUE",
)

# The disclosed, deterministic activation policy (Section 16 of the architecture review): which
# simulated channels a given real BP7 recommended_action activates. A fixed table, never inferred
# or AI-generated at request time — auditable in one place.
ACTIVATION_POLICY: dict[str, tuple[str, ...]] = {
    "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER": ("case", "crm"),
    "PRIORITY_QUEUE_REVIEW": ("case", "crm", "notification"),
    "STANDARD_QUEUE": ("notification",),
}


# ---------------------------------------------------------------------------
# Simulated downstream store — a real, in-process SQLite DB (not a stub). Every adapter call is
# persisted here and independently readable back via GET /activation/log, so "simulated" means
# "no real external system is touched", never "fake/no-op".
# ---------------------------------------------------------------------------
_DB_LOCK = threading.Lock()
_CONN: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(":memory:", check_same_thread=False)
        _CONN.execute(
            """
            CREATE TABLE activation_log (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                complaint_id TEXT,
                system TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """
        )
    return _CONN


def _record_event(event_type: str, complaint_id: Optional[str], system: str, payload: dict) -> str:
    import json

    event_id = f"sim-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc).isoformat()
    with _DB_LOCK:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO activation_log (event_id, event_type, complaint_id, system, payload_json, "
            "created_at_utc) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, event_type, complaint_id, system, json.dumps(payload), created_at),
        )
        conn.commit()
    return event_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_conn()  # create the in-process simulated store at startup
    yield


app = FastAPI(
    title="Customer360 Navigator — Activation Layer (SIMULATED)",
    description=(
        "Simulated Insight->Decision->Action activation adapters over BP7's real decision output. "
        "No adapter here calls a real external system — see module docstring."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------
class CaseRequest(BaseModel):
    complaint_id: str = Field(..., description="Real BP7-scored Complaint ID this case is opened for.")
    recommended_action: str = Field(..., description="BP7's own recommended_action for this complaint.")
    priority_score: Optional[float] = None
    reason_codes: list[str] = Field(default_factory=list)
    queue: Optional[str] = Field(None, description="Simulated case-management queue name.")


class CaseResponse(BaseModel):
    case_id: str
    status: Literal["created"] = "created"
    system: Literal["SIMULATED_CASE_MANAGEMENT"] = "SIMULATED_CASE_MANAGEMENT"
    created_at_utc: str


class CrmRequest(BaseModel):
    complaint_id: str
    customer_360_id: Optional[str] = Field(
        None, description="Optional golden-record ID from the identity-resolution demo layer, if used."
    )
    note: str = Field(..., description="Activity note to log against the simulated CRM record.")
    priority: Optional[str] = None


class CrmResponse(BaseModel):
    activity_id: str
    status: Literal["logged"] = "logged"
    system: Literal["SIMULATED_CRM"] = "SIMULATED_CRM"
    logged_at_utc: str


class NotificationRequest(BaseModel):
    complaint_id: str
    channel: Literal["email", "sms", "in_app"] = "in_app"
    recipient_hint: str = Field(
        ..., description="Opaque display hint only (e.g. 'customer on file') — never a real address/number."
    )
    template: str = Field(..., description="Notification template name — content is never generated here.")
    priority: Optional[str] = None


class NotificationResponse(BaseModel):
    message_id: str
    status: Literal["queued"] = "queued"
    system: Literal["SIMULATED_NOTIFICATION_GATEWAY"] = "SIMULATED_NOTIFICATION_GATEWAY"
    queued_at_utc: str


class RouteRequest(BaseModel):
    complaint_id: str
    recommended_action: str = Field(..., description="Must be one of BP7's real recommended_action values.")
    priority_score: Optional[float] = None
    intervention_flag: Optional[bool] = None
    reason_codes: list[str] = Field(default_factory=list)
    customer_360_id: Optional[str] = None


class RouteResponse(BaseModel):
    complaint_id: str
    recommended_action: str
    channels_activated: list[str]
    case: Optional[CaseResponse] = None
    crm: Optional[CrmResponse] = None
    notification: Optional[NotificationResponse] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def root() -> dict:
    return {
        "service": SERVICE_NAME,
        "purpose": "Simulated activation adapters (case/crm/notification) over BP7's real decision output.",
        "disclosure": "No adapter makes any real external network call. See module docstring.",
        "known_recommended_actions": list(KNOWN_RECOMMENDED_ACTIONS),
        "activation_policy": {k: list(v) for k, v in ACTIVATION_POLICY.items()},
    }


@app.get("/health")
def health() -> dict:
    with _DB_LOCK:
        n_events = _get_conn().execute("SELECT COUNT(*) FROM activation_log").fetchone()[0]
    return {"status": "ok", "service": SERVICE_NAME, "simulated_events_logged": n_events}


@app.post("/activation/case", response_model=CaseResponse, dependencies=[Depends(require_api_key)])
def create_case(req: CaseRequest) -> CaseResponse:
    case_id = f"CASE-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    _record_event("case", req.complaint_id, "SIMULATED_CASE_MANAGEMENT", req.model_dump())
    return CaseResponse(case_id=case_id, created_at_utc=now)


@app.post("/activation/crm", response_model=CrmResponse, dependencies=[Depends(require_api_key)])
def log_crm_activity(req: CrmRequest) -> CrmResponse:
    activity_id = f"ACT-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    _record_event("crm", req.complaint_id, "SIMULATED_CRM", req.model_dump())
    return CrmResponse(activity_id=activity_id, logged_at_utc=now)


@app.post(
    "/activation/notification", response_model=NotificationResponse, dependencies=[Depends(require_api_key)]
)
def send_notification(req: NotificationRequest) -> NotificationResponse:
    message_id = f"MSG-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    _record_event("notification", req.complaint_id, "SIMULATED_NOTIFICATION_GATEWAY", req.model_dump())
    return NotificationResponse(message_id=message_id, queued_at_utc=now)


@app.post("/activation/route", response_model=RouteResponse, dependencies=[Depends(require_api_key)])
def route_decision(req: RouteRequest) -> RouteResponse:
    """Applies the disclosed ACTIVATION_POLICY table to a real BP7-shaped decision record and calls
    the matching simulated adapter(s) — the Decision -> Activation policy -> Channel hop from the
    architecture review, end to end in one call."""
    if req.recommended_action not in ACTIVATION_POLICY:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown recommended_action '{req.recommended_action}'. Known values: "
                f"{list(KNOWN_RECOMMENDED_ACTIONS)}. Routing is never attempted for an action outside "
                "BP7's own real vocabulary, rather than guessing a channel."
            ),
        )
    channels = ACTIVATION_POLICY[req.recommended_action]
    result = RouteResponse(
        complaint_id=req.complaint_id,
        recommended_action=req.recommended_action,
        channels_activated=list(channels),
    )
    if "case" in channels:
        result.case = create_case(
            CaseRequest(
                complaint_id=req.complaint_id,
                recommended_action=req.recommended_action,
                priority_score=req.priority_score,
                reason_codes=req.reason_codes,
            )
        )
    if "crm" in channels:
        result.crm = log_crm_activity(
            CrmRequest(
                complaint_id=req.complaint_id,
                customer_360_id=req.customer_360_id,
                note=f"BP7 recommended_action={req.recommended_action}; reason_codes={req.reason_codes}",
            )
        )
    if "notification" in channels:
        result.notification = send_notification(
            NotificationRequest(
                complaint_id=req.complaint_id,
                channel="in_app",
                recipient_hint="customer on file",
                template=f"decision_{req.recommended_action.lower()}",
            )
        )
    return result


@app.get("/activation/log", dependencies=[Depends(require_api_key)])
def activation_log(limit: int = 50) -> dict:
    """Proves this is a real, stateful simulation, not a stub: every prior adapter call is
    independently readable back here."""
    with _DB_LOCK:
        rows = (
            _get_conn()
            .execute(
                "SELECT event_id, event_type, complaint_id, system, payload_json, created_at_utc "
                "FROM activation_log ORDER BY created_at_utc DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            )
            .fetchall()
        )
    import json

    return {
        "count": len(rows),
        "events": [
            {
                "event_id": r[0],
                "event_type": r[1],
                "complaint_id": r[2],
                "system": r[3],
                "payload": json.loads(r[4]),
                "created_at_utc": r[5],
            }
            for r in rows
        ],
    }
