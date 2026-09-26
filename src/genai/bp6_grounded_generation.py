"""BP6 (GenAI Resolution Assistant) — Gate 5 support module: grounded evidence assembly, the real
Google Gemini API call, citation validation, UDAAP customer-facing language review, and NIST AI
RMF risk-category computation.

This is BP6's first gate with an actual external API call — every earlier gate (1-4) was prep-only
and structurally verified zero GenAI SDK modules loaded. Master Plan Section 5.1 (paragraph 117)
states the architecture directly: "Use retrieval/grounding and deterministic templates around
GenAI (BP6) — no ungrounded generation is ever presented as a recommendation." This module
implements that literally: the model is never allowed to invent its own evidence. It is given a
real, pre-assembled evidence bundle (citation IDs already fixed, drawn from BP1-BP5's own real
artifacts) and instructed to cite only from it; the generated text is then structurally validated
— every citation tag the model used must resolve to a real citation record, or the check fails and
nothing is presented as a finished recommendation. The final artifact wraps the model's (validated)
text inside a deterministic template alongside the full real citation table, never presenting raw
model prose alone.

Per user decision (2026-09-24): provider is Google's Gemini API via the official `google-genai`
SDK — pivoted the same day from an initial Anthropic Claude API choice, specifically because
Gemini has a genuine, standing no-cost free tier (the Flash-family models) reachable with only a
Google AI Studio API key, no funded billing account required. (Anthropic's own Claude for Startups
free-credit program was considered and ruled out: its stated eligibility requires institutional
equity funding and a company founded within the last four years — this project is a personal
portfolio build during a job search, not a funded company, so it does not meet that bar.) This gate
is still built PLUGGABLE — the real call is fully wired, but if GEMINI_API_KEY is not set, this
module raises a clear RuntimeError naming exactly what to do, rather than fabricating or stubbing a
fake response. No artifact and no config block are ever written from a failed/missing-key run.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# Reused unmodified from src/genai/bp6_evidence_prep.py (Gate 2) - the same real bp_id -> bp_name
# lookup every gate in this project already uses, never re-derived here.
from genai.bp6_evidence_prep import UPSTREAM_BP_NAMES

# ======================================================================================
# SECTION A: Real headline-evidence retrieval from BP1-BP5's own real Gate 7 executive rollup
# manifests. Schema-agnostic by design (BP6's own stated principle, carried from Gate 2's
# evidence-source registry): each upstream BP's manifest has a DIFFERENT real schema (BP1-3 use
# "champion_model", BP4 uses "champion_pipeline", BP5 uses neither) - this reads whatever real
# top-level scalar fields each manifest actually has, rather than assuming a common one.
# ======================================================================================

# Metadata/structural fields present on every manifest that are not themselves evidentiary facts
# about a BP's real findings (a file path, a report label, a timestamp) - excluded uniformly
# across every BP, never as a BP-specific carve-out.
_EXCLUDED_METADATA_FIELDS = {
    "source_artifacts_dir",
    "report",
    "report_name",
    "generated_at_utc",
    "bp_id",
    "gate",
}


def retrieve_headline_evidence_bundle(
    project_root: Path, upstream_bp_ids: tuple[str, ...] = ("bp1", "bp2", "bp3", "bp4", "bp5")
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Opens each upstream BP's real `executive_rollup_manifest.json` (its own real Gate 7 output)
    and builds one citation record per real top-level scalar field found (excluding the
    non-evidentiary metadata fields above) — every field name, value, and source path is read
    directly from the real file, never invented or paraphrased. Returns (ordered list of citation
    records, {evidence_id: citation record} lookup for O(1) validation later). Raises
    FileNotFoundError naming the exact missing file if any upstream BP's real manifest does not
    exist yet — this gate never proceeds on a partial or assumed evidence set."""
    retrieval_timestamp_utc = datetime.now(timezone.utc).isoformat()
    citations: list[dict[str, Any]] = []
    n_by_bp: dict[str, int] = {}

    for bp_id in upstream_bp_ids:
        bp_name = UPSTREAM_BP_NAMES[bp_id]
        manifest_path = project_root / "notebooks" / bp_name / "artifacts" / "executive_rollup_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"{manifest_path} does not exist. Prerequisite: {bp_name}'s own real Gate 7 "
                "(Executive Rollup Report) must have run for real before BP6 Gate 5 can retrieve "
                "real evidence from it."
            )
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        rel_path = manifest_path.relative_to(project_root).as_posix()
        n = 0
        for field_name, value in manifest.items():
            if field_name in _EXCLUDED_METADATA_FIELDS:
                continue
            if not isinstance(value, (str, int, float, bool)):
                continue  # citation schema requires a single scalar extracted_value, never a list/dict
            evidence_id = f"EV-{bp_id.upper()}-{n + 1}"
            citations.append(
                {
                    "evidence_id": evidence_id,
                    "source_bp": bp_id,
                    "source_gate": 7,
                    "source_artifact_relative_path": rel_path,
                    "source_field_or_metric": field_name,
                    "extracted_value": value,
                    "retrieval_timestamp_utc": retrieval_timestamp_utc,
                    "verification_method": f"read directly from JSON key path '{field_name}' in "
                    f"{rel_path}",
                }
            )
            n += 1
        n_by_bp[bp_id] = n

    lookup = {c["evidence_id"]: c for c in citations}
    return citations, lookup


