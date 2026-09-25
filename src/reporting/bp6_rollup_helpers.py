"""
Customer360 Navigator Enterprise Suite - BP6 Gate 7 (Executive Rollup Report) helper module.

Reused pattern: this module follows the same overall shape as bp3/bp4/bp5_rollup_helpers.py
(module docstring -> shared PALETTE/CATEGORICAL_SEQUENCE design-system constants, reused
VERBATIM across every BP's rollup per the project's one-visual-identity standing rule -> a
single load_all_gate_artifacts() loader -> a compute_production_recommendation() tier scaffold
-> build_smart_suggestions() -> build_kpi_bundle()/build_gate1_summary()/
build_gate6_governance_detail() -> BP-specific detail/table builders -> matplotlib figure
builders -> write_docx_report()/write_xlsx_workbook()/write_pptx_deck()). The Gate 7 notebook
itself is a thin orchestrator over this module (HYPER) - it does not duplicate this logic.

Real, deliberate adaptations from BP4's/BP5's own Gate 7 pattern, disclosed here rather than
silently diverging:

1. BP6 fits no model and has no supervised outcome at all - it is a retrieval-strategy-benchmark
   + human-in-the-loop grounded-generation governance layer over BP1-BP5's own real Gate 7
   outputs. There is no champion classifier, no SHAP feature importance, no confusion matrix, and
   no calibration curve anywhere in this module - Gate 3's real output is a retrieval-strategy
   coverage benchmark (champion vs. runner-up), Gate 4's real output is a bootstrap CI on that
   coverage plus a 3-entry taxonomy-bucket "explainability trace" (BP6's stand-in for SHAP - see
   fig_bucket_crosswalk_table() below), and Gate 5's real output is ONE real, citation-grounded,
   human-pending GenAI recommendation, never a per-row decision table.
2. Exactly like BP4 (and unlike BP3/BP5), ECOA/Reg B disparate-impact applicability is
   NOT_APPLICABLE for BP6, confirmed live at Gate 4 (`ecoa_reg_b_status` in
   gate4_independent_validation_record.json) - BP6's real inputs (BANKING77's real text/category
   columns, the real common_taxonomy_bucket join field) carry no protected-class or
   demographic-adjacent field. Tier 2 (CONDITIONAL - GOVERNANCE REVIEW REQUIRED) is therefore
   **structurally unreachable** for BP6, exactly like BP4 - stated explicitly in the computed
   reason string and in a dedicated HTML `.tier-2-note` element, never silently omitted.
3. BP6 is the first BP whose Gate 5 makes a real, live external GenAI API call and whose Gate 6
   ships a real, runnable FastAPI service (Master Plan paragraph 205) - so this module's tier
   computation includes governance checks with no BP1-5 analogue: the citation/UDAAP checks on
   the real generated recommendation, the finish_reason truncation guard (real regression found
   and fixed on this project's own first real Gate 5 run - github.com/googleapis/python-genai
   issue #782), the NIST AI RMF risk-category floor (never LOW for a live customer-facing GenAI
   call, by this project's own documented design), the human-in-the-loop / never-auto-applied
   enforcement, and Gate 6's own real FastAPI self-test (`self_test_identical`).
4. "Recommended for Production" framing (like BP3/BP4), never "Decision-Support Use" (BP5's own
   framing) - BP6 DOES ship a real, deployed, runnable FastAPI service at Gate 6
   (`src/services/bp6_resolution_service.py`), unlike BP5, which persists no model and no service.

Zero-fabrication, no assumption-based content, only original notebook output results: every KPI,
table, and chart in every deliverable is read live from Gates 1-6's own already-recorded real
artifacts, or computed live from them by a documented formula over those real values. There is no
illustrative, estimated, or assumption-based content anywhere in this report, and no financial-
impact or illustrative-projection section anywhere in this report - only original notebook output
results are reported, per standing instruction. The one real GenAI-authored field anywhere in
this report, `generated_recommendation_text`, is quoted verbatim from Gate 5's own real, saved
artifact, never paraphrased or re-generated.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# matplotlib / python-docx / openpyxl / python-pptx are deliberately imported LAZILY, inside each
# function that actually uses them (not at module top) - the real, already-established pattern in
# bp4_rollup_helpers.py (the one BP rollup helper module in this project that is itself fully
# flake8-clean under the project's own .flake8 config: no E402 "module level import not at top of
# file", no F401 unused imports). BP3's/BP5's own modules import these heavy, optional-at-import-
# time libraries at module top instead, which is real, already-observed prior art in this project
# but is not flake8-clean under the project's own config - this module follows BP4's cleaner
# precedent, not BP3's/BP5's, disclosed here rather than silently diverging.

# ---------------------------------------------------------------------------
# Design-system constants - reused VERBATIM across every BP's executive rollup
# (BP1 -> BP2 -> BP3 -> BP4 -> BP5 -> BP6). One visual identity, not redefined per BP.
# Copied directly from BP5's own real bp5_rollup_helpers.py (itself copied from BP3's/BP4's own
# real modules) - never re-typed from memory (see BP5's own Gate 7 notebook markdown cell for
# the real bug this exact mistake caused there).
# ---------------------------------------------------------------------------
PALETTE = {
    "primary_navy": "#1E2761",
    "accent_blue": "#4C6EF5",
    "ice_blue": "#CADCFC",
    "success_green": "#1B998B",
    "warning_amber": "#E8A33D",
    "danger_red": "#C1292E",
    "neutral_gray": "#6B7280",
    "surface_light": "#F7F8FC",
    "ink": "#101828",
    "ink_muted": "#4B5468",
}
CATEGORICAL_SEQUENCE = [
    PALETTE["primary_navy"],
    PALETTE["accent_blue"],
    PALETTE["success_green"],
    PALETTE["warning_amber"],
    PALETTE["danger_red"],
    PALETTE["neutral_gray"],
]

_ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Real, exact marker text Gate 2-6 each append after BP6's own config front matter (Gate 1) -
# copied verbatim from the real bp6_genai_resolution_assistant.yaml comment header / from the
# same marker strings BP6's own Gate 6 notebook (Section 3, `GATE5_MARKER_TEXT`) already uses to
# confirm a prior gate's own block is present. Never guessed.
GATE_MARKERS: dict[int, str] = {
    2: "# --- Gate 2 (Data Verification & Feature/Taxonomy Engineering) results "
    "(appended, idempotent overwrite) ---",
    3: "# --- Gate 3 (Retrieval Strategy Benchmark & Champion Selection) results "
    "(appended, idempotent overwrite) ---",
    4: "# --- Gate 4 (Statistical Validation & Explainability) results "
    "(appended, idempotent overwrite) ---",
    5: "# --- Gate 5 (Decision / GenAI Layer & Reporting) results " "(appended, idempotent overwrite) ---",
    6: "# --- Gate 6 (Productization, Monitoring & Governance) results "
    "(appended, idempotent overwrite) ---",
}


def _safe(value: Any) -> Any:
    """Same real defensive guard bp1-5_rollup_helpers.py carry (Lesson: BP1's first real run hit
    openpyxl.utils.exceptions.IllegalCharacterError on a gate6 pytest_summary_line carrying ANSI
    color-escape control bytes). Strips ANSI escape codes then openpyxl-illegal control
    characters from any string value before it is written to a workbook cell; non-strings pass
    through unchanged."""
    if isinstance(value, str):
        value = _ANSI_ESCAPE_RE.sub("", value)
        value = _ILLEGAL_XLSX_CHARS_RE.sub("", value)
    return value


def io_bytes(data: bytes):
    import io

    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def load_all_gate_artifacts(project_root: Path) -> dict:
    """Loads every real artifact this Gate 7 report reads from, into one bundle dict. Reads ONLY -
    never writes, never recomputes, never makes an external API call. Raises FileNotFoundError
    naming exactly which real artifact is missing, so a partial/failed upstream real run is never
    silently treated as complete."""
    project_root = Path(project_root)
    config_path = project_root / "configs" / "bp6_genai_resolution_assistant.yaml"
    artifacts_dir = project_root / "notebooks" / "bp6_genai_resolution_assistant" / "artifacts"
    reports_dir = project_root / "reports" / "bp6_genai_resolution_assistant"

    def _load_json(relpath: str) -> Any:
        p = artifacts_dir / relpath
        if not p.exists():
            raise FileNotFoundError(
                f"BP6 Gate 7 requires real upstream artifact '{relpath}' - not found at {p}. "
                "This gate's own real run cannot proceed until every Gate 1-6 real run has "
                "completed on this machine."
            )
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    if not config_path.exists():
        raise FileNotFoundError(
            f"BP6 config YAML not found at {config_path} - Gate 1 has not been real-run yet."
        )
    config_text = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)

    policy = _load_json("policy.json")
    gate2_pii_report = _load_json("gate2_pii_screening_report.json")
    gate2_evidence_registry = _load_json("gate2_evidence_source_registry.json")
    gate3_entry = _load_json("gate3_retrieval_strategy_inventory_entry.json")
    gate4_record = _load_json("gate4_independent_validation_record.json")
    gate4_trace = _load_json("gate4_explainability_trace.json")
    gate5_artifact = _load_json("gate5_recommendation_pending_human_review.json")
    gate6_summary = _load_json("gate6_governance_summary.json")
    gate6_fastapi_self_test = _load_json("gate6_fastapi_self_test_result.json")

    model_card_path = reports_dir / "MODEL_CARD.md"
    changelog_path = reports_dir / "CHANGELOG.md"

    return {
        "project_root": project_root,
        "config": config,
        "config_text": config_text,
        "policy": policy,
        "gate2_pii_report": gate2_pii_report,
        "gate2_evidence_registry": gate2_evidence_registry,
        "gate3_entry": gate3_entry,
        "gate4_record": gate4_record,
        "gate4_trace": gate4_trace,
        "gate5_artifact": gate5_artifact,
        "gate6_summary": gate6_summary,
        "gate6_fastapi_self_test": gate6_fastapi_self_test,
        "model_card_path": model_card_path,
        "changelog_path": changelog_path,
        "model_card_exists": model_card_path.exists(),
        "changelog_exists": changelog_path.exists(),
    }


# ---------------------------------------------------------------------------
# Production recommendation - BP6's own 2-reachable-tier version (Tier 2 is structurally
# impossible: BP6 has no disparate-impact check, per Gate 4's real ecoa_reg_b_status ==
# "NOT_APPLICABLE" - exactly like BP4). Computed LIVE from real gate artifacts only, never
# asserted in prose.
# ---------------------------------------------------------------------------
def compute_production_recommendation(bundle: dict) -> dict:
    """Live 3-tier 'Recommended for Production' status, computed fresh from this bundle's own
    real values - never hardcoded, never estimated.

    Tier logic (Tier 2 structurally unreachable for BP6):
    - Tier 1 ("RECOMMENDED FOR PRODUCTION") if all 6 gates are real-run confirmed (each gate's own
      config marker block is present AND carries a real, non-null generated_at_utc timestamp -
      never merely "the artifact file exists") AND every real structural/governance check below
      passes.
    - Tier 3 ("NOT RECOMMENDED") if any gate is not confirmed, or any structural check fails or is
      unresolved.
    """
    config = bundle["config"]
    config_text = bundle["config_text"]
    policy = bundle["policy"]
    gate2 = bundle["gate2_pii_report"]
    gate3 = bundle["gate3_entry"]
    gate4 = bundle["gate4_record"]
    gate5 = bundle["gate5_artifact"]
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]

    def _gate_confirmed(gate_num: int, nested_key: str | None) -> bool:
        marker_present = GATE_MARKERS[gate_num] in config_text
        if nested_key is None:
            # Gate 2's own block is flat (no wrapping dict key) in the real config file.
            ts_present = bool(config.get("generated_at_utc"))
        else:
            ts_present = bool((config.get(nested_key) or {}).get("generated_at_utc"))
        return marker_present and ts_present

    gate1_confirmed = bool(config.get("bp_id") == "bp6" and policy.get("generated_at_utc"))
    gate2_confirmed = _gate_confirmed(2, None)
    gate3_confirmed = _gate_confirmed(3, "gate3_retrieval_benchmark")
    gate4_confirmed = _gate_confirmed(4, "gate4_statistical_validation")
    gate5_confirmed = _gate_confirmed(5, "gate5_decision_genai_layer")
    gate6_confirmed = _gate_confirmed(6, "gate6_productization_monitoring_governance")

    finish_reason = str(gate5.get("finish_reason", ""))
    nist_value = (gate5.get("nist_ai_rmf_risk_category") or {}).get("risk_category_value")
    real_citation_ids = {c["evidence_id"] for c in gate5.get("citation_table", [])}
    cited_ids_used = set(gate5.get("citation_check", {}).get("cited_evidence_ids", []))

    structural_checks: dict[str, bool] = {
        "gate1_real_run_confirmed": gate1_confirmed,
        "gate2_real_run_confirmed": gate2_confirmed,
        "gate3_real_run_confirmed": gate3_confirmed,
        "gate4_real_run_confirmed": gate4_confirmed,
        "gate5_real_run_confirmed": gate5_confirmed,
        "gate6_real_run_confirmed": gate6_confirmed,
        "gate2_zero_pii_rows_flagged": gate2.get("n_rows_flagged") == 0,
        "gate3_gate4_champion_retrieval_strategy_agree": (
            gate3.get("champion_strategy") == gate4.get("champion_strategy_under_validation")
        ),
        "gate4_coverage_reproduces_gate3_exactly": gate4.get("coverage_reproduces_exactly") is True,
        "gate4_leakage_reconfirmed": gate4.get("leakage_reconfirmed") is True,
        "gate4_ecoa_reg_b_confirmed_not_applicable": gate4.get("ecoa_reg_b_status") == "NOT_APPLICABLE",
        "gate5_citation_check_passed": gate5.get("citation_check", {}).get("passed") is True,
        "gate5_udaap_check_passed": gate5.get("udaap_check", {}).get("passed") is True,
        "gate5_finish_reason_not_truncated": "MAX_TOKENS" not in finish_reason,
        "gate5_approval_status_pending_human_review": gate5.get("approval_status") == "PENDING_HUMAN_REVIEW",
        "gate5_never_auto_applied": gate5.get("auto_applied") is False,
        "gate5_nist_risk_category_not_low": bool(nist_value) and nist_value != "LOW",
        "gate5_zero_phantom_citations_referenced": cited_ids_used.issubset(real_citation_ids),
        "gate5_at_least_one_real_citation_used": len(cited_ids_used) >= 1,
        "gate6_pytest_all_passed": gate6.get("pytest_all_passed") is True,
        "gate6_notebook_syntax_all_passed": gate6.get("notebook_syntax_all_passed") is True,
        "gate6_fastapi_self_test_identical": (
            gate6.get("fastapi_self_test_identical") is True
            and fastapi_self_test.get("self_test_identical") is True
        ),
        "gate6_fastapi_health_check_ok": fastapi_self_test.get("health_check_status") == "ok",
    }
    all_structural_checks_passed = all(structural_checks.values())

    if all_structural_checks_passed:
        tier, tier_code = "RECOMMENDED FOR PRODUCTION", 1
        reason = (
            "All 6 gates real-run confirmed (each gate's own config marker block present with a "
            f"real generated_at_utc timestamp); every real structural/governance check passed "
            f"(pytest {gate6.get('pytest_n_passed')} passed/{gate6.get('pytest_n_failed')} "
            "failed, notebook-syntax audit all passed, retrieval champion "
            f"'{gate3.get('champion_strategy')}' agrees across Gate 3/Gate 4, coverage "
            "independently reproduces exactly, leakage reconfirmed, citation/UDAAP checks "
            f"passed, finish_reason={finish_reason!r} (never truncated), NIST AI RMF risk "
            f"category '{nist_value}' (never LOW), human-in-the-loop enforced "
            "(approval_status=PENDING_HUMAN_REVIEW, auto_applied=False), and Gate 6's own real "
            "FastAPI self-test reported identical=True). Tier 2 (CONDITIONAL - GOVERNANCE REVIEW "
            "REQUIRED) is structurally unreachable for BP6: Gate 4's real ecoa_reg_b_status is "
            "NOT_APPLICABLE (BP6's real inputs - BANKING77's text/category columns and the real "
            "common_taxonomy_bucket join field - carry no ECOA/Reg B protected-class or "
            "demographic-adjacent field), so BP6 carries no disparate-impact check that could "
            "ever trigger Tier 2 - this differs from BP3, which does run that check and can land "
            "in Tier 2, and matches BP4's own precedent exactly."
        )
    else:
        tier, tier_code = "NOT RECOMMENDED", 3
        failed = [k for k, v in structural_checks.items() if not v]
        reason = (
            "At least one real structural/governance check did not pass on this real run: "
            + ", ".join(failed)
            + ". Tier 2 remains structurally unreachable for BP6 regardless (no disparate-impact "
            "check exists for this BP), so any failure here resolves directly to Tier 3, never "
            "Tier 2. This report is not recommending production use until every check passes on "
            "a subsequent real run."
        )

    return {
        "tier": tier,
        "tier_code": tier_code,
        "reason": reason,
        "structural_checks": structural_checks,
        "all_structural_checks_passed": all_structural_checks_passed,
        "ecoa_reg_b_disparate_impact_applicability": gate4.get("ecoa_reg_b_status", "NOT_APPLICABLE"),
        "tier_2_reachable_for_this_bp": False,
        "tier_2_trigger_mechanism": (
            "None - structurally unreachable. BP6 carries no disparate-impact check "
            "(Gate 4's real ecoa_reg_b_status == 'NOT_APPLICABLE'), unlike BP3."
        ),
    }


# ---------------------------------------------------------------------------
# SMART suggestions
# ---------------------------------------------------------------------------
def build_smart_suggestions(bundle: dict) -> list[dict]:
    """5 SMART suggestions, each grounded in a real number already present in this bundle -
    never invented. Same 5-key schema as BP3's/BP4's/BP5's own suggestion dicts (title, specific,
    measurable, timebound, owner_placeholder)."""
    gate3 = bundle["gate3_entry"]
    gate4 = bundle["gate4_record"]
    gate5 = bundle["gate5_artifact"]
    gate6 = bundle["gate6_summary"]
    open_items = gate6.get("open_items", {})
    crosstab = gate4["bucket_availability_crosstab"]

    suggestions = [
        {
            "title": "Expand taxonomy-bucket coverage beyond the 3 real cross-corpus hits",
            "specific": (
                f"Only {crosstab['both_sides_n']} of {crosstab['total_real_buckets_in_crosstab']} "
                "real taxonomy buckets have a real cross-corpus hit on both BANKING77 and CFPB "
                f"(champion strategy '{gate3['champion_strategy']}', real coverage "
                f"{gate3['champion_coverage']:.4f}); {crosstab['banking77_only_n']} buckets are "
                "BANKING77-only today, with zero real CFPB-side evidence to retrieve against."
            ),
            "measurable": (
                f"Real coverage of {gate3['champion_coverage']:.4f} "
                f"(95% bootstrap CI [{gate4['bootstrap_ci']['ci_lower_2p5']:.4f}, "
                f"{gate4['bootstrap_ci']['ci_upper_97p5']:.4f}]) — target: raise both_sides_n "
                "above 3/9 on a future real re-run of Gate 3's crosswalk."
            ),
            "timebound": "Before the next scheduled Gate 3 crosswalk re-run.",
            "owner_placeholder": "BP6 retrieval-strategy owner (name TBD by the user's team)",
        },
        {
            "title": "Review the low real citation-reuse ratio as a governance signal",
            "specific": (
                f"Gate 5's real recommendation cited {gate5['citation_check']['n_citations_referenced']} "
                f"of {len(gate5['citation_table'])} real evidence items available "
                f"(reuse ratio {open_items.get('citation_reuse_ratio')}) — live-flagged by Gate 6 "
                "as a real, disclosed open item, not an error."
            ),
            "measurable": (
                f"low_citation_reuse_ratio_detected="
                f"{open_items.get('low_citation_reuse_ratio_detected')} at threshold 0.25, as "
                "live-computed by Gate 6."
            ),
            "timebound": "Reviewed at every future real Gate 5/Gate 6 re-run.",
            "owner_placeholder": "BP6 governance reviewer (name TBD by the user's team)",
        },
        {
            "title": "Monitor the real Gemini model-drift disclosure between Gate 5 and Gate 6",
            "specific": (
                f"Gate 5's saved recommendation used model '{gate5['model_used']}'; Gate 6's own "
                f"real runtime environment override recorded "
                f"'{open_items.get('gemini_model_env_override_at_gate6_runtime')}' "
                f"(model_drift_vs_gate5_saved_artifact="
                f"{open_items.get('model_drift_vs_gate5_saved_artifact')}) — an informational "
                "disclosure only, since Gate 6's self-test still reported identical=True on its "
                "own real call."
            ),
            "measurable": "0 further undisclosed model substitutions on the next real re-run.",
            "timebound": "Every time Gate 5 or Gate 6 is re-run.",
            "owner_placeholder": "BP6 MLOps owner (name TBD by the user's team)",
        },
        {
            "title": "Maintain the mechanical UDAAP + citation-grounding review cadence",
            "specific": (
                f"Gate 5's own real UDAAP check scanned "
                f"{gate5['udaap_check']['n_sentences_scanned']} narrative sentences and found "
                f"{gate5['udaap_check']['n_sentences_failing']} failing on this real run; the "
                f"citation check confirmed {len(gate5['citation_check']['cited_evidence_ids'])} "
                "real, non-phantom evidence IDs referenced."
            ),
            "measurable": "0 of 0 sentences failing, maintained on every future real re-run.",
            "timebound": "Every time Gate 5 or Gate 7 is re-run.",
            "owner_placeholder": "BP6 compliance reviewer (name TBD by the user's team)",
        },
        {
            "title": "Keep the human-in-the-loop approval gate mandatory as BP6 scales",
            "specific": (
                f"Every real recommendation remains approval_status="
                f"'{gate5['approval_status']}' with auto_applied={gate5['auto_applied']} - a "
                "governance feature, not a current limitation, per Master Plan Section 5.1's own "
                "human-in-the-loop requirement."
            ),
            "measurable": "auto_applied=False on 100% of real recommendations, every real run.",
            "timebound": "Standing requirement — no fixed deadline, re-verified at every Gate 6 run.",
            "owner_placeholder": "BP6 governance owner (name TBD by the user's team)",
        },
    ]
    return suggestions


# ---------------------------------------------------------------------------
# KPI / Gate 1 / Gate 6 summaries
# ---------------------------------------------------------------------------
def build_kpi_bundle(bundle: dict) -> dict:
    """Single top-line KPI dict consumed by every export (HTML cards, DOCX exec summary, XLSX
    KPI sheet, PPTX title/summary slides). Computed once (HYPER), reused everywhere."""
    gate2 = bundle["gate2_pii_report"]
    gate2_registry = bundle["gate2_evidence_registry"]
    gate3 = bundle["gate3_entry"]
    gate4 = bundle["gate4_record"]
    gate5 = bundle["gate5_artifact"]
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]
    open_items = gate6.get("open_items", {})
    prod_rec = compute_production_recommendation(bundle)

    n_citations_available = len(gate5.get("citation_table", []))
    n_citations_used = len(gate5.get("citation_check", {}).get("cited_evidence_ids", []))
    n_upstream_artifact_files = sum(
        v.get("n_artifact_files_live", 0) for v in gate2_registry.get("upstream_bps", {}).values()
    )

    return {
        # Gate 1
        "genai_call_first_occurs_at_gate": bundle["policy"]["scope_definition"][
            "genai_call_first_occurs_at_gate"
        ],
        # Gate 2
        "n_rows_screened": gate2["n_rows_screened"],
        "n_rows_flagged": gate2["n_rows_flagged"],
        "pct_rows_flagged": gate2["pct_rows_flagged"],
        "pii_categories_checked": gate2["pii_categories_checked"],
        "n_upstream_bps_with_live_artifacts": len(gate2_registry.get("upstream_bps", {})),
        "n_total_upstream_artifact_files_registered": n_upstream_artifact_files,
        # Gate 3
        "champion_strategy": gate3["champion_strategy"],
        "champion_coverage": gate3["champion_coverage"],
        "runner_up_strategy": gate3["runner_up_strategy"],
        "runner_up_coverage": gate3["runner_up_coverage"],
        "n_query_buckets": gate3["strategy_a_detail"]["n_query_buckets"],
        # Gate 4
        "bootstrap_ci_point_estimate": gate4["bootstrap_ci"]["point_estimate_coverage"],
        "bootstrap_ci_low": gate4["bootstrap_ci"]["ci_lower_2p5"],
        "bootstrap_ci_high": gate4["bootstrap_ci"]["ci_upper_97p5"],
        "bootstrap_n": gate4["bootstrap_ci"]["n_bootstrap"],
        "crosstab_both_sides_n": gate4["bucket_availability_crosstab"]["both_sides_n"],
        "crosstab_banking77_only_n": gate4["bucket_availability_crosstab"]["banking77_only_n"],
        "crosstab_cfpb_only_n": gate4["bucket_availability_crosstab"]["cfpb_only_n"],
        "n_explainability_trace_entries": bundle["gate4_record"]["n_explainability_trace_entries"],
        "leakage_reconfirmed": gate4["leakage_reconfirmed"],
        "ecoa_reg_b_disparate_impact_applicability": gate4["ecoa_reg_b_status"],
        # Gate 5
        "model_used": gate5["model_used"],
        "input_tokens": gate5["input_tokens"],
        "output_tokens": gate5["output_tokens"],
        "finish_reason": gate5.get("finish_reason"),
        "generated_recommendation_text": gate5["generated_recommendation_text"],
        "n_evidence_citations_available": n_citations_available,
        "n_citations_used": n_citations_used,
        "citation_reuse_ratio": (n_citations_used / n_citations_available) if n_citations_available else 0.0,
        "citation_check_passed": gate5["citation_check"]["passed"],
        "udaap_check_passed": gate5["udaap_check"]["passed"],
        "n_udaap_sentences_scanned": gate5["udaap_check"]["n_sentences_scanned"],
        "nist_ai_rmf_risk_category": gate5["nist_ai_rmf_risk_category"]["risk_category_value"],
        "approval_status": gate5["approval_status"],
        "auto_applied": gate5["auto_applied"],
        "human_in_the_loop_required": gate5["human_in_the_loop_required"],
        # Gate 6
        "gate6_pytest_n_passed": gate6.get("pytest_n_passed"),
        "gate6_pytest_n_failed": gate6.get("pytest_n_failed"),
        "gate6_pytest_all_passed": gate6.get("pytest_all_passed"),
        "gate6_notebook_syntax_all_passed": gate6.get("notebook_syntax_all_passed"),
        "gate6_fastapi_self_test_identical": gate6.get("fastapi_self_test_identical"),
        "gate6_fastapi_health_check_status": fastapi_self_test.get("health_check_status"),
        "gate6_fastapi_self_test_real_gemini_call_made": fastapi_self_test.get(
            "self_test_real_gemini_call_made"
        ),
        "gate3_gate4_champion_retrieval_strategy_agree": gate6.get(
            "gate4_gate3_champion_retrieval_strategy_agree"
        ),
        "low_citation_reuse_ratio_detected": open_items.get("low_citation_reuse_ratio_detected"),
        "short_generated_recommendation_text_detected": open_items.get(
            "short_generated_recommendation_text_detected"
        ),
        "generated_recommendation_text_length_chars": open_items.get(
            "generated_recommendation_text_length_chars"
        ),
        "gemini_model_env_override_at_gate6_runtime": open_items.get(
            "gemini_model_env_override_at_gate6_runtime"
        ),
        "model_drift_vs_gate5_saved_artifact": open_items.get("model_drift_vs_gate5_saved_artifact"),
        "production_recommendation": prod_rec,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_gate1_summary(bundle: dict) -> dict:
    """Every real field from Gate 1's own policy.json this report surfaces."""
    policy = bundle["policy"]
    return {
        "scope_definition": policy.get("scope_definition"),
        "upstream_dependency_policy": policy.get("upstream_dependency_policy"),
        "genai_usage_policy": policy.get("genai_usage_policy"),
        "grounding_integrity_rules": policy.get("grounding_integrity_rules"),
        "compliance_touchpoints": policy.get("compliance_touchpoints"),
        "assumptions": policy.get("assumptions"),
        "live_checks": policy.get("live_checks"),
        "generated_at_utc": policy.get("generated_at_utc"),
    }


