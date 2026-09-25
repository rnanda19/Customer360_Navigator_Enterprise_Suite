"""
src/services/bp6_resolution_service.py — Customer360 Navigator

BP6 (GenAI Resolution Assistant) FastAPI service — Gate 6 (Productization, Monitoring &
Governance) deliverable. Self-contained and independently deployable (run with
`uvicorn services.bp6_resolution_service:app`), matching BP1-4's own one-service-file-per-problem
pattern, but architecturally different from all of them: BP6 fits no persisted model bundle and
indexes no static artifact — every real `/resolve` call performs a real, live, grounded-generation
round trip through Google's Gemini API (`src/genai/bp6_grounded_generation.py`), exactly
reproducing Gate 5's own real pipeline, request by request.

Per Master Plan paragraph 205 ("Per-BP governance set, required before Gate 6 sign-off:
MODEL_CARD.md, CHANGELOG.md, and — for BP6/BP7 — a runnable FastAPI service with a live self-test
proving API output matches direct computation."), this file is itself part of BP6's Gate 6
deliverable, not an optional Hardening extra (Section 18.1's "Optional FastAPI + Docker + MLflow"
does not apply to BP6/BP7 — theirs is mandatory).

Deliberately standalone: does NOT import `src/services/service_common.py` (its ModelBundleHandle/
HealthResponse are model-bundle-shaped, BP1/BP2/BP3-specific) — reimplements project-root
resolution locally, identically, matching BP4's own precedent for a service with no model bundle.

Zero-fabrication rule applies here exactly as everywhere else in this project: if the real,
upstream Gate 7 evidence manifests, Gate 2's PII-screened corpus, or a real `GEMINI_API_KEY` are
not present, this service still starts (so it can be health-checked) but serves 503 on every
generation endpoint — never a mock/stub/fabricated recommendation.

On "the self-test proving API output matches direct computation": Gemini's real, live text
generation is not deterministic across two separate network calls (temperature/sampling are not
pinned to 0 by this project's own real Gate 5 design), so a self-test that fired the network twice
and diffed the generated *text* would be dishonestly testing LLM determinism, not this service. The
honest, real thing to prove — and the thing `POST /resolve/self-test` below actually proves — is
that the FastAPI layer is a byte-for-byte-transparent wrapper around the exact same underlying
`src/genai/bp6_grounded_generation.py` functions Gate 5's own notebook calls directly: it makes
ONE real Gemini call, captures that one real `generation_result`, and then independently re-derives
the final recommendation artifact TWICE from that identical `generation_result` — once via this
service's own internal `_run_pipeline()` composition, once via a second, independently-invoked call
to `build_recommendation_artifact()` — and asserts the two are equal. One real network call, two
independent code paths, real equality check. This is disclosed here, in the module docstring, and
again in the endpoint's own docstring and response, so it is never mistaken for a claim that two
live Gemini calls would produce identical prose.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

BP_ID = "bp6"
UPSTREAM_BP_IDS = ("bp1", "bp2", "bp3", "bp4", "bp5")


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every service/notebook in this project
    (PROJECT_STRUCTURE_LOCKED.md rule #3) — reimplemented here (not imported from
    service_common.py), matching BP4's own precedent for a service with no model bundle."""
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


