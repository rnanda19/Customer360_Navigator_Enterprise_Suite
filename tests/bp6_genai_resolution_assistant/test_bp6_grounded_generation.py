"""
tests/bp6_genai_resolution_assistant/test_bp6_grounded_generation.py — Customer360 Navigator

BP6's first-ever unit test coverage of `src/genai/bp6_grounded_generation.py`'s pure functions -
delivered at Gate 6 (Productization, Monitoring & Governance), matching every other BP's own
"first-ever test coverage delivered at Gate 6" precedent (e.g. BP5's
test_bp5_driver_association.py). Covers every function that takes no live network dependency:
citation validation, UDAAP language checks, sentence splitting, NIST AI RMF risk categorization,
prompt assembly, and artifact building. `call_grounded_generation()` itself (the one function that
makes a real, live external call) is exercised instead by
`tests/services/test_bp6_resolution_service.py`, with the network mocked at the
`google.genai.Client` boundary - never a real call in this file either.
"""

from __future__ import annotations

from genai.bp6_grounded_generation import (
    assemble_grounded_prompt,
    build_recommendation_artifact,
    check_udaap_customer_facing_language,
    check_udaap_customer_facing_language_batch,
    compute_nist_ai_rmf_risk_category,
    split_into_sentences,
    validate_citations_in_generated_text,
)

CITATIONS = [
    {
        "evidence_id": "EV-BP1-1",
        "source_bp": "bp1",
        "source_gate": 7,
        "source_artifact_relative_path": "notebooks/bp1_customer_intent_classification/artifacts/"
        "executive_rollup_manifest.json",
        "source_field_or_metric": "headline_metric_a",
        "extracted_value": 0.95,
        "retrieval_timestamp_utc": "2026-09-24T00:00:00+00:00",
        "verification_method": "read directly from JSON key path 'headline_metric_a'",
    },
    {
        "evidence_id": "EV-BP2-1",
        "source_bp": "bp2",
        "source_gate": 7,
        "source_artifact_relative_path": "notebooks/bp2_customer_friction_classification/artifacts/"
        "executive_rollup_manifest.json",
        "source_field_or_metric": "headline_metric_a",
        "extracted_value": 0.88,
        "retrieval_timestamp_utc": "2026-09-24T00:00:00+00:00",
        "verification_method": "read directly from JSON key path 'headline_metric_a'",
    },
]
CITATION_LOOKUP = {c["evidence_id"]: c for c in CITATIONS}

NARRATIVE_SAMPLE = {
    "masked_text": "My card was charged twice for the same purchase.",
    "category": "card_payment_wrong_exchange_rate",
    "common_taxonomy_bucket": "bucket_a",
    "split": "train",
}


# --------------------------------------------------------------------------------------------
# validate_citations_in_generated_text
# --------------------------------------------------------------------------------------------


def test_validate_citations_all_real_and_used():
    text = "A monetary-relief resolution is appropriate [EV-BP1-1]. Timelines follow the process [EV-BP2-1]."
    result = validate_citations_in_generated_text(text, CITATION_LOOKUP)
    assert result["passed"] is True
    assert set(result["cited_evidence_ids"]) == {"EV-BP1-1", "EV-BP2-1"}
    assert result["invalid_evidence_ids_referenced"] == []
    assert result["n_citations_referenced"] == 2


def test_validate_citations_rejects_phantom_id():
    text = "This is grounded in evidence [EV-BP9-1]."
    result = validate_citations_in_generated_text(text, CITATION_LOOKUP)
    assert result["passed"] is False
    assert "EV-BP9-1" in result["invalid_evidence_ids_referenced"]


def test_validate_citations_rejects_zero_citations():
    text = "This recommendation cites nothing at all."
    result = validate_citations_in_generated_text(text, CITATION_LOOKUP)
    assert result["passed"] is False
    assert result["n_citations_referenced"] == 0


def test_validate_citations_accepts_single_real_citation():
    text = "Escalation is warranted here [EV-BP1-1]."
    result = validate_citations_in_generated_text(text, CITATION_LOOKUP)
    assert result["passed"] is True
    assert result["cited_evidence_ids"] == ["EV-BP1-1"]


# --------------------------------------------------------------------------------------------
# split_into_sentences / UDAAP checks
# --------------------------------------------------------------------------------------------


def test_split_into_sentences_basic():
    sentences = split_into_sentences("First sentence. Second sentence! Third one?")
    assert sentences == ["First sentence.", "Second sentence!", "Third one?"]


def test_udaap_single_sentence_clean_passes():
    result = check_udaap_customer_facing_language("A resolution is recommended based on the evidence.")
    assert result["passed"] is True
    assert result["banned_terms_found"] == []


def test_udaap_single_sentence_absolute_language_fails():
    result = check_udaap_customer_facing_language("You are guaranteed a full refund immediately.")
    assert result["passed"] is False
    assert "guaranteed" in " ".join(result["banned_terms_found"]).lower()


def test_udaap_batch_passes_when_every_sentence_clean():
    sentences = ["A resolution is recommended.", "Please review the details before proceeding."]
    result = check_udaap_customer_facing_language_batch(sentences)
    assert result["passed"] is True


def test_udaap_batch_fails_when_any_sentence_dirty():
    sentences = ["A resolution is recommended.", "This is a risk-free guarantee."]
    result = check_udaap_customer_facing_language_batch(sentences)
    assert result["passed"] is False