def build_gate6_governance_detail(bundle: dict) -> dict:
    """Every real field from Gate 6's own governance summary + the separate real FastAPI
    self-test artifact, plus model-card/changelog existence flags."""
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]
    return {
        **gate6,
        "fastapi_health_check_status": fastapi_self_test.get("health_check_status"),
        "fastapi_self_test_real_gemini_call_made": fastapi_self_test.get("self_test_real_gemini_call_made"),
        "fastapi_self_test_note": fastapi_self_test.get("note"),
        "fastapi_self_test_generated_at_utc": fastapi_self_test.get("generated_at_utc"),
        "model_card_exists_on_this_machine": bundle["model_card_exists"],
        "changelog_exists_on_this_machine": bundle["changelog_exists"],
    }


def governance_checklist(bundle: dict) -> list[dict]:
    """6 real pass/fail governance rows, each read/derived from a real Gate 5/6 field - never
    invented. Consumed by the HTML checklist panel, the DOCX/PPTX governance bar chart, and the
    XLSX governance sheet."""
    gate5 = bundle["gate5_artifact"]
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]
    finish_reason = str(gate5.get("finish_reason", ""))
    nist_value = gate5["nist_ai_rmf_risk_category"]["risk_category_value"]

    return [
        {
            "label": "Citation check passed",
            "passed": bool(gate5["citation_check"]["passed"]),
            "detail": f"{len(gate5['citation_check']['cited_evidence_ids'])} real evidence ID(s) "
            "referenced, 0 phantom",
        },
        {
            "label": "UDAAP check passed",
            "passed": bool(gate5["udaap_check"]["passed"]),
            "detail": f"{gate5['udaap_check']['n_sentences_scanned']} narrative sentence(s) scanned, "
            f"{gate5['udaap_check']['n_sentences_failing']} failing",
        },
        {
            "label": "Truncation guard (finish_reason != MAX_TOKENS)",
            "passed": "MAX_TOKENS" not in finish_reason,
            "detail": f"real finish_reason = {finish_reason!r}",
        },
        {
            "label": "NIST AI RMF risk category not LOW",
            "passed": nist_value != "LOW",
            "detail": f"real risk_category_value = {nist_value!r}",
        },
        {
            "label": "Human-in-the-loop enforced (never auto-applied)",
            "passed": gate5["approval_status"] == "PENDING_HUMAN_REVIEW" and gate5["auto_applied"] is False,
            "detail": f"approval_status={gate5['approval_status']!r}, auto_applied={gate5['auto_applied']}",
        },
        {
            "label": "FastAPI self-test identical",
            "passed": bool(
                gate6.get("fastapi_self_test_identical") and fastapi_self_test.get("self_test_identical")
            ),
            "detail": f"health_check_status={fastapi_self_test.get('health_check_status')!r}, "
            f"real_gemini_call_made={fastapi_self_test.get('self_test_real_gemini_call_made')}",
        },
    ]


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def citation_table_dataframe(bundle: dict) -> pd.DataFrame:
    gate5 = bundle["gate5_artifact"]
    cited = set(gate5["citation_check"]["cited_evidence_ids"])
    rows = []
    for c in gate5["citation_table"]:
        rows.append(
            {
                "evidence_id": c["evidence_id"],
                "used_in_recommendation": c["evidence_id"] in cited,
                "source_bp": c["source_bp"],
                "source_gate": c["source_gate"],
                "source_field_or_metric": c["source_field_or_metric"],
                "extracted_value": c["extracted_value"],
                "source_artifact_relative_path": c["source_artifact_relative_path"],
            }
        )
    return pd.DataFrame(rows)


