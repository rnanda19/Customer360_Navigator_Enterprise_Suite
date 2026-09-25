"""
tests/bp6_genai_resolution_assistant/test_gate_artifacts.py — Customer360 Navigator

Schema / cross-artifact consistency checks over BP6's real, currently saved Gates 1-6 artifacts -
BP6's first-ever coverage of this kind, delivered at Gate 6, matching BP5's own
test_gate_artifacts.py precedent. Every test is SKIPPED (never failed) when the real artifact it
needs has not been produced yet by a real run - this file makes no network call and never
generates, mocks, or fabricates a substitute artifact; it only inspects what is really on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "PROJECT_STRUCTURE_LOCKED.md").exists():
            return candidate
    pytest.skip("Not running inside the Customer360 Navigator project tree.")


@pytest.fixture(scope="module")
def artifacts_dir(project_root: Path) -> Path:
    return project_root / "notebooks" / "bp6_genai_resolution_assistant" / "artifacts"


def _load_or_skip(path: Path, what: str) -> dict:
    if not path.exists():
        pytest.skip(f"{what} has not been run for real yet ({path} does not exist).")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------------------------
# Gate 5 recommendation artifact schema
# --------------------------------------------------------------------------------------------


def test_gate5_recommendation_artifact_has_required_fields(artifacts_dir):
    artifact = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    required_fields = {
        "bp_id",
        "gate",
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
    }
    missing = required_fields - set(artifact.keys())
    assert not missing, f"gate5 recommendation artifact is missing real fields: {missing}"


def test_gate5_recommendation_never_auto_applied(artifacts_dir):
    artifact = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    assert artifact["approval_status"] == "PENDING_HUMAN_REVIEW"
    assert artifact["auto_applied"] is False


def test_gate5_response_not_truncated(artifacts_dir):
    """Real regression test for the thinking-token truncation bug (issue #782): the currently
    saved real artifact must never carry finish_reason == MAX_TOKENS."""
    artifact = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    assert artifact.get("finish_reason") != "MAX_TOKENS"


def test_gate5_citation_and_udaap_checks_passed(artifacts_dir):
    artifact = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    assert artifact["citation_check"]["passed"] is True
    assert artifact["udaap_check"]["passed"] is True


def test_gate5_nist_risk_category_is_medium_or_high_never_low(artifacts_dir):
    artifact = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    assert artifact["nist_ai_rmf_risk_category"]["risk_category_value"] in ("MEDIUM", "HIGH")


def test_gate5_cited_evidence_ids_all_real(artifacts_dir):
    """No phantom evidence ID: every id the model actually cited must exist in the real citation
    table retrieved for that same run."""
    artifact = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    real_ids = {c["evidence_id"] for c in artifact["citation_table"]}
    cited_ids = set(artifact["citation_check"]["cited_evidence_ids"])
    assert cited_ids.issubset(real_ids)


# --------------------------------------------------------------------------------------------
# Cross-gate consistency
# --------------------------------------------------------------------------------------------


def test_gate3_gate4_champion_retrieval_strategy_agree(artifacts_dir):
    gate3 = _load_or_skip(
        artifacts_dir / "gate3_retrieval_strategy_inventory_entry.json", "BP6 Gate 3"
    )
    gate4 = _load_or_skip(artifacts_dir / "gate4_independent_validation_record.json", "BP6 Gate 4")
    assert gate4["champion_strategy_under_validation"] == gate3["champion_strategy"]


def test_gate4_independently_reproduces_gate3_coverage(artifacts_dir):
    gate3 = _load_or_skip(
        artifacts_dir / "gate3_retrieval_strategy_inventory_entry.json", "BP6 Gate 3"
    )
    gate4 = _load_or_skip(artifacts_dir / "gate4_independent_validation_record.json", "BP6 Gate 4")
    assert gate4["coverage_reproduces_exactly"] is True
    assert gate4["gate4_independently_reproduced_coverage"] == pytest.approx(gate3["champion_coverage"])


def test_gate2_pii_screen_clean(artifacts_dir):
    gate2 = _load_or_skip(artifacts_dir / "gate2_pii_screening_report.json", "BP6 Gate 2")
    assert gate2["n_rows_flagged"] == 0
    assert gate2["n_rows_screened"] > 0


def test_gate1_policy_declares_genai_call_at_gate5(artifacts_dir):
    gate1 = _load_or_skip(artifacts_dir / "policy.json", "BP6 Gate 1")
    assert gate1["scope_definition"]["genai_call_occurs_at_this_gate"] is False
    assert gate1["scope_definition"]["genai_call_first_occurs_at_gate"] == 5
    assert gate1["genai_usage_policy"]["human_in_the_loop"]["required"] is True
    assert gate1["genai_usage_policy"]["human_in_the_loop"]["auto_apply_allowed"] is False


# --------------------------------------------------------------------------------------------
# Gate 6's own governance artifacts
# --------------------------------------------------------------------------------------------


def test_gate6_governance_summary_reports_all_passed(artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate6_governance_summary.json", "BP6 Gate 6")
    assert summary["pytest_all_passed"] is True
    assert summary["notebook_syntax_all_passed"] is True
    assert summary["fastapi_self_test_identical"] is True


def test_gate6_self_test_result_is_never_presented_as_a_recommendation(artifacts_dir):
    """The self-test artifact must stay clearly scoped as a governance/testing record and must
    never overwrite or be confused with Gate 5's own customer-facing recommendation artifact."""
    self_test = _load_or_skip(artifacts_dir / "gate6_fastapi_self_test_result.json", "BP6 Gate 6")
    assert "approval_status" not in self_test
    assert self_test["self_test_identical"] is True

    recommendation = _load_or_skip(
        artifacts_dir / "gate5_recommendation_pending_human_review.json", "BP6 Gate 5"
    )
    assert recommendation["gate"] == 5  # Gate 5's own artifact, untouched by Gate 6


def test_gate6_config_block_and_report_files_exist(project_root, artifacts_dir):
    summary = _load_or_skip(artifacts_dir / "gate6_governance_summary.json", "BP6 Gate 6")
    model_card_path = project_root / summary["model_card_path"]
    changelog_path = project_root / summary["changelog_path"]
    assert model_card_path.exists(), f"{model_card_path} does not exist"
    assert changelog_path.exists(), f"{changelog_path} does not exist"