# --------------------------------------------------------------------------------------------
# compute_nist_ai_rmf_risk_category
# --------------------------------------------------------------------------------------------


def test_nist_risk_category_medium_when_all_mitigations_pass():
    result = compute_nist_ai_rmf_risk_category(
        citation_check_passed=True,
        udaap_check_passed=True,
        human_in_the_loop_enforced=True,
        auto_apply_allowed=False,
        pii_masking_applied_upstream=True,
    )
    assert result["risk_category_value"] == "MEDIUM"
    assert result["all_mitigations_passed"] is True


def test_nist_risk_category_high_when_citation_check_fails():
    result = compute_nist_ai_rmf_risk_category(
        citation_check_passed=False,
        udaap_check_passed=True,
        human_in_the_loop_enforced=True,
        auto_apply_allowed=False,
        pii_masking_applied_upstream=True,
    )
    assert result["risk_category_value"] == "HIGH"


def test_nist_risk_category_high_when_auto_apply_allowed():
    """auto_apply_allowed=True flips auto_apply_forbidden to False - this project's own design
    never allows LOW, and never allows auto-apply to coexist with MEDIUM."""
    result = compute_nist_ai_rmf_risk_category(
        citation_check_passed=True,
        udaap_check_passed=True,
        human_in_the_loop_enforced=True,
        auto_apply_allowed=True,
        pii_masking_applied_upstream=True,
    )
    assert result["risk_category_value"] == "HIGH"
    assert result["mitigations_checked"]["auto_apply_forbidden"] is False


def test_nist_risk_category_never_low():
    """Every real combination of these 5 booleans yields only MEDIUM or HIGH - LOW does not exist
    as a reachable value, matching this project's own documented design floor."""
    from itertools import product

    for combo in product([True, False], repeat=5):
        result = compute_nist_ai_rmf_risk_category(*combo)
        assert result["risk_category_value"] in ("MEDIUM", "HIGH")


# --------------------------------------------------------------------------------------------
# assemble_grounded_prompt
# --------------------------------------------------------------------------------------------


def test_assemble_grounded_prompt_includes_message_and_all_citations():
    prompt = assemble_grounded_prompt(NARRATIVE_SAMPLE, CITATIONS)
    assert NARRATIVE_SAMPLE["masked_text"] in prompt
    assert "EV-BP1-1" in prompt
    assert "EV-BP2-1" in prompt
    assert "2-4 sentences" in prompt


def test_assemble_grounded_prompt_instructs_no_guarantees():
    prompt = assemble_grounded_prompt(NARRATIVE_SAMPLE, CITATIONS)
    assert "do not guarantee" in prompt.lower() or "guaranteed" in prompt.lower()


# --------------------------------------------------------------------------------------------
# build_recommendation_artifact
# --------------------------------------------------------------------------------------------


def _fake_generation_result(text="Escalation is warranted [EV-BP1-1].", finish_reason="STOP"):
    return {
        "generated_text": text,
        "model_used": "gemini-3.5-flash",
        "input_tokens": 500,
        "output_tokens": 40,
        "response_id": "fake-id",
        "finish_reason": finish_reason,
        "generated_at_utc": "2026-09-24T00:00:00+00:00",
    }


def test_build_recommendation_artifact_shape_and_never_auto_applied():
    generation_result = _fake_generation_result()
    citation_check = validate_citations_in_generated_text(generation_result["generated_text"], CITATION_LOOKUP)
    udaap_check = check_udaap_customer_facing_language_batch(
        split_into_sentences(generation_result["generated_text"])
    )
    risk_category = compute_nist_ai_rmf_risk_category(
        citation_check_passed=citation_check["passed"],
        udaap_check_passed=udaap_check["passed"],
        human_in_the_loop_enforced=True,
        auto_apply_allowed=False,
        pii_masking_applied_upstream=True,
    )
    artifact = build_recommendation_artifact(
        NARRATIVE_SAMPLE, CITATIONS, generation_result, citation_check, udaap_check, risk_category
    )
    assert artifact["approval_status"] == "PENDING_HUMAN_REVIEW"
    assert artifact["auto_applied"] is False
    assert artifact["human_in_the_loop_required"] is True
    assert artifact["human_in_the_loop_auto_apply_allowed"] is False
    assert artifact["finish_reason"] == "STOP"
    assert artifact["generated_recommendation_text"] == generation_result["generated_text"]
    assert artifact["citation_table"] == CITATIONS


def test_build_recommendation_artifact_preserves_finish_reason_field():
    """Regression test for the real thinking-token-truncation bug (issue #782): the artifact must
    always carry finish_reason so downstream gates can structurally detect MAX_TOKENS truncation."""
    generation_result = _fake_generation_result(text=" and is recommended [EV-BP1-1].", finish_reason="MAX_TOKENS")
    citation_check = validate_citations_in_generated_text(generation_result["generated_text"], CITATION_LOOKUP)
    udaap_check = check_udaap_customer_facing_language_batch(
        split_into_sentences(generation_result["generated_text"])
    )
    risk_category = compute_nist_ai_rmf_risk_category(
        citation_check_passed=citation_check["passed"],
        udaap_check_passed=udaap_check["passed"],
        human_in_the_loop_enforced=True,
        auto_apply_allowed=False,
        pii_masking_applied_upstream=True,
    )
    artifact = build_recommendation_artifact(
        NARRATIVE_SAMPLE, CITATIONS, generation_result, citation_check, udaap_check, risk_category
    )
    assert artifact["finish_reason"] == "MAX_TOKENS"