def select_real_narrative_sample(
    pii_screened_csv_path: Path,
    eligible_buckets: tuple[str, ...],
    random_state: int = 42,
) -> dict[str, Any]:
    """Deterministically selects ONE real customer-utterance row from Gate 2's own real,
    already-screened `gate2_pii_screened_narrative_text.csv` — never a fabricated customer
    message. Restricted to rows whose real `pii_detected` flag is False (defense in depth, even
    though Gate 2's own real run already confirmed 0/13,083 rows flagged) and whose real
    `common_taxonomy_bucket` is one of Gate 3/4's own real cross-corpus-hit buckets (so the
    selected example genuinely has real evidence retrievable on the other side of the CFPB<->
    BANKING77 divide — never a bucket where no counterpart evidence exists). Selection is
    reproducible (sorted by real text, then seeded sample of 1), not the CSV's on-disk row order,
    so re-running this function twice on unchanged real data returns the identical real row."""
    df = pd.read_csv(pii_screened_csv_path)
    eligible = df[
        (df["pii_detected"] == False)  # noqa: E712 - pandas Series comparison, not plain-Python truthiness
        & (df["common_taxonomy_bucket"].isin(eligible_buckets))
    ]
    if eligible.empty:
        raise ValueError(
            "No real PII-clear row found in any Gate 3/4 cross-corpus-hit bucket - cannot select "
            "a grounded narrative sample."
        )
    eligible_sorted = eligible.sort_values("masked_text").reset_index(drop=True)
    row = eligible_sorted.sample(n=1, random_state=random_state).iloc[0]
    return {
        "masked_text": row["masked_text"],
        "category": row["category"],
        "common_taxonomy_bucket": row["common_taxonomy_bucket"],
        "split": row["split"],
    }


# ======================================================================================
# SECTION B: Deterministic prompt assembly (the "deterministic template around GenAI") and the
# real, pluggable Google Gemini API call.
# ======================================================================================


def assemble_grounded_prompt(narrative_sample: dict[str, Any], citations: list[dict[str, Any]]) -> str:
    """Builds the deterministic prompt template. The model is given the real customer utterance
    and the REAL evidence bundle (each record's real evidence_id/source_bp/field/value), and is
    instructed to cite ONLY the evidence_ids provided — it is never given free rein to assert an
    unsourced fact. This is the "deterministic template" half of Master Plan paragraph 117's
    architecture; `validate_citations_in_generated_text` below is the other half (verifying the
    model actually complied)."""
    evidence_lines = "\n".join(
        f"  [{c['evidence_id']}] {c['source_bp'].upper()} (Gate {c['source_gate']}) - "
        f"{c['source_field_or_metric']}: {c['extracted_value']}"
        for c in citations
    )
    return (
        "You are drafting a short, grounded next-action recommendation for a customer service "
        "team member handling the real customer message below. Use ONLY the evidence items "
        "listed - do not state any fact, statistic, or claim that is not one of these evidence "
        "items. Cite every factual claim inline using its bracketed evidence ID exactly as given "
        "(e.g. [EV-BP1-1]). Do not guarantee any outcome, do not promise a specific result, and "
        "do not use absolute language ('always', 'never', 'guaranteed', 'risk-free'). Write "
        "2-4 sentences only. This draft will be reviewed by a human before any action is taken - "
        "do not claim the action has already been taken.\n\n"
        f"Real customer message (category: {narrative_sample['category']}, common taxonomy "
        f"bucket: {narrative_sample['common_taxonomy_bucket']}):\n"
        f'  "{narrative_sample["masked_text"]}"\n\n'
        f"Available evidence (cite ONLY these, by ID):\n{evidence_lines}\n"
    )