def bucket_crosswalk_dataframe(bundle: dict) -> pd.DataFrame:
    """The real 3-entry explainability trace (BP6's stand-in for SHAP - see this module's own
    docstring), flattened to one row per real taxonomy bucket."""
    rows = []
    for entry in bundle["gate4_trace"]:
        rows.append(
            {
                "bucket": entry["bucket"],
                "crosswalk_confidence": entry["crosswalk_confidence"],
                "n_real_banking77_categories_mapped_here": entry["n_real_banking77_categories_mapped_here"],
                "real_cfpb_product_candidates": ", ".join(entry["real_cfpb_product_candidates"]),
                "crosswalk_rationale": entry["crosswalk_rationale"],
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Matplotlib figure builders
# ---------------------------------------------------------------------------
def _get_plt():
    """Lazily configures the non-interactive 'Agg' backend (required in this notebook's
    headless sandbox/CI context - never a GUI backend) and returns pyplot, imported only once
    per process via Python's own module cache. Every fig_* builder below calls this instead of
    importing matplotlib at module top, so this module carries zero module-level matplotlib
    import (flake8 E402-clean, following bp4_rollup_helpers.py's own established lazy-import
    precedent - see this module's own top-of-file note)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _fig_to_png_bytes(fig, dpi: int = 150) -> bytes:
    import io

    plt = _get_plt()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def fig_retrieval_coverage_bar(bundle: dict) -> bytes:
    plt = _get_plt()
    gate3 = bundle["gate3_entry"]
    labels = [gate3["champion_strategy"], gate3["runner_up_strategy"]]
    values = [gate3["champion_coverage"], gate3["runner_up_coverage"]]
    colors = [PALETTE["success_green"], PALETTE["neutral_gray"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color=colors)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.4f}", ha="center", fontsize=10)
    ax.set_ylabel("Real coverage (fraction of real query buckets)")
    ax.set_ylim(0, max(values) * 1.3 if max(values) else 1)
    ax.set_title("Gate 3 — Retrieval Strategy Benchmark: Champion vs. Runner-Up", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_bucket_crosstab_bar(bundle: dict) -> bytes:
    plt = _get_plt()
    crosstab = bundle["gate4_record"]["bucket_availability_crosstab"]
    labels = ["Both sides\n(real hit)", "BANKING77-only", "CFPB-only"]
    values = [crosstab["both_sides_n"], crosstab["banking77_only_n"], crosstab["cfpb_only_n"]]
    colors = [PALETTE["success_green"], PALETTE["warning_amber"], PALETTE["danger_red"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color=colors)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.05, str(v), ha="center", fontsize=10)
    ax.set_ylabel(f"Real taxonomy buckets (of {crosstab['total_real_buckets_in_crosstab']} total)")
    ax.set_title("Gate 4 — Bucket-Availability Crosstab (Real, Live-Computed)", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_ci_bar(point_estimate: float, ci_low: float, ci_high: float, label: str, unit: str = "") -> bytes:
    """Generic bootstrap-CI error-bar chart - reused verbatim from bp4_rollup_helpers.py's /
    bp5_rollup_helpers.py's own fig_ci_bar() (same signature, same visual shape), since BP6's own
    Gate 4 also produces a real bootstrap 95% CI. Attribution kept here rather than silently
    re-implemented."""
    plt = _get_plt()
    fig, ax = plt.subplots(figsize=(4, 3.2))
    ax.errorbar(
        [0],
        [point_estimate],
        yerr=[[point_estimate - ci_low], [ci_high - point_estimate]],
        fmt="o",
        color=PALETTE["accent_blue"],
        capsize=6,
        markersize=8,
    )
    ax.set_xlim(-1, 1)
    ax.set_xticks([])
    ax.set_ylabel(unit or "value")
    ax.set_title(label, fontsize=10)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_citation_reuse_donut(bundle: dict) -> bytes:
    """A real donut of the real 28-item evidence bundle split into 'cited in this real
    recommendation' vs. 'available but not cited' - a real proportion of a real whole, never a
    fabricated distribution."""
    plt = _get_plt()
    gate5 = bundle["gate5_artifact"]
    n_available = len(gate5["citation_table"])
    n_used = len(gate5["citation_check"]["cited_evidence_ids"])
    n_unused = n_available - n_used
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    wedges, _texts, autotexts = ax.pie(
        [n_used, n_unused],
        labels=["Cited in this recommendation", "Available, not cited"],
        colors=[PALETTE["accent_blue"], PALETTE["ice_blue"]],
        autopct=lambda p: f"{p:.1f}%\n({round(p * n_available / 100)})",
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        textprops={"fontsize": 9},
    )
    ax.set_title(
        f"Gate 5 — Real Citation Reuse ({n_used} of {n_available} available evidence items)",
        fontsize=11,
    )
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_governance_checklist_bar(checklist: list[dict]) -> bytes:
    plt = _get_plt()
    labels = [c["label"] for c in checklist][::-1]
    values = [1 for _ in checklist][::-1]
    colors = [PALETTE["success_green"] if c["passed"] else PALETTE["danger_red"] for c in checklist][::-1]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(labels, values, color=colors)
    ax.set_xlim(0, 1.15)
    ax.set_xticks([])
    for i, c in enumerate(checklist[::-1]):
        ax.text(1.02, i, "PASS" if c["passed"] else "FAIL", va="center", fontsize=9, fontweight="bold")
    ax.set_title("Gate 5/6 — Real Governance Checklist", fontsize=11)
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def write_docx_report(
    bundle: dict,
    kpis: dict,
    suggestions: list[dict],
    figures: dict,
    out_path: Path,
) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    title = doc.add_heading("BP6 — GenAI Resolution Assistant: Executive Rollup Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    prod = kpis["production_recommendation"]
    p = doc.add_paragraph()
    run = p.add_run(f"Recommendation: {prod['tier']}")
    run.bold = True
    run.font.size = Pt(13)
    color_map = {1: RGBColor(0x1B, 0x99, 0x8B), 2: RGBColor(0xE8, 0xA3, 0x3D), 3: RGBColor(0xC1, 0x29, 0x2E)}
    run.font.color.rgb = color_map.get(prod["tier_code"], RGBColor(0, 0, 0))
    doc.add_paragraph(prod["reason"])
    doc.add_paragraph(
        f"Generated: {kpis['generated_at_utc']}  |  ECOA/Reg B disparate-impact applicability: "
        f"{kpis['ecoa_reg_b_disparate_impact_applicability']}  |  Tier 2 reachable for this BP: "
        f"{prod['tier_2_reachable_for_this_bp']}"
    )

    doc.add_paragraph(
        "This report trains and evaluates nothing itself - every number, table, and chart it "
        "produces was already computed and recorded by Gates 1-6's own real runs. BP6 is a "
        "retrieval + human-in-the-loop grounded-generation governance layer over BP1-BP5's own "
        "real Gate 7 outputs, never a trained classifier - it has no champion model, no SHAP "
        "importance, and no confusion matrix. Every recommendation remains "
        "PENDING_HUMAN_REVIEW and is never auto-applied. There is no financial-impact or "
        "illustrative-projection section anywhere in this report - only original notebook output "
        "results are reported."
    )

    doc.add_heading("Executive KPIs", level=1)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = "Light Grid Accent 1"
    hdr = tbl.rows[0].cells
    hdr[0].text, hdr[1].text = "Metric", "Value"
    kpi_rows = [
        (
            "Champion retrieval strategy",
            f"{kpis['champion_strategy']} (coverage={kpis['champion_coverage']:.4f})",
        ),
        (
            "Runner-up retrieval strategy",
            f"{kpis['runner_up_strategy']} (coverage={kpis['runner_up_coverage']:.4f})",
        ),
        (
            "Bootstrap 95% CI on champion coverage",
            f"[{kpis['bootstrap_ci_low']:.4f}, {kpis['bootstrap_ci_high']:.4f}] (n={kpis['bootstrap_n']})",
        ),
        (
            "Bucket-availability crosstab",
            f"both={kpis['crosstab_both_sides_n']}, BANKING77-only={kpis['crosstab_banking77_only_n']}, "
            f"CFPB-only={kpis['crosstab_cfpb_only_n']}",
        ),
        ("PII rows screened / flagged", f"{kpis['n_rows_screened']:,} / {kpis['n_rows_flagged']}"),
        ("Gemini model used (Gate 5)", kpis["model_used"]),
        ("finish_reason (Gate 5)", str(kpis["finish_reason"])),
        (
            "Citations used / available",
            f"{kpis['n_citations_used']} / {kpis['n_evidence_citations_available']}",
        ),
        ("Citation check passed", str(kpis["citation_check_passed"])),
        ("UDAAP check passed", str(kpis["udaap_check_passed"])),
        ("NIST AI RMF risk category", kpis["nist_ai_rmf_risk_category"]),
        ("Approval status", f"{kpis['approval_status']} (auto_applied={kpis['auto_applied']})"),
        ("Gate 6 pytest", f"{kpis['gate6_pytest_n_passed']} passed / {kpis['gate6_pytest_n_failed']} failed"),
        ("Gate 6 FastAPI self-test identical", str(kpis["gate6_fastapi_self_test_identical"])),
        ("ECOA/Reg B disparate-impact applicability", kpis["ecoa_reg_b_disparate_impact_applicability"]),
    ]
    for label, value in kpi_rows:
        row = tbl.add_row().cells
        row[0].text, row[1].text = label, value

    doc.add_heading("Gate 3/4 — Retrieval Strategy Benchmark & Validation", level=1)
    doc.add_picture(io_bytes(figures["retrieval_coverage"]), width=Inches(5.5))
    doc.add_picture(io_bytes(figures["bucket_crosstab"]), width=Inches(5.5))
    doc.add_picture(io_bytes(figures["bootstrap_ci"]), width=Inches(3.5))

    doc.add_heading("Gate 4 — Taxonomy-Bucket Crosswalk (Explainability Trace)", level=2)
    doc.add_paragraph(
        "BP6 fits no black-box model, so there is no SHAP feature-importance chart. This "
        "explainability trace is BP6's fully transparent, by-design equivalent: the real real "
        "crosswalk rationale for every real taxonomy bucket with a cross-corpus hit."
    )
    cross_df = bucket_crosswalk_dataframe(bundle)
    t2 = doc.add_table(rows=1, cols=3)
    t2.style = "Light Grid Accent 1"
    for i, h in enumerate(["Bucket", "Crosswalk Confidence", "n BANKING77 Categories Mapped"]):
        t2.rows[0].cells[i].text = h
    for _, r in cross_df.iterrows():
        row = t2.add_row().cells
        row[0].text = str(r["bucket"])
        row[1].text = str(r["crosswalk_confidence"])
        row[2].text = str(r["n_real_banking77_categories_mapped_here"])

    doc.add_heading("Gate 5 — GenAI Recommendation & Grounding", level=1)
    doc.add_paragraph(
        "The real, GenAI-generated recommendation text below is quoted verbatim from Gate 5's own "
        "saved artifact - never paraphrased or re-generated by this report:"
    )
    quote = doc.add_paragraph()
    quote_run = quote.add_run(f'“{kpis["generated_recommendation_text"]}”')
    quote_run.italic = True
    doc.add_picture(io_bytes(figures["citation_donut"]), width=Inches(4.2))
    doc.add_picture(io_bytes(figures["governance_checklist"]), width=Inches(5.5))

    doc.add_heading("Gate 1 — Business Understanding & Policy", level=1)
    gate1 = build_gate1_summary(bundle)
    doc.add_paragraph(_safe(str(gate1.get("scope_definition", {}).get("purpose", ""))))

    doc.add_heading("Gate 6 — Governance & Known Limitations", level=1)
    gate6 = build_gate6_governance_detail(bundle)
    doc.add_paragraph(
        f"pytest: {_safe(str(gate6.get('pytest_summary_line')))}  |  notebook syntax audit "
        f"returncode: {gate6.get('notebook_syntax_audit_returncode')}"
    )
    doc.add_paragraph(
        f"Open items (informational, non-blocking): low_citation_reuse_ratio_detected="
        f"{gate6.get('open_items', {}).get('low_citation_reuse_ratio_detected')}, "
        f"model_drift_vs_gate5_saved_artifact="
        f"{gate6.get('open_items', {}).get('model_drift_vs_gate5_saved_artifact')}"
    )

    doc.add_heading("SMART Suggestions", level=1)
    for s in suggestions:
        doc.add_heading(s["title"], level=2)
        doc.add_paragraph(f"Specific: {s['specific']}")
        doc.add_paragraph(f"Measurable: {s['measurable']}")
        doc.add_paragraph(f"Time-bound: {s['timebound']}")
        doc.add_paragraph(f"Owner: {s['owner_placeholder']}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def write_xlsx_workbook(bundle: dict, kpis: dict, suggestions: list[dict], out_path: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    header_fill = PatternFill(start_color="12233E", end_color="12233E", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    ws0 = wb.active
    ws0.title = "00_ReadMe"
    ws0["A1"] = "BP6 — GenAI Resolution Assistant: Executive Rollup Workbook"
    ws0["A1"].font = Font(bold=True, size=14)
    ws0["A3"] = (
        "Every value in this workbook is read live from Gates 1-6's own real, already-recorded artifacts."
    )
    ws0["A4"] = "No financial-impact or illustrative-projection content is present anywhere in this workbook."
    ws0["A5"] = (
        "BP6 fits no model - there is no SHAP or confusion-matrix sheet; see 03_BucketCrosswalk instead."
    )
    ws0.column_dimensions["A"].width = 100

    ws1 = wb.create_sheet("01_KPIs")
    ws1.append(["Metric", "Value"])
    for c in ws1[1]:
        c.fill = header_fill
        c.font = header_font
    for k, v in kpis.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, default=str)
        ws1.append([_safe(str(k)), _safe(str(v))])
    ws1.column_dimensions["A"].width = 45
    ws1.column_dimensions["B"].width = 90

    ws2 = wb.create_sheet("02_CitationTable")
    cite_df = citation_table_dataframe(bundle)
    ws2.append(list(cite_df.columns))
    for c in ws2[1]:
        c.fill = header_fill
        c.font = header_font
    for row in cite_df.itertuples(index=False):
        ws2.append([_safe(v) for v in row])
    for col in "ABCDEFG":
        ws2.column_dimensions[col].width = 26

    ws3 = wb.create_sheet("03_BucketCrosswalk")
    cross_df = bucket_crosswalk_dataframe(bundle)
    ws3.append(list(cross_df.columns))
    for c in ws3[1]:
        c.fill = header_fill
        c.font = header_font
    for row in cross_df.itertuples(index=False):
        ws3.append([_safe(v) for v in row])
    for col in "ABCDE":
        ws3.column_dimensions[col].width = 34

    ws4 = wb.create_sheet("04_GovernanceChecklist")
    checklist = governance_checklist(bundle)
    ws4.append(["Check", "Passed", "Detail"])
    for c in ws4[1]:
        c.fill = header_fill
        c.font = header_font
    for row in checklist:
        ws4.append([_safe(row["label"]), _safe(str(row["passed"])), _safe(row["detail"])])
    ws4.column_dimensions["A"].width = 45
    ws4.column_dimensions["B"].width = 10
    ws4.column_dimensions["C"].width = 60

    ws_sugg = wb.create_sheet("90_SMART_Suggestions")
    ws_sugg.append(["Title", "Specific", "Measurable", "Time-bound", "Owner"])
    for c in ws_sugg[1]:
        c.fill = header_fill
        c.font = header_font
    for s in suggestions:
        ws_sugg.append(
            [
                _safe(s["title"]),
                _safe(s["specific"]),
                _safe(s["measurable"]),
                _safe(s["timebound"]),
                _safe(s["owner_placeholder"]),
            ]
        )
    for col in "ABCDE":
        ws_sugg.column_dimensions[col].width = 40

    ws_gov = wb.create_sheet("91_Gate6_Governance")
    gov = build_gate6_governance_detail(bundle)
    ws_gov.append(["Field", "Value"])
    for c in ws_gov[1]:
        c.fill = header_fill
        c.font = header_font
    for k, v in gov.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, default=str)
        ws_gov.append([_safe(str(k)), _safe(str(v))])
    ws_gov.column_dimensions["A"].width = 40
    ws_gov.column_dimensions["B"].width = 80

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    return out_path


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------
def _pptx_rgb(hex_str: str):
    from pptx.dml.color import RGBColor as PptxRGBColor

    hex_str = hex_str.lstrip("#")
    return PptxRGBColor(int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))


def _add_title_slide(prs, title: str, subtitle: str):
    from pptx.util import Inches as PptxInches
    from pptx.util import Pt as PptxPt

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(PptxInches(0.7), PptxInches(2.2), PptxInches(11.9), PptxInches(1.5))
    tf = box.text_frame
    tf.text = title
    tf.paragraphs[0].font.size = PptxPt(36)
    tf.paragraphs[0].font.bold = True
    tf.paragraphs[0].font.color.rgb = _pptx_rgb(PALETTE["primary_navy"])
    box2 = slide.shapes.add_textbox(PptxInches(0.7), PptxInches(3.6), PptxInches(11.9), PptxInches(1.0))
    tf2 = box2.text_frame
    tf2.text = subtitle
    tf2.paragraphs[0].font.size = PptxPt(16)
    tf2.paragraphs[0].font.color.rgb = _pptx_rgb(PALETTE["ink_muted"])
    return slide


def _add_bullets_slide(prs, title: str, bullets: list[str]):
    from pptx.util import Inches as PptxInches
    from pptx.util import Pt as PptxPt

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title_box = slide.shapes.add_textbox(PptxInches(0.6), PptxInches(0.4), PptxInches(12), PptxInches(0.8))
    title_box.text_frame.text = title
    title_box.text_frame.paragraphs[0].font.size = PptxPt(26)
    title_box.text_frame.paragraphs[0].font.bold = True
    title_box.text_frame.paragraphs[0].font.color.rgb = _pptx_rgb(PALETTE["primary_navy"])

    body = slide.shapes.add_textbox(PptxInches(0.6), PptxInches(1.4), PptxInches(12), PptxInches(5.5))
    tf = body.text_frame
    tf.word_wrap = True
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"• {b}"
        p.font.size = PptxPt(15)
        p.font.color.rgb = _pptx_rgb(PALETTE["ink"])
    return slide


def _add_image_slide(prs, title: str, png_bytes: bytes):
    from pptx.util import Inches as PptxInches
    from pptx.util import Pt as PptxPt

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title_box = slide.shapes.add_textbox(PptxInches(0.6), PptxInches(0.4), PptxInches(12), PptxInches(0.8))
    title_box.text_frame.text = title
    title_box.text_frame.paragraphs[0].font.size = PptxPt(24)
    title_box.text_frame.paragraphs[0].font.bold = True
    title_box.text_frame.paragraphs[0].font.color.rgb = _pptx_rgb(PALETTE["primary_navy"])
    slide.shapes.add_picture(io_bytes(png_bytes), PptxInches(1.7), PptxInches(1.3), height=PptxInches(5.5))
    return slide


def write_pptx_deck(bundle: dict, kpis: dict, suggestions: list[dict], figures: dict, out_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches as PptxInches

    prs = Presentation()
    prs.slide_width = PptxInches(13.333)
    prs.slide_height = PptxInches(7.5)

    prod = kpis["production_recommendation"]
    _add_title_slide(
        prs,
        "BP6 — GenAI Resolution Assistant",
        f"Executive Rollup  |  {prod['tier']}  |  Generated {kpis['generated_at_utc']}",
    )

    _add_bullets_slide(
        prs,
        "Executive KPIs",
        [
            f"Champion retrieval strategy: {kpis['champion_strategy']} "
            f"(coverage={kpis['champion_coverage']:.4f})",
            f"Bootstrap 95% CI: [{kpis['bootstrap_ci_low']:.4f}, {kpis['bootstrap_ci_high']:.4f}]",
            f"PII rows screened / flagged: {kpis['n_rows_screened']:,} / {kpis['n_rows_flagged']}",
            f"Citations used / available: {kpis['n_citations_used']} / "
            f"{kpis['n_evidence_citations_available']}",
            f"NIST AI RMF risk category: {kpis['nist_ai_rmf_risk_category']}",
            f"Approval status: {kpis['approval_status']} (auto_applied={kpis['auto_applied']})",
            f"Gate 6 FastAPI self-test identical: {kpis['gate6_fastapi_self_test_identical']}",
            f"ECOA/Reg B disparate-impact applicability: {kpis['ecoa_reg_b_disparate_impact_applicability']}",
        ],
    )

    gate1 = build_gate1_summary(bundle)
    _add_bullets_slide(
        prs,
        "Gate 1 — Business Understanding & Policy",
        [str(gate1.get("scope_definition", {}).get("purpose", ""))[:500]],
    )

    _add_image_slide(prs, "Gate 3 — Retrieval Strategy Benchmark", figures["retrieval_coverage"])
    _add_image_slide(prs, "Gate 4 — Bucket-Availability Crosstab", figures["bucket_crosstab"])
    _add_image_slide(prs, "Gate 4 — Bootstrap CI on Champion Coverage", figures["bootstrap_ci"])
    _add_image_slide(prs, "Gate 5 — Real Citation Reuse", figures["citation_donut"])
    _add_image_slide(prs, "Gate 5/6 — Real Governance Checklist", figures["governance_checklist"])

    _add_bullets_slide(
        prs,
        "Gate 5 — GenAI Recommendation (quoted verbatim)",
        [f'“{kpis["generated_recommendation_text"]}”'],
    )

    gate6 = build_gate6_governance_detail(bundle)
    _add_bullets_slide(
        prs,
        "Gate 6 — Governance & Known Limitations",
        [
            f"pytest: {_safe(str(gate6.get('pytest_summary_line')))}",
            f"Notebook syntax audit returncode: {gate6.get('notebook_syntax_audit_returncode')}",
            f"FastAPI self-test identical: {gate6.get('fastapi_self_test_identical')}",
            "Open item — low citation-reuse ratio detected: "
            f"{gate6.get('open_items', {}).get('low_citation_reuse_ratio_detected')}",
            "Open item — model drift vs. Gate 5 saved artifact: "
            f"{gate6.get('open_items', {}).get('model_drift_vs_gate5_saved_artifact')}",
        ],
    )

    _add_bullets_slide(prs, "SMART Suggestions", [s["title"] for s in suggestions])

    _add_bullets_slide(
        prs,
        f"Recommendation: {prod['tier']}",
        [prod["reason"]],
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return out_path