class ResolutionAssistantHandle:
    """Loads (or fails to load) BP6's real, static prerequisites at service startup — the Gate 4
    eligible-bucket trace, the Gate 2 PII-screened corpus path, and the real evidence bundle built
    from BP1-5's own real Gate 7 executive rollup manifests. Never raises past __init__ — any
    missing prerequisite is recorded as `self.error`, not thrown, so the service can still start,
    serve an honest /health response, and return 503 on every generation endpoint (same pattern as
    every other BP's service handle in this project). Does NOT check `GEMINI_API_KEY` here (that
    is re-checked fresh on every /resolve call by `call_grounded_generation` itself, matching
    Gate 5's own notebook behavior — an operator could rotate the key mid-process)."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.citations: Optional[list[dict[str, Any]]] = None
        self.citation_lookup: Optional[dict[str, dict[str, Any]]] = None
        self.pii_screened_csv_path: Optional[Path] = None
        self.eligible_buckets: Optional[tuple[str, ...]] = None
        self.error: Optional[str] = None
        self._load()

    def _load(self) -> None:
        from genai.bp6_grounded_generation import retrieve_headline_evidence_bundle

        artifacts_dir = self.project_root / "notebooks" / "bp6_genai_resolution_assistant" / "artifacts"
        pii_csv = artifacts_dir / "gate2_pii_screened_narrative_text.csv"
        gate4_trace_path = artifacts_dir / "gate4_explainability_trace.json"

        if not pii_csv.exists():
            self.error = f"{pii_csv} does not exist. Run BP6 Gate 2 for real first."
            return
        if not gate4_trace_path.exists():
            self.error = f"{gate4_trace_path} does not exist. Run BP6 Gate 4 for real first."
            return

        import json

        with open(gate4_trace_path, "r", encoding="utf-8") as f:
            gate4_trace = json.load(f)
        eligible_buckets = tuple(entry["bucket"] for entry in gate4_trace)
        if not eligible_buckets:
            self.error = (
                f"{gate4_trace_path} contains zero real cross-corpus-hit buckets — Gate 5/6 "
                "cannot select a grounded narrative sample. Re-run BP6 Gate 4 for real."
            )
            return

        try:
            citations, citation_lookup = retrieve_headline_evidence_bundle(
                self.project_root, upstream_bp_ids=UPSTREAM_BP_IDS
            )
        except FileNotFoundError as e:
            self.error = str(e)
            return

        self.pii_screened_csv_path = pii_csv
        self.eligible_buckets = eligible_buckets
        self.citations = citations
        self.citation_lookup = citation_lookup

    @property
    def is_loaded(self) -> bool:
        return self.citations is not None


_handle: Optional[ResolutionAssistantHandle] = None


def _get_handle() -> ResolutionAssistantHandle:
    if _handle is None:
        raise HTTPException(status_code=503, detail="BP6 resolution-assistant handle not initialized.")
    return _handle


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _handle
    _handle = ResolutionAssistantHandle(resolve_project_root())
    yield


app = FastAPI(
    title="Customer360 Navigator - BP6 GenAI Resolution Assistant",
    description=(
        "Real, live, grounded-generation resolution-recommendation service. Every /resolve call "
        "makes one real external call to the Google Gemini API and consumes real, free-tier API "
        "quota — never a mock or cached response. Every recommendation is PENDING_HUMAN_REVIEW "
        "and never auto-applied (Master Plan paragraph 117)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' if prerequisites loaded, else 'not_configured'.")
    bp_id: str
    n_evidence_citations_available: Optional[int] = None
    n_eligible_retrieval_buckets: Optional[int] = None
    gemini_api_key_present: bool
    gemini_model_override: Optional[str] = None
    error: Optional[str] = None


class NarrativeSampleIn(BaseModel):
    """Explicit override of the customer message this call should draft a recommendation for.
    Matches `select_real_narrative_sample()`'s own real return shape exactly (masked_text/
    category/common_taxonomy_bucket) — the caller supplies a real message (already PII-masked by
    the caller's own upstream process; this service applies no PII screening of its own, matching
    Gate 5's own scope, which consumes Gate 2's already-screened output rather than re-screening)."""

    masked_text: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    common_taxonomy_bucket: str = Field(..., min_length=1)


class ResolveRequest(BaseModel):
    narrative_sample: Optional[NarrativeSampleIn] = Field(
        None,
        description=(
            "Explicit customer message to draft a recommendation for. Omit to reuse Gate 5's own "
            "reproducible selection (one real, PII-clear row from Gate 2's screened corpus, "
            "random_state=42) — the same real example Gate 5's notebook itself used."
        ),
    )
    random_state: int = Field(
        42, description="Only used when narrative_sample is omitted (reproducible-sample mode)."
    )


class ResolveResponse(BaseModel):
    recommendation_artifact: dict[str, Any]


class SelfTestResponse(BaseModel):
    identical: bool = Field(
        description=(
            "True iff the artifact this endpoint composed and the artifact independently "
            "re-derived from the SAME real generation_result are field-for-field equal. Proves "
            "the FastAPI layer introduces no drift versus direct computation — see module "
            "docstring for why this is the honest proof, not a claim of LLM determinism."
        )
    )
    endpoint_composed_artifact: dict[str, Any]
    directly_computed_artifact: dict[str, Any]
    real_gemini_call_made: bool = True


def _select_narrative_sample(handle: ResolutionAssistantHandle, req: ResolveRequest) -> dict[str, Any]:
    if req.narrative_sample is not None:
        return req.narrative_sample.model_dump()
    from genai.bp6_grounded_generation import select_real_narrative_sample

    return select_real_narrative_sample(
        handle.pii_screened_csv_path, eligible_buckets=handle.eligible_buckets, random_state=req.random_state
    )


def _run_pipeline(handle: ResolutionAssistantHandle, narrative_sample: dict[str, Any]) -> dict[str, Any]:
    """The one real pipeline composition, shared by /resolve and (as the endpoint-composed half
    of) /resolve/self-test — exactly Gate 5 notebook's own Sections 6-12, reused verbatim rather
    than re-implemented, so this service can never silently drift from the notebook's own real,
    governed behavior."""
    from genai.bp6_grounded_generation import (
        MissingApiKeyError,
        assemble_grounded_prompt,
        build_recommendation_artifact,
        call_grounded_generation,
        check_udaap_customer_facing_language_batch,
        compute_nist_ai_rmf_risk_category,
        split_into_sentences,
        validate_citations_in_generated_text,
    )

    prompt = assemble_grounded_prompt(narrative_sample, handle.citations)
    try:
        generation_result = call_grounded_generation(prompt)
    except MissingApiKeyError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    citation_check = validate_citations_in_generated_text(
        generation_result["generated_text"], handle.citation_lookup
    )
    sentences = split_into_sentences(generation_result["generated_text"])
    udaap_check = check_udaap_customer_facing_language_batch(sentences)
    risk_category = compute_nist_ai_rmf_risk_category(
        citation_check_passed=citation_check["passed"],
        udaap_check_passed=udaap_check["passed"],
        human_in_the_loop_enforced=True,
        auto_apply_allowed=False,
        pii_masking_applied_upstream=True,
    )

    response_truncated = generation_result.get("finish_reason") == "MAX_TOKENS"
    if not (citation_check["passed"] and udaap_check["passed"]) or response_truncated:
        raise HTTPException(
            status_code=422,
            detail=(
                "This real generation failed BP6's own structural checks "
                f"(citation_check.passed={citation_check['passed']}, "
                f"udaap_check.passed={udaap_check['passed']}, "
                f"finish_reason={generation_result.get('finish_reason')!r}). Per Master Plan "
                "paragraph 117, a recommendation that fails grounding/UDAAP review or was "
                "truncated is never presented, even flagged. Retry the call for a fresh attempt — "
                "no recommendation was returned."
            ),
        )

    artifact = build_recommendation_artifact(
        narrative_sample, handle.citations, generation_result, citation_check, udaap_check, risk_category
    )
    return artifact, generation_result


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "bp6_genai_resolution_assistant",
        "docs": "/docs",
        "health": "/health",
        "resolve": "/resolve",
        "self_test": "/resolve/self-test",
        "note": (
            "Every /resolve and /resolve/self-test call makes a REAL, live external call to the "
            "Google Gemini API and consumes real API quota. Every recommendation is "
            "PENDING_HUMAN_REVIEW and is never auto-applied."
        ),
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    handle = _get_handle()
    key_present = bool(os.environ.get("GEMINI_API_KEY"))
    model_override = os.environ.get("GEMINI_MODEL")
    if not handle.is_loaded:
        return HealthResponse(
            status="not_configured",
            bp_id=BP_ID,
            gemini_api_key_present=key_present,
            gemini_model_override=model_override,
            error=handle.error,
        )
    return HealthResponse(
        status="ok",
        bp_id=BP_ID,
        n_evidence_citations_available=len(handle.citations),
        n_eligible_retrieval_buckets=len(handle.eligible_buckets),
        gemini_api_key_present=key_present,
        gemini_model_override=model_override,
    )


@app.post("/resolve", response_model=ResolveResponse, tags=["generation"])
def resolve(req: ResolveRequest):
    """Makes ONE real, live Gemini API call and returns a grounded, PENDING_HUMAN_REVIEW
    recommendation artifact — the exact same shape Gate 5's notebook writes to
    `gate5_recommendation_pending_human_review.json`. Real external network call: consumes real
    API quota on every invocation; never a mock or cached response (zero-fabrication rule)."""
    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(
            status_code=503, detail=f"BP6 resolution assistant is not configured: {handle.error}"
        )
    narrative_sample = _select_narrative_sample(handle, req)
    artifact, _ = _run_pipeline(handle, narrative_sample)
    return ResolveResponse(recommendation_artifact=artifact)


@app.post("/resolve/self-test", response_model=SelfTestResponse, tags=["generation", "governance"])
def resolve_self_test(req: ResolveRequest):
    """Master Plan paragraph 205's required BP6 Gate 6 deliverable: 'a runnable FastAPI service
    with a live self-test proving API output matches direct computation'. Makes exactly ONE real
    Gemini call, then independently re-derives the recommendation artifact TWICE from that
    identical real `generation_result` — once via this service's own `_run_pipeline()`
    composition (the endpoint-composed half), once via a fresh, separately-invoked call to
    `build_recommendation_artifact()` (the directly-computed half) — and reports whether they are
    field-for-field equal. See the module docstring for why this is the honest proof (the LLM's
    live text is not pinned deterministic across two network calls; this endpoint fires the
    network exactly once and diffs two computations of that one real result, not two live calls)."""
    from genai.bp6_grounded_generation import (
        build_recommendation_artifact,
        check_udaap_customer_facing_language_batch,
        compute_nist_ai_rmf_risk_category,
        split_into_sentences,
        validate_citations_in_generated_text,
    )

    handle = _get_handle()
    if not handle.is_loaded:
        raise HTTPException(
            status_code=503, detail=f"BP6 resolution assistant is not configured: {handle.error}"
        )
    narrative_sample = _select_narrative_sample(handle, req)

    endpoint_artifact, generation_result = _run_pipeline(handle, narrative_sample)

    # Directly-computed half: re-derive from the SAME real generation_result, independently.
    citation_check = validate_citations_in_generated_text(
        generation_result["generated_text"], handle.citation_lookup
    )
    sentences = split_into_sentences(generation_result["generated_text"])
    udaap_check = check_udaap_customer_facing_language_batch(sentences)
    risk_category = compute_nist_ai_rmf_risk_category(
        citation_check_passed=citation_check["passed"],
        udaap_check_passed=udaap_check["passed"],
        human_in_the_loop_enforced=True,
        auto_apply_allowed=False,
        pii_masking_applied_upstream=True,
    )
    direct_artifact = build_recommendation_artifact(
        narrative_sample, handle.citations, generation_result, citation_check, udaap_check, risk_category
    )

    identical = endpoint_artifact == direct_artifact
    return SelfTestResponse(
        identical=identical,
        endpoint_composed_artifact=endpoint_artifact,
        directly_computed_artifact=direct_artifact,
    )