class MissingApiKeyError(RuntimeError):
    """Raised when GEMINI_API_KEY is not set. Never caught silently - this gate is built
    pluggable per explicit user decision (2026-09-24): the real call is fully wired, but a
    missing key must stop the run with a clear, disclosed error, never a fabricated response."""


def call_grounded_generation(
    prompt: str,
    api_key_env_var: str = "GEMINI_API_KEY",
    model_env_var: str = "GEMINI_MODEL",
    default_model: str = "gemini-3.5-flash",
    max_tokens: int = 400,
) -> dict[str, Any]:
    """Makes the real Google Gemini API call via the official `google-genai` SDK. Raises
    MissingApiKeyError with exact setup instructions if `api_key_env_var` is not set in the
    environment - this function NEVER returns a fabricated or stubbed response in that case. The
    model ID is read from `model_env_var` if set, else `default_model` - deliberately overridable,
    since exact current model IDs can change and this project's own standing rule is to never
    assert an unverified fact as certain; the user should confirm `default_model` is still a valid,
    current model ID for their account before the first real run, or set GEMINI_MODEL to override
    it (the free tier's Flash-family models are the ones documented as free-tier eligible as of
    this gate's own delivery)."""
    api_key = os.environ.get(api_key_env_var)
    if not api_key:
        raise MissingApiKeyError(
            f"{api_key_env_var} is not set. BP6 Gate 5 makes a real Google Gemini API call and "
            "will not fabricate a response in its place. To run this gate for real: (1) get a "
            "real, free Gemini API key from https://aistudio.google.com/apikey (Google AI Studio "
            "auto-creates a default project and key for you - no separate GCP billing setup is "
            "required for the free tier), (2) set it as an environment variable before starting "
            f'Jupyter, e.g. in Windows: `setx {api_key_env_var} "AIza..."` (then restart the '
            f'kernel), or for the current session only: `import os; os.environ["{api_key_env_var}"]'
            f' = "AIza..."` in a cell BEFORE this one. (3) Optionally set {model_env_var} to a '
            f"specific model ID if {default_model!r} is not current or not free-tier-eligible for "
            "your account - check https://ai.google.dev/gemini-api/docs/pricing for the current "
            "free-tier model list. No artifact and no config block are written by this gate until "
            "a real call succeeds."
        )
    # Imported here, not at module top, so every earlier-gate style import of this module (e.g. a
    # future notebook that only needs Section A) never requires the google-genai package to be
    # installed unless this function is actually called. Caught explicitly (the same real gap this
    # module's own pre-delivery testing found under the prior Anthropic-based version: a bare
    # ModuleNotFoundError here would be cryptic - every other prerequisite failure in this project
    # gives a clear, actionable message, so this one does too) and re-raised with install
    # instructions, never swallowed or worked around.
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "The 'google-genai' package is not installed in this kernel. Install it before "
            "running this gate for real: pip install google-genai (or add it to requirements.txt "
            "and re-install). No artifact and no config block are written by this gate until a "
            "real call succeeds."
        ) from exc

    model = os.environ.get(model_env_var, default_model)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            # Real bug found on this module's own first real run (2026-09-24, user's actual
            # device): Gemini's "thinking" models spend part of max_output_tokens on invisible
            # reasoning tokens before writing any visible answer text - documented upstream
            # (googleapis/python-genai issue #782: "thinking spend has a floor of roughly two to
            # three thousand tokens before a single character of answer gets written"). With
            # thinking left at its default and max_output_tokens=400, the real run produced only
            # 13 visible output tokens - a truncated, broken sentence fragment ("' and is
            # recommended for production [EV-BP4-2].'") rather than the instructed 2-4 sentence
            # recommendation. This task (short, template-constrained, grounded summarization of a
            # fixed evidence bundle) does not need extended reasoning, so thinking is disabled
            # outright (thinking_budget=0) to guarantee the full token budget goes to the visible
            # answer. finish_reason is also now captured below and structurally checked by this
            # gate's own notebook (Section 11/15), so a future truncation is caught and refused
            # rather than silently written as a broken "recommendation."
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    generated_text = response.text or ""
    # Defensive extraction, not a guess presented as certain: the Gemini API's documented
    # UsageMetadata field names (prompt_token_count / candidates_token_count) are read via
    # getattr with a None fallback rather than direct attribute access, so a real SDK response
    # missing one of these (e.g. a future SDK version renaming a field) degrades to a disclosed
    # None in the artifact/config rather than crashing this gate after a real, billed-nothing but
    # still real API call has already succeeded.
    usage = getattr(response, "usage_metadata", None)
    input_tokens = getattr(usage, "prompt_token_count", None) if usage is not None else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage is not None else None
    # Gemini's generate_content response does not document a stable top-level response id the way
    # Anthropic's does - best-effort only, None if genuinely absent, never fabricated.
    response_id = getattr(response, "response_id", None)
    # finish_reason (e.g. "STOP" vs "MAX_TOKENS") - added after this module's own real first run
    # surfaced a silent-truncation bug (see the thinking_config comment above). Read defensively
    # from the first real candidate; None if genuinely absent rather than assumed "STOP".
    candidates = getattr(response, "candidates", None) or []
    finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    # Real bug caught by pre-delivery sandbox testing (2026-09-24, BP6 Gate 6 work): the real
    # google-genai SDK's FinishReason is a (str, Enum) member, so a bare `str(finish_reason)`
    # returns "FinishReason.MAX_TOKENS" (its __str__), NOT "MAX_TOKENS" - live-confirmed against
    # the installed SDK: `str(types.FinishReason.MAX_TOKENS) == "MAX_TOKENS"` is False, while
    # `types.FinishReason.MAX_TOKENS.name == "MAX_TOKENS"` is True. The already-delivered,
    # already real-run-confirmed Gate 5 notebook's own truncation-refusal check compares against
    # the bare string "MAX_TOKENS" - under the old str() cast, that comparison would have SILENTLY
    # NEVER matched a genuine future truncation (it happened not to matter on the real run so far,
    # since that run's real finish_reason was STOP, not MAX_TOKENS - the mismatch is cosmetic only
    # for a passing run, but would have silently defeated the truncation guard on a failing one).
    # Fixed here by reading `.name` when available (falls back to `str()` only for a value that is
    # not itself an enum member, e.g. a plain string from some other real code path).
    finish_reason = (
        finish_reason.name
        if finish_reason is not None and hasattr(finish_reason, "name")
        else (str(finish_reason) if finish_reason is not None else None)
    )
    return {
        "generated_text": generated_text,
        "model_used": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "response_id": response_id,
        "finish_reason": finish_reason,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ======================================================================================
# SECTION C: Structural anti-hallucination check - verifies every citation the model actually used
# resolves to a real evidence record. This is the enforcement half of paragraph 117's "no
# ungrounded generation is ever presented as a recommendation."
# ======================================================================================

_EVIDENCE_ID_PATTERN = re.compile(r"\[EV-[A-Z0-9]+-\d+\]")


def validate_citations_in_generated_text(
    generated_text: str, citation_lookup: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Extracts every `[EV-...]` tag literally present in the model's generated text and checks
    each one against the REAL citation lookup built in Section A. `invalid_evidence_ids_referenced`
    (a citation tag the model used that does not exist in the real bundle - i.e. the model
    invented or mis-cited something) is the core anti-hallucination signal; a non-empty list here
    means `passed=False` and this gate's own notebook must refuse to present the text as a
    finished recommendation."""
    referenced_raw = _EVIDENCE_ID_PATTERN.findall(generated_text)
    referenced_ids = sorted({tag.strip("[]") for tag in referenced_raw})
    valid_ids = [eid for eid in referenced_ids if eid in citation_lookup]
    invalid_ids = [eid for eid in referenced_ids if eid not in citation_lookup]
    return {
        "passed": len(invalid_ids) == 0 and len(referenced_ids) > 0,
        "n_citations_referenced": len(referenced_ids),
        "cited_evidence_ids": valid_ids,
        "invalid_evidence_ids_referenced": invalid_ids,
        "zero_citations_used": len(referenced_ids) == 0,
    }


# ======================================================================================
# SECTION D: UDAAP customer-facing-language review. BP6's own adaptation of the pattern BP5 Gate 5
# established (per-sentence scanning + single-quote masking so real quoted source text is never
# mistaken for this gate's own authored language) - BP6's banned-term list targets DECEPTIVE/
# MISLEADING customer-facing language (BP6 Gate 1's own policy.json: "reviewed for deceptive/
# misleading language"), not BP5's causal-claim language (BP5 is a root-cause report; BP6 is a
# customer-facing recommendation - different real risk, different real list). Written
# independently here rather than importing BP5's module, since each BP's own src/ subpackage is
# kept independent in this project (src/genai for BP6, src/models for BP5) - this is BP6's own
# compliance check, not a cross-BP dependency.
# ======================================================================================

UDAAP_BANNED_DECEPTIVE_PATTERNS: list[str] = [
    "guaranteed",
    "guarantee",
    "100% certain",
    "no risk",
    "risk-free",
    "risk free",
    "promise",
    "promises",
    "promised",
    "definitely will",
    "always works",
    "never fails",
    "act now",
    "limited time",
    "you must",
    "immediately resolve",
    "instantly fix",
    "fully resolve",
    "completely resolve",
]


def check_udaap_customer_facing_language(text: str) -> dict[str, Any]:
    """Mechanically scans `text` for banned deceptive/misleading customer-facing language
    (case-insensitive substring match), masking single-quoted spans first (this project's
    established convention for quoting real source text verbatim) so a real quoted customer
    message or evidence value is never mistaken for this gate's own authored language."""
    masked = re.sub(r"'[^']*'", "'<quoted-value>'", text)
    lowered = masked.lower()
    found = [p for p in UDAAP_BANNED_DECEPTIVE_PATTERNS if p in lowered]
    return {
        "passed": len(found) == 0,
        "banned_terms_found": found,
        "n_banned_matches": len(found),
        "n_chars_scanned": len(text),
    }


def check_udaap_customer_facing_language_batch(sentences: list[str]) -> dict[str, Any]:
    """Runs the single-text check on each sentence SEPARATELY and aggregates - same
    cross-sentence-quote-parity-bug avoidance BP5 Gate 5's own sandbox verification found and
    fixed (checking a joined blob lets one sentence's stray apostrophe silently un-mask another
    sentence's quoted content); checking each sentence independently removes that failure mode."""
    per_sentence = [check_udaap_customer_facing_language(s) for s in sentences]
    all_banned = sorted({t for r in per_sentence for t in r["banned_terms_found"]})
    failing = [
        {"sentence_index": i, "sentence": sentences[i], "banned_terms_found": r["banned_terms_found"]}
        for i, r in enumerate(per_sentence)
        if not r["passed"]
    ]
    return {
        "passed": len(failing) == 0,
        "n_sentences_scanned": len(sentences),
        "n_sentences_failing": len(failing),
        "failing_sentences": failing,
        "banned_terms_found": all_banned,
    }


def split_into_sentences(text: str) -> list[str]:
    """Simple, disclosed sentence splitter (on '.', '!', '?' followed by whitespace) - matches
    the granularity BP5 Gate 5's own UDAAP batch check operates at. Not a full NLP sentence
    tokenizer; adequate for this gate's own short (2-4 sentence), template-constrained output."""
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in raw if s]


# ======================================================================================
# SECTION E: NIST AI RMF risk-category computation. No official NIST-published LOW/MEDIUM/HIGH
# enum exists for this - Master Plan Section 9's own NIST AI RMF row only requires "a documented
# risk category" without specifying a scale. This project's own documented judgment (same status
# as taxonomy_mapping.yaml's own HIGH/MEDIUM/LOW confidence field: "a documented reasoning
# judgment, never invented as a computed metric"): a live, real, external customer-facing GenAI
# call is never categorized LOW in this project regardless of how many mitigations pass, since the
# underlying action (an LLM call producing customer-facing text) always carries some residual
# risk; MEDIUM only when every real structural mitigation below passed; HIGH if any did not.
# ======================================================================================


def compute_nist_ai_rmf_risk_category(
    citation_check_passed: bool,
    udaap_check_passed: bool,
    human_in_the_loop_enforced: bool,
    auto_apply_allowed: bool,
    pii_masking_applied_upstream: bool,
) -> dict[str, Any]:
    """Structurally computed from this gate's own real run facts (never a hardcoded value). All
    five real conditions must hold for MEDIUM (this project's floor for a live customer-facing
    GenAI call - never LOW); any single failure is HIGH."""
    mitigations = {
        "citation_check_passed": citation_check_passed,
        "udaap_check_passed": udaap_check_passed,
        "human_in_the_loop_enforced": human_in_the_loop_enforced,
        "auto_apply_forbidden": not auto_apply_allowed,
        "pii_masking_applied_upstream": pii_masking_applied_upstream,
    }
    all_passed = all(mitigations.values())
    category = "MEDIUM" if all_passed else "HIGH"
    return {
        "risk_category_value": category,
        "mitigations_checked": mitigations,
        "all_mitigations_passed": all_passed,
        "rationale": (
            "This project's own documented risk-tiering judgment, informed by NIST AI RMF's "
            "Govern/Map/Measure/Manage functions - not an official NIST-published category enum "
            "(no such enum exists in the framework). A live, real, customer-facing external LLM "
            "call is never categorized LOW here, regardless of how many mitigations pass; MEDIUM "
            "requires every real structural mitigation above to hold, computed fresh from this "
            "gate's own actual run, never assumed."
        ),
    }


# ======================================================================================
# SECTION F: Final deterministic-template-wrapped recommendation artifact. The model's raw text is
# NEVER presented alone - it is always wrapped with the full real citation table, the real
# structural check results, and an explicit pending-human-approval banner (Master Plan Section
# 5.1's own words, BP6 Gate 1's own policy: "No BP6 recommendation is ever applied, sent, or
# treated as final without an explicit human approval step"). This function does not decide
# whether the recommendation is fit to present - the caller (this gate's own notebook) checks
# citation_check['passed'] and udaap_check['passed'] and refuses to write this artifact at all if
# either failed, rather than writing a flagged-but-still-present artifact.
# ======================================================================================


def build_recommendation_artifact(
    narrative_sample: dict[str, Any],
    citations: list[dict[str, Any]],
    generation_result: dict[str, Any],
    citation_check: dict[str, Any],
    udaap_check: dict[str, Any],
    risk_category: dict[str, Any],
) -> dict[str, Any]:
    """Assembles the final artifact. `approval_status` is always "PENDING_HUMAN_REVIEW" and
    `auto_applied` is always False - this gate never applies, sends, or finalizes a
    recommendation; it only stages one for a human to review, exactly as BP6 Gate 1's own
    grounding_integrity_rules require."""
    return {
        "bp_id": "bp6",
        "gate": 5,
        "compliance_touchpoint": "UDAAP language review on customer-facing text; NIST AI RMF "
        "Measure/Manage check on BP6",
        "customer_message_context": {
            "real_source": "notebooks/bp6_genai_resolution_assistant/artifacts/"
            "gate2_pii_screened_narrative_text.csv (Gate 2's own real, PII-screened row)",
            "category": narrative_sample["category"],
            "common_taxonomy_bucket": narrative_sample["common_taxonomy_bucket"],
        },
        "generated_recommendation_text": generation_result["generated_text"],
        "model_used": generation_result["model_used"],
        "input_tokens": generation_result["input_tokens"],
        "output_tokens": generation_result["output_tokens"],
        "finish_reason": generation_result.get("finish_reason"),
        "citation_table": citations,
        "citation_check": citation_check,
        "udaap_check": udaap_check,
        "nist_ai_rmf_risk_category": risk_category,
        "approval_status": "PENDING_HUMAN_REVIEW",
        "auto_applied": False,
        "human_in_the_loop_required": True,
        "human_in_the_loop_auto_apply_allowed": False,
        "generated_at_utc": generation_result["generated_at_utc"],
    }
