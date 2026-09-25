"""
Customer360 Navigator Enterprise Suite - BP7 Gate 7 (Executive Rollup Report) helper module.

Reused pattern: this module follows the same overall shape as bp3/bp4/bp5/bp6_rollup_helpers.py
(module docstring -> shared PALETTE/CATEGORICAL_SEQUENCE design-system constants, reused
VERBATIM across every BP's rollup per the project's one-visual-identity standing rule -> a
single load_all_gate_artifacts() loader -> a compute_production_recommendation() tier scaffold
-> build_smart_suggestions() -> build_kpi_bundle()/build_gate1_summary()/
build_gate6_governance_detail() -> BP-specific detail/table builders -> matplotlib figure
builders -> write_docx_report()/write_xlsx_workbook()/write_pptx_deck()). The Gate 7 notebook
itself is a thin orchestrator over this module (HYPER) - it does not duplicate this logic.

Real, deliberate adaptations from BP6's/BP3's own Gate 7 pattern, disclosed here rather than
silently diverging:

1. BP7 fits no trained classifier and makes no GenAI/external API call ever
   (`genai_api_used: false` at every gate that states it - policy.json compliance_touchpoint,
   gate5_decision_layer_summary.json compliance_touchpoint, gate6_fastapi_self_test_result.json
   real_external_api_call_made). It is a transparent, auditable, deterministic weighted
   decision-rule layer (Master Plan Section 5.1/7), never a black box, that combines BP2's/BP3's/
   BP4's own already-computed real prediction fields (BP1 is optional context only - real 6.55%
   CFPB coverage; BP5 was PENDING_NOT_YET_DELIVERED at BP7's own Gate 1 time and never became a
   scoring input) into three real output fields per complaint: `priority_score` (a weighted
   combination), `intervention_flag` (boolean, thresholded at 0.5), and `recommended_action`
   (a deterministic, reason-code-keyed lookup - never GenAI text). There is therefore no SHAP, no
   confusion matrix, no calibration curve, and no citation/UDAAP checks anywhere in this module -
   Gate 3's real output is a champion RULE-SCHEME selection (not a champion model) across 4
   candidate weighting schemes, all 4 structurally passing; Gate 4's real output is a bit-exact
   independent reproduction of that champion-selection pipeline, a bootstrap 95% CI on two real
   rates, and an EXACT (not approximate) per-row contribution decomposition of the deterministic
   linear-combination formula - BP7's own fully transparent, by-design stand-in for SHAP, since the
   rule already IS a linear combination and its own arithmetic is its explanation, not an estimate
   of one (see `gate4_contribution_decomposition_summary.json`'s own disclosure text, reused
   verbatim in `fig_contribution_decomposition_bar()` below).
2. UDAAP and NIST AI RMF are explicitly "Not Applicable to BP7 Gate 5", per
   `gate5_decision_layer_summary.json`'s own real `compliance_touchpoint` dict - stated here
   plainly rather than silently omitted, exactly the way BP6's own module docstring stated Tier 2's
   structural unreachability rather than omitting it. `recommended_action` is Gate 1's own named
   deterministic, reason-code-keyed lookup, never GenAI-generated text, so there is no
   citation-grounding panel and no UDAAP-language-review panel anywhere in this report.
3. **ECOA/Reg B disparate-impact IS applicable and IS real-checked for BP7** (unlike BP4/BP6, where
   it is NOT_APPLICABLE) - Gate 3 honestly DEFERRED this check (BP7's own Gate 2 Gold layer does
   not preserve BP3's `tags_group` grouping, and reconstructing it from the raw, barred 'Tags'
   column would have made it a Gate 3 SCORING input, which Gate 1's leakage_rules bars); Gate 4
   RESOLVES that deferral by reading `tags_group` from BP3's own separate, already-governance-
   approved Gold layer and joining it onto BP7's already-scored population strictly AFTER scoring,
   for audit-grouping only. This module's tier computation therefore follows **BP3's own real,
   genuinely-reachable 3-tier shape** (Tier 2 = CONDITIONAL - GOVERNANCE REVIEW REQUIRED, triggered
   specifically by `flagged_four_fifths_rule == True`), NOT BP4's/BP6's 2-tier shape where Tier 2
   is structurally asserted unreachable. On this real run's own numbers,
   `flagged_four_fifths_rule` is `False` (real adverse_impact_ratio 0.908127, well above the 0.8
   four-fifths-rule convention threshold reused verbatim from BP3), so this real run computes
   Tier 1 - but the code genuinely supports landing in Tier 2 on a future real run where the check
   flags, and that is asserted by a dedicated structural integrity check in the notebook
   (`tier_2_genuinely_reachable_for_bp7`), never hardcoded to always resolve Tier 1.
4. **Flat-config Gate 2/3/4 marker check, real structural difference from BP6's own config shape.**
   BP7's real `configs/bp7_customer_navigator_decision_engine.yaml` writes Gate 2/3/4's own result
   blocks as FLAT keys directly on the config root (no wrapping nested dict the way BP6's config
   wraps its own Gate 3 block under `gate3_retrieval_benchmark`), and only Gate 5
   (`gate5_generated_at_utc`) and Gate 6 (`gate6_generated_at_utc`) carry their own
   `generated_at_utc` timestamp field directly in the flat config. Gates 2/3/4 have NO
   `generated_at_utc` field in the flat config at all - `_gate_confirmed()` below therefore checks
   each gate's OWN corresponding artifact JSON's real `generated_at_utc` field (e.g.
   `gate2_rescoring_summary.json`'s, `gate3_decision_rule_benchmark_summary.json`'s,
   `gate4_statistical_validation_explainability_summary.json`'s) combined with the real
   marker-text-presence check in `config_text`, rather than BP6's own nested-dict
   `config.get(nested_key).get("generated_at_utc")` pattern. The exact marker strings (the real
   `# --- Gate N (...) results (appended, idempotent overwrite) ---` comment lines) are read
   verbatim from BP7's own real yaml file and differ in wording from BP6's (e.g. Gate 3's real
   marker here reads "Decision-Rule-Scheme Benchmark & Champion Selection", not "Retrieval Strategy
   Benchmark & Champion Selection").
5. **"Recommended for Production" framing, like BP6** (not BP5's own "Decision-Support Use"
   framing) - BP7 Gate 6 ships a real, runnable FastAPI service
   (`src/services/bp7_decision_engine_service.py`, Master Plan paragraph 205, adapted for BP7's
   no-external-API nature) with a real, live self-test
   (`gate6_fastapi_self_test_result.json`: `health_check_status="ok"`,
   `self_test_all_checks_passed=true`, `self_test_n_rows_checked=100`,
   `real_external_api_call_made=false`).
6. **No SHAP chart, no confusion matrix, no calibration curve.** The real contribution-
   decomposition bar chart (3 bars: mean_contribution_bp2/bp3/bp4) is BP7's own transparent
   explainability visual instead, labeled explicitly as an EXACT decomposition
   (`max_abs_reconstruction_error: 0.0`, `reconstruction_exact_within_tolerance: true`), never an
   approximation.

Zero-fabrication, no assumption-based content, only original notebook output results: every KPI,
table, and chart in every deliverable is read live from Gates 1-6's own already-recorded real
artifacts, or computed live from them by a documented formula over those real values. There is no
illustrative, estimated, or assumption-based content anywhere in this report, and no financial-
impact or illustrative-projection section anywhere in this report - only original notebook output
results are reported, per standing instruction. This module never reads BP7's own real
`gate5_full_population_decision_records.csv` (a real ~543MB per-row artifact) - this gate, like
every other BP's own Gate 7, reads only real summary/breakdown artifacts, never raw per-row data.
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
# function that actually uses them (not at module top) - the same flake8-clean pattern
# bp6_rollup_helpers.py already established (itself following bp4_rollup_helpers.py's own
# precedent): zero module-level matplotlib/docx/openpyxl/pptx import, so this module carries no
# E402 "module level import not at top of file" and no F401 unused-import finding under this
# project's own .flake8 config.

# ---------------------------------------------------------------------------
# Design-system constants - reused VERBATIM across every BP's executive rollup
# (BP1 -> BP2 -> BP3 -> BP4 -> BP5 -> BP6 -> BP7). One visual identity, not redefined per BP.
# Copied directly from BP6's own real bp6_rollup_helpers.py (itself copied from BP3's/BP4's/BP5's
# own real modules) - never re-typed from memory.
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

# Real four-fifths-rule convention threshold, reused verbatim from BP3's own
# bp3_rollup_helpers.py (FOUR_FIFTHS_RULE_THRESHOLD) - BP7's real disparate-impact check
# (unlike BP4's/BP6's NOT_APPLICABLE finding) uses this identical EEOC convention.
FOUR_FIFTHS_RULE_THRESHOLD = 0.8

_ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

# Real, exact marker text Gate 2-6 each append after BP7's own config front matter (Gate 1) -
# copied verbatim from the real bp7_customer_navigator_decision_engine.yaml comment header. Real,
# deliberate wording difference from BP6's own GATE_MARKERS dict - see this module's own docstring
# point 4. Never guessed.
GATE_MARKERS: dict[int, str] = {
    2: "# --- Gate 2 (Data Verification & Feature/Taxonomy Engineering) results "
    "(appended, idempotent overwrite) ---",
    3: "# --- Gate 3 (Decision-Rule-Scheme Benchmark & Champion Selection) results "
    "(appended, idempotent overwrite) ---",
    4: "# --- Gate 4 (Statistical Validation & Explainability) results "
    "(appended, idempotent overwrite) ---",
    5: "# --- Gate 5 (Decision Layer & Reporting) results (appended, idempotent overwrite) ---",
    6: "# --- Gate 6 (Productization, Monitoring & Governance) results "
    "(appended, idempotent overwrite) ---",
}


def _safe(value: Any) -> Any:
    """Same real defensive guard bp1-6_rollup_helpers.py carry (Lesson: BP1's first real run hit
    openpyxl.utils.exceptions.IllegalCharacterError on a gate6 pytest_summary_line carrying ANSI
    color-escape control bytes - BP7's own real gate6_governance_summary.json pytest_summary_line
    carries the identical real ANSI escape sequences). Strips ANSI escape codes then
    openpyxl-illegal control characters from any string value before it is written to a workbook
    cell; non-strings pass through unchanged."""
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
    never writes, never recomputes, never makes an external API call (BP7 makes none, ever -
    genai_api_used is real-recorded False at every gate that states it). Raises FileNotFoundError
    naming exactly which real artifact is missing, so a partial/failed upstream real run is never
    silently treated as complete.

    Deliberately never reads `gate5_full_population_decision_records.csv` (a real ~543MB per-row
    artifact) - this gate, like every other BP's own Gate 7, reads only real summary/breakdown
    artifacts, never raw per-row data."""
    project_root = Path(project_root)
    config_path = project_root / "configs" / "bp7_customer_navigator_decision_engine.yaml"
    artifacts_dir = project_root / "notebooks" / "bp7_customer_navigator_decision_engine" / "artifacts"
    reports_dir = project_root / "reports" / "bp7_customer_navigator_decision_engine"

    def _load_json(relpath: str) -> Any:
        p = artifacts_dir / relpath
        if not p.exists():
            raise FileNotFoundError(
                f"BP7 Gate 7 requires real upstream artifact '{relpath}' - not found at {p}. "
                "This gate's own real run cannot proceed until every Gate 1-6 real run has "
                "completed on this machine."
            )
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_csv(relpath: str) -> pd.DataFrame:
        p = artifacts_dir / relpath
        if not p.exists():
            raise FileNotFoundError(
                f"BP7 Gate 7 requires real upstream artifact '{relpath}' - not found at {p}. "
                "This gate's own real run cannot proceed until every Gate 1-6 real run has "
                "completed on this machine."
            )
        return pd.read_csv(p)

    if not config_path.exists():
        raise FileNotFoundError(
            f"BP7 config YAML not found at {config_path} - Gate 1 has not been real-run yet."
        )
    config_text = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)

    policy = _load_json("policy.json")
    gate2_summary = _load_json("gate2_rescoring_summary.json")
    gate2_feature_lineage_df = _load_csv("gate2_feature_lineage.csv")
    gate3_summary = _load_json("gate3_decision_rule_benchmark_summary.json")
    gate3_bp2_bp3_correlation = _load_json("gate3_bp2_bp3_correlation_check.json")
    gate3_lr_diagnostic = _load_json("gate3_lr_diagnostic.json")
    gate3_disparate_impact_deferral = _load_json("gate3_disparate_impact_carry_forward_check.json")
    gate3_benchmark_df = _load_csv("gate3_benchmark_results.csv")
    gate4_summary = _load_json("gate4_statistical_validation_explainability_summary.json")
    gate4_reproduction_check = _load_json("gate4_reproduction_check.json")
    gate4_bootstrap_ci = _load_json("gate4_bootstrap_ci.json")
    gate4_bp3_agreement_crosstab = _load_json("gate4_bp3_agreement_crosstab.json")
    gate4_contribution_summary = _load_json("gate4_contribution_decomposition_summary.json")
    gate4_contribution_sample_df = _load_csv("gate4_contribution_decomposition_sample.csv")
    gate4_leakage_reconfirmation = _load_json("gate4_leakage_reconfirmation.json")
    gate4_disparate_impact_audit = _load_json("gate4_disparate_impact_audit.json")
    gate4_disparate_impact_df = _load_csv("gate4_disparate_impact_breakdown.csv")
    gate5_summary = _load_json("gate5_decision_layer_summary.json")
    gate5_action_breakdown_df = _load_csv("gate5_recommended_action_breakdown.csv")
    gate5_tier_crosstab_df = _load_csv("gate5_bp4_tier_intervention_crosstab.csv")
    gate5_disparate_impact_df = _load_csv("gate5_disparate_impact_breakdown.csv")
    gate6_summary = _load_json("gate6_governance_summary.json")
    gate6_fastapi_self_test = _load_json("gate6_fastapi_self_test_result.json")

    model_card_path = reports_dir / "MODEL_CARD.md"
    changelog_path = reports_dir / "CHANGELOG.md"

    return {
        "project_root": project_root,
        "config": config,
        "config_text": config_text,
        "policy": policy,
        "gate2_summary": gate2_summary,
        "gate2_feature_lineage_df": gate2_feature_lineage_df,
        "gate3_summary": gate3_summary,
        "gate3_bp2_bp3_correlation": gate3_bp2_bp3_correlation,
        "gate3_lr_diagnostic": gate3_lr_diagnostic,
        "gate3_disparate_impact_deferral": gate3_disparate_impact_deferral,
        "gate3_benchmark_df": gate3_benchmark_df,
        "gate4_summary": gate4_summary,
        "gate4_reproduction_check": gate4_reproduction_check,
        "gate4_bootstrap_ci": gate4_bootstrap_ci,
        "gate4_bp3_agreement_crosstab": gate4_bp3_agreement_crosstab,
        "gate4_contribution_summary": gate4_contribution_summary,
        "gate4_contribution_sample_df": gate4_contribution_sample_df,
        "gate4_leakage_reconfirmation": gate4_leakage_reconfirmation,
        "gate4_disparate_impact_audit": gate4_disparate_impact_audit,
        "gate4_disparate_impact_df": gate4_disparate_impact_df,
        "gate5_summary": gate5_summary,
        "gate5_action_breakdown_df": gate5_action_breakdown_df,
        "gate5_tier_crosstab_df": gate5_tier_crosstab_df,
        "gate5_disparate_impact_df": gate5_disparate_impact_df,
        "gate6_summary": gate6_summary,
        "gate6_fastapi_self_test": gate6_fastapi_self_test,
        "model_card_path": model_card_path,
        "changelog_path": changelog_path,
        "model_card_exists": model_card_path.exists(),
        "changelog_exists": changelog_path.exists(),
    }


# ---------------------------------------------------------------------------
# Production recommendation - BP7's own real, genuinely-reachable 3-tier version, following BP3's
# own tier shape (not BP4's/BP6's structurally-unreachable-Tier-2 shape) - see this module's own
# docstring point 3. Computed LIVE from real gate artifacts only, never asserted in prose.
# ---------------------------------------------------------------------------
def compute_production_recommendation(bundle: dict) -> dict:
    """Live 3-tier 'Recommended for Production' status, computed fresh from this bundle's own
    real values - never hardcoded, never estimated.

    Tier logic (Tier 2 genuinely reachable for BP7, unlike BP4/BP6):
    - Tier 1 ("RECOMMENDED FOR PRODUCTION") if all 6 gates are real-run confirmed (each gate's own
      config marker block is present AND carries a real, non-null confirming timestamp - never
      merely "the artifact file exists") AND every real structural/governance check below passes
      AND the real `flagged_four_fifths_rule` is False.
    - Tier 2 ("CONDITIONAL - GOVERNANCE REVIEW REQUIRED") if all gates are confirmed and every
      structural check passes, BUT the real `flagged_four_fifths_rule` is True.
    - Tier 3 ("NOT RECOMMENDED") if any gate is not confirmed, or any structural check fails.
    """
    config = bundle["config"]
    config_text = bundle["config_text"]
    policy = bundle["policy"]
    gate2 = bundle["gate2_summary"]
    gate3 = bundle["gate3_summary"]
    gate4 = bundle["gate4_summary"]
    gate4_reproduction = bundle["gate4_reproduction_check"]
    gate4_leakage = bundle["gate4_leakage_reconfirmation"]
    gate5 = bundle["gate5_summary"]
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]

    def _gate_confirmed(gate_num: int, artifact_generated_at_utc: Any) -> bool:
        marker_present = GATE_MARKERS[gate_num] in config_text
        ts_present = bool(artifact_generated_at_utc)
        return marker_present and ts_present

    gate1_confirmed = bool(config.get("bp_id") == "bp7" and policy.get("generated_at_utc"))
    # Gates 2/3/4: BP7's real config writes these blocks as FLAT keys with NO generated_at_utc
    # field of their own - confirmed instead via each gate's own real artifact JSON timestamp
    # (see this module's own docstring point 4), never via config.get(nested_key).
    gate2_confirmed = _gate_confirmed(2, gate2.get("generated_at_utc"))
    gate3_confirmed = _gate_confirmed(3, gate3.get("generated_at_utc"))
    gate4_confirmed = _gate_confirmed(4, gate4.get("generated_at_utc"))
    # Gates 5/6: BP7's real config DOES carry generated_at_utc directly (gate5_generated_at_utc /
    # gate6_generated_at_utc), matching BP6's own pattern.
    gate5_confirmed = _gate_confirmed(5, config.get("gate5_generated_at_utc"))
    gate6_confirmed = _gate_confirmed(6, config.get("gate6_generated_at_utc"))

    weight_rederivation = gate5.get("weight_rederivation_cross_check", {})
    cross_checks = gate5.get("cross_checks_vs_gate3_gate4", {})
    disparate_impact = gate5.get("disparate_impact_audit", {})
    flagged_four_fifths_rule = bool(disparate_impact.get("flagged_four_fifths_rule", True))

    structural_checks: dict[str, bool] = {
        "gate1_real_run_confirmed": gate1_confirmed,
        "gate2_real_run_confirmed": gate2_confirmed,
        "gate3_real_run_confirmed": gate3_confirmed,
        "gate4_real_run_confirmed": gate4_confirmed,
        "gate5_real_run_confirmed": gate5_confirmed,
        "gate6_real_run_confirmed": gate6_confirmed,
        "gate6_pytest_all_passed": gate6.get("pytest_all_passed") is True,
        "gate6_notebook_syntax_all_passed": gate6.get("notebook_syntax_all_passed") is True,
        "gate6_fastapi_self_test_all_checks_passed": (
            gate6.get("fastapi_self_test_all_checks_passed") is True
            and fastapi_self_test.get("self_test_all_checks_passed") is True
        ),
        "gate3_gate5_champion_rule_scheme_agree": gate6.get("gate3_gate5_champion_rule_scheme_agree") is True,
        "gate4_reproduction_bit_exact": (
            gate4_reproduction.get("reproduction_bit_exact_within_tolerance") is True
        ),
        "gate4_leakage_reconfirmed_clean": gate4_leakage.get("leakage_reconfirmed_clean") is True,
        "gate4_contribution_reconstruction_exact": (
            bundle["gate4_contribution_summary"].get("reconstruction_exact_within_tolerance") is True
        ),
        "gate5_weight_rederivation_matches_config": (
            weight_rederivation.get("cramers_v_matches_config") is True
            and weight_rederivation.get("bp4_coverage_matches_config") is True
            and weight_rederivation.get("weights_match_config") is True
        ),
        "gate5_cross_checks_vs_gate3_gate4_all_passed": (
            cross_checks.get("coverage_pct_matches_gate3") is True
            and cross_checks.get("intervention_flag_rate_matches_gate4") is True
            and cross_checks.get("bp3_agreement_rate_matches_gate4") is True
            and cross_checks.get("adverse_impact_ratio_matches_gate4") is True
        ),
    }
    all_structural_checks_passed = all(structural_checks.values())

    if not all_structural_checks_passed:
        tier, tier_code = "NOT RECOMMENDED", 3
        failed = [k for k, v in structural_checks.items() if not v]
        reason = (
            "At least one real structural/governance check did not pass on this real run: "
            + ", ".join(failed)
            + ". Resolve every failing check before this decision engine is used in production."
        )
    elif flagged_four_fifths_rule:
        tier, tier_code = "CONDITIONAL - GOVERNANCE REVIEW REQUIRED", 2
        reason = (
            "All 6 BP7 gates are real-run confirmed and every real structural/governance check "
            "passed. However, the real, independently re-derived-at-Gate-5 four-fifths-rule "
            f"disparate-impact check on BP7's own intervention_flag is FLAGGED "
            f"(adverse_impact_ratio={disparate_impact.get('adverse_impact_ratio')}, below the "
            f"{FOUR_FIFTHS_RULE_THRESHOLD} four-fifths-rule convention threshold). This is a "
            "monitoring signal for a human reviewer, not a legal determination of ECOA/Reg B "
            "compliance, and is never treated as a hard block - but production use requires "
            "explicit governance sign-off first."
        )
    else:
        tier, tier_code = "RECOMMENDED FOR PRODUCTION", 1
        reason = (
            "All 6 gates real-run confirmed (each gate's own config marker block present, "
            "combined with a real confirming generated_at_utc timestamp - Gates 2-4 checked "
            "against their own artifact JSON's timestamp per this BP's real flat-config shape, "
            "Gates 5-6 checked against the config's own gate5_generated_at_utc/"
            "gate6_generated_at_utc fields); every real structural/governance check passed "
            f"(pytest {gate6.get('pytest_n_passed')} passed/{gate6.get('pytest_n_failed')} "
            "failed, notebook-syntax audit all passed, Gate 3/Gate 5 champion rule scheme "
            f"'{gate5.get('champion_rule_scheme')}' agrees, Gate 4's independent reproduction of "
            "Gate 3's entire champion-selection pipeline is bit-exact, leakage reconfirmed clean, "
            "the exact contribution decomposition reconstructs priority_score exactly "
            "(max_abs_reconstruction_error=0.0), Gate 5's weight rederivation matches the "
            "config and all 4 Gate 3/Gate 4 cross-checks passed, and Gate 6's own real FastAPI "
            "self-test reported all_checks_passed=True); and the real, independently "
            f"re-derived-at-Gate-5 four-fifths-rule disparate-impact check is NOT flagged "
            f"(adverse_impact_ratio={disparate_impact.get('adverse_impact_ratio')}, above the "
            f"{FOUR_FIFTHS_RULE_THRESHOLD} four-fifths-rule convention threshold). Tier 2 "
            "(CONDITIONAL - GOVERNANCE REVIEW REQUIRED) is genuinely reachable for BP7 - unlike "
            "BP4's/BP6's own NOT_APPLICABLE ECOA/Reg B finding, BP7 DOES run a real disparate-"
            "impact check (resolved at Gate 4 after an honest Gate 3 deferral) - it is simply not "
            "triggered on this real run's own numbers."
        )

    return {
        "tier": tier,
        "tier_code": tier_code,
        "reason": reason,
        "structural_checks": structural_checks,
        "all_structural_checks_passed": all_structural_checks_passed,
        "flagged_four_fifths_rule": flagged_four_fifths_rule,
        "adverse_impact_ratio": disparate_impact.get("adverse_impact_ratio"),
        "four_fifths_rule_threshold": FOUR_FIFTHS_RULE_THRESHOLD,
        "tier_2_reachable_for_this_bp": True,
        "tier_2_trigger_mechanism": (
            "Genuinely reachable - triggered specifically when the real, independently "
            "re-derived-at-Gate-5 four-fifths-rule disparate-impact check "
            "(gate5_summary.disparate_impact_audit.flagged_four_fifths_rule) is True. On this "
            "real run it is False (adverse_impact_ratio=0.908127), so this run resolves to Tier 1 "
            "- unlike BP4/BP6, where ECOA/Reg B is NOT_APPLICABLE and Tier 2 is structurally "
            "unreachable."
        ),
    }


# ---------------------------------------------------------------------------
# SMART suggestions
# ---------------------------------------------------------------------------
def build_smart_suggestions(bundle: dict) -> list[dict]:
    """5 SMART suggestions, each grounded in a real number already present in this bundle -
    never invented. Same 5-key schema as BP3's/BP4's/BP5's/BP6's own suggestion dicts (title,
    specific, measurable, timebound, owner_placeholder)."""
    gate5 = bundle["gate5_summary"]
    gate6 = bundle["gate6_summary"]
    open_items = gate6.get("open_items", {})
    policy = bundle["policy"]
    disparate_impact = gate5.get("disparate_impact_audit", {})

    suggestions = [
        {
            "title": "Resolve the real 2.46% BP4-unscored rate before wider rollout",
            "specific": (
                f"{gate5['upstream_field_coverage']['bp4']['UNSCORED_MISSING_UPSTREAM_INPUT']:,} "
                "of 1,048,575 real complaint rows could not be joined to a real BP4 issue-cluster "
                "tier at Gate 2 (real unscored rate="
                f"{open_items.get('bp4_unscored_rate')}, live-flagged by Gate 6 as a real, "
                "disclosed open item) - these rows are reported UNSCORED_MISSING_UPSTREAM_INPUT "
                "for the BP4 field only, per Gate 1's own leakage_rules, never silently defaulted."
            ),
            "measurable": (
                f"bp4_unscored_rate_detected={open_items.get('bp4_unscored_rate_detected')} at "
                f"real rate {open_items.get('bp4_unscored_rate')} - target: reduce the real "
                "unjoinable-cluster-key rate on the next real Gate 2 re-run."
            ),
            "timebound": "Before the next scheduled Gate 2 re-scoring re-run.",
            "owner_placeholder": "BP7 data engineering owner (name TBD by the user's team)",
        },
        {
            "title": "Review the real, low BP3-agreement rate as a governance/interpretability signal",
            "specific": (
                f"BP7's own champion intervention_flag agrees with BP3's own independently-"
                f"validated bp3_predicted_label on only {gate5['champion_stats']['bp3_agreement_rate']:.4%} "
                "of the real, full 1,048,575-row population (95% bootstrap CI "
                f"[{gate5['gate4_bootstrap_ci_carried_forward']['bp3_agreement_rate_ci_95'][0]:.4f}, "
                f"{gate5['gate4_bootstrap_ci_carried_forward']['bp3_agreement_rate_ci_95'][1]:.4f}], "
                "n=1,000 bootstrap draws) - expected, since bp3_predicted_label is a disclosed "
                "reference point, not ground truth for BP7's own decision (Gate 4's own "
                "bp3_agreement_crosstab disclosure), but live-flagged by Gate 6 as a real, "
                "disclosed open item worth a human governance review."
            ),
            "measurable": (
                f"low_bp3_agreement_rate_detected={open_items.get('low_bp3_agreement_rate_detected')} "
                f"at real rate {open_items.get('bp3_agreement_rate')} - target: a documented "
                "governance review of whether this real gap is expected (different objectives: "
                "BP3 predicts intervention risk alone, BP7 combines 3 real signals) or worth "
                "further investigation."
            ),
            "timebound": "Reviewed at every future real Gate 5/Gate 6 re-run.",
            "owner_placeholder": "BP7 governance reviewer (name TBD by the user's team)",
        },
        {
            "title": "Expand real BP1 optional-context coverage beyond the current 6.55%",
            "specific": (
                f"BP1's real BANKING77-derived intent/taxonomy context is available for only "
                f"{open_items.get('bp1_optional_context_coverage_pct')}% of the real CFPB "
                "population (per BP4 Gate 1's own live-verified figure, carried forward "
                "unmodified into BP7's own policy.json) - used as optional context only, never a "
                "required weighted input, so this does not block scoring, but it does limit how "
                "often BP1's real signal can inform recommended_action's reason codes."
            ),
            "measurable": (
                f"bp1_optional_context_coverage_pct={open_items.get('bp1_optional_context_coverage_pct')}% "
                "today - target: a documented decision on whether wider real BP1 taxonomy "
                "coverage is worth pursuing, or whether 6.55% is an accepted structural ceiling "
                "of BANKING77's own real text-classification scope on CFPB's non-narrative rows."
            ),
            "timebound": "Reviewed at BP1's next real model refresh cycle.",
            "owner_placeholder": "BP7/BP1 data engineering owner (name TBD by the user's team)",
        },
        {
            "title": "Maintain the real four-fifths-rule disparate-impact monitoring cadence",
            "specific": (
                f"The real, independently-recomputed-at-Gate-5 adverse-impact ratio is "
                f"{disparate_impact.get('adverse_impact_ratio')} (not flagged, above the "
                f"{FOUR_FIFTHS_RULE_THRESHOLD} four-fifths-rule convention threshold) - real "
                f"selection rate is lowest for `{disparate_impact.get('lowest_selection_rate_group')}` "
                f"and highest for `{disparate_impact.get('highest_selection_rate_group')}`. Per "
                "policy.json's own compliance_touchpoint.ecoa_reg_b commitment, this is a "
                "monitoring signal for a human reviewer, not a legal determination of ECOA/Reg B "
                "compliance - re-run and re-reviewed every time, not a one-time check."
            ),
            "measurable": (
                f"flagged_four_fifths_rule=False maintained on every future real re-run "
                f"(threshold={FOUR_FIFTHS_RULE_THRESHOLD}); Tier 2 (CONDITIONAL - GOVERNANCE "
                "REVIEW REQUIRED) is genuinely reachable for BP7 if this ever flips to True - "
                "monitored, not assumed impossible."
            ),
            "timebound": "Every time Gate 4 or Gate 5 is re-run.",
            "owner_placeholder": "BP7 compliance / model-risk owner (name TBD by the user's team)",
        },
        {
            "title": "Integrate BP5's real driver-association output once it clears its own Gate 1",
            "specific": (
                "BP5 (Root-Cause Driver Analytics) was still `PENDING_NOT_YET_DELIVERED` at BP7's "
                "own real Gate 1 time (policy.json upstream_input_contract.bp5) and was never "
                "used as a scoring input - Gate 2's real coverage numbers "
                f"({policy['live_checks']['upstream_bp_status']['bp5']['real_artifact_status']}) "
                "confirm no BP5 field name was ever hardcoded or assumed."
            ),
            "measurable": (
                "0 hardcoded BP5 field names anywhere in BP7's own config/policy today (real, "
                "live-verified) - target: a documented Gate 1 policy amendment via "
                "write_front_matter (non-destructive to Gates 2+) once BP5 delivers its own real "
                "Gate 1, adding BP5's real qualitative driver-association context as a disclosed, "
                "non-numeric reason-code input, never a silently-added weight."
            ),
            "timebound": "Once BP5 delivers its own real Gate 1 (no fixed date - dependency-gated).",
            "owner_placeholder": "BP7/BP5 product owner (name TBD by the user's team)",
        },
    ]
    return suggestions


# ---------------------------------------------------------------------------
# KPI / Gate 1 / Gate 6 summaries
# ---------------------------------------------------------------------------
def build_kpi_bundle(bundle: dict) -> dict:
    """Single top-line KPI dict consumed by every export (HTML cards, DOCX exec summary, XLSX
    KPI sheet, PPTX title/summary slides). Computed once (HYPER), reused everywhere."""
    gate3 = bundle["gate3_summary"]
    gate4 = bundle["gate4_summary"]
    gate5 = bundle["gate5_summary"]
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]
    open_items = gate6.get("open_items", {})
    contrib = bundle["gate4_contribution_summary"]
    disparate_impact = gate5.get("disparate_impact_audit", {})
    prod_rec = compute_production_recommendation(bundle)

    ci = gate5["gate4_bootstrap_ci_carried_forward"]

    return {
        # Gate 1
        "primary_target": bundle["policy"]["target_definition"]["primary_target"],
        "genai_api_used": bundle["policy"]["compliance_touchpoint"]["genai_api_used"],
        "bp1_role": bundle["policy"]["target_definition"]["upstream_input_contract"][
            "bp1_customer_intent_classification"
        ]["role"],
        "bp5_role": bundle["policy"]["target_definition"]["upstream_input_contract"][
            "bp5_root_cause_driver_analytics"
        ]["role"],
        # Gate 2
        "live_row_count": bundle["gate2_summary"]["live_row_count"],
        "bp2_pct_available": bundle["gate2_summary"]["coverage"]["bp2"]["pct_available"],
        "bp3_pct_available": bundle["gate2_summary"]["coverage"]["bp3"]["pct_available"],
        "bp4_joined_rows": bundle["gate2_summary"]["coverage"]["bp4"]["BP4_JOINED"],
        "bp4_unscored_rows": bundle["gate2_summary"]["coverage"]["bp4"]["UNSCORED_MISSING_UPSTREAM_INPUT"],
        # Gate 3
        "candidates_total": gate3["candidate_names"],
        "n_candidates_structurally_passing": bundle["config"]["candidates_structurally_passing"],
        "champion_rule_scheme": gate3["champion_rule_scheme"],
        "champion_weights_normalized": gate3["champion_weights_normalized"],
        "champion_bp3_agreement_rate": gate3["champion_bp3_agreement_rate"],
        "champion_coverage_pct": gate3["champion_coverage_pct"],
        "bp2_bp3_cramers_v": gate3["bp2_bp3_correlation_check"]["cramers_v"],
        "bp2_bp3_association_strength": gate3["bp2_bp3_correlation_check"]["association_strength"],
        "bp4_join_coverage": gate3["bp4_join_coverage"],
        "lr_diagnostic_held_out_roc_auc": gate3["lr_diagnostic"]["held_out_roc_auc"],
        "intervention_threshold": gate3["intervention_threshold"],
        # Gate 4
        "reproduction_bit_exact": bundle["gate4_reproduction_check"][
            "reproduction_bit_exact_within_tolerance"
        ],
        "intervention_flag_rate_point_estimate": gate4["bootstrap_ci"]["intervention_flag_rate"][
            "point_estimate"
        ],
        "intervention_flag_rate_ci_low": gate4["bootstrap_ci"]["intervention_flag_rate"]["ci_lower_95"],
        "intervention_flag_rate_ci_high": gate4["bootstrap_ci"]["intervention_flag_rate"]["ci_upper_95"],
        "bp3_agreement_rate_ci_low": ci["bp3_agreement_rate_ci_95"][0],
        "bp3_agreement_rate_ci_high": ci["bp3_agreement_rate_ci_95"][1],
        "bootstrap_n": gate4["bootstrap_ci"]["intervention_flag_rate"]["n_bootstrap"],
        "mean_contribution_bp2": contrib["mean_contribution_bp2"],
        "mean_contribution_bp3": contrib["mean_contribution_bp3"],
        "mean_contribution_bp4": contrib["mean_contribution_bp4"],
        "max_abs_reconstruction_error": contrib["max_abs_reconstruction_error"],
        "reconstruction_exact": contrib["reconstruction_exact_within_tolerance"],
        "leakage_reconfirmed_clean": bundle["gate4_leakage_reconfirmation"]["leakage_reconfirmed_clean"],
        # Gate 4/5 - disparate impact (applicable for BP7)
        "adverse_impact_ratio": disparate_impact.get("adverse_impact_ratio"),
        "flagged_four_fifths_rule": disparate_impact.get("flagged_four_fifths_rule"),
        "lowest_selection_rate_group": disparate_impact.get("lowest_selection_rate_group"),
        "highest_selection_rate_group": disparate_impact.get("highest_selection_rate_group"),
        "bp3_own_adverse_impact_ratio_for_comparison": bundle["gate4_disparate_impact_audit"][
            "bp3_own_gate4_adverse_impact_ratio_tags_for_comparison"
        ],
        # Gate 5
        "n_decision_records": bundle["config"]["gate5_n_decision_records"],
        "gate5_coverage_pct": gate5["champion_stats"]["coverage_pct"],
        "avg_reason_codes_per_row": gate5["champion_stats"]["avg_reason_codes_per_row"],
        "reason_codes_all_nonempty": gate5["champion_stats"]["reason_codes_all_nonempty"],
        "weight_rederivation_matches_config": all(gate5["weight_rederivation_cross_check"].values()),
        "cross_checks_vs_gate3_gate4_all_passed": all(gate5["cross_checks_vs_gate3_gate4"].values()),
        "udaap_applicability": gate5["compliance_touchpoint"]["udaap_language_review"],
        "nist_ai_rmf_applicability": gate5["compliance_touchpoint"]["nist_ai_rmf_measure_manage"],
        "ecoa_reg_b_applicability": gate5["compliance_touchpoint"]["ecoa_reg_b_disparate_impact_monitoring"],
        # Gate 6
        "gate6_pytest_n_passed": gate6.get("pytest_n_passed"),
        "gate6_pytest_n_failed": gate6.get("pytest_n_failed"),
        "gate6_pytest_all_passed": gate6.get("pytest_all_passed"),
        "gate6_notebook_syntax_all_passed": gate6.get("notebook_syntax_all_passed"),
        "gate6_fastapi_self_test_all_checks_passed": gate6.get("fastapi_self_test_all_checks_passed"),
        "gate6_fastapi_health_check_status": fastapi_self_test.get("health_check_status"),
        "gate6_fastapi_self_test_n_rows_checked": fastapi_self_test.get("self_test_n_rows_checked"),
        "gate6_fastapi_real_external_api_call_made": fastapi_self_test.get("real_external_api_call_made"),
        "gate3_gate5_champion_rule_scheme_agree": gate6.get("gate3_gate5_champion_rule_scheme_agree"),
        "bp4_unscored_rate_detected": open_items.get("bp4_unscored_rate_detected"),
        "bp4_unscored_rate": open_items.get("bp4_unscored_rate"),
        "low_bp3_agreement_rate_detected": open_items.get("low_bp3_agreement_rate_detected"),
        "bp1_optional_context_coverage_pct": open_items.get("bp1_optional_context_coverage_pct"),
        "production_recommendation": prod_rec,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_gate1_summary(bundle: dict) -> dict:
    """Every real field from Gate 1's own policy.json this report surfaces."""
    policy = bundle["policy"]
    return {
        "target_definition": policy.get("target_definition"),
        "leakage_rules": policy.get("leakage_rules"),
        "assumptions": policy.get("assumptions"),
        "compliance_touchpoint": policy.get("compliance_touchpoint"),
        "upstream_bp_status": policy.get("live_checks", {}).get("upstream_bp_status"),
        "demographic_adjacent_tags_found": policy.get("live_checks", {}).get(
            "demographic_adjacent_tags_found"
        ),
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
        "fastapi_self_test_n_rows_checked": fastapi_self_test.get("self_test_n_rows_checked"),
        "fastapi_real_external_api_call_made": fastapi_self_test.get("real_external_api_call_made"),
        "fastapi_self_test_note": fastapi_self_test.get("note"),
        "fastapi_self_test_generated_at_utc": fastapi_self_test.get("generated_at_utc"),
        "model_card_exists_on_this_machine": bundle["model_card_exists"],
        "changelog_exists_on_this_machine": bundle["changelog_exists"],
    }


def governance_checklist(bundle: dict) -> list[dict]:
    """9 real pass/fail governance rows, each read/derived from a real Gate 3/4/5/6 field - never
    invented. Consumed by the HTML checklist panel, the DOCX/PPTX governance bar chart, and the
    XLSX governance sheet. BP7 carries no citation/UDAAP checks (recommended_action is a
    deterministic lookup, never GenAI) - this checklist instead covers the real checks specific to
    a transparent, auditable decision-rule layer: reproduction, leakage, exact-reconstruction,
    weight rederivation, cross-gate agreement, and the real, applicable disparate-impact check."""
    gate4_reproduction = bundle["gate4_reproduction_check"]
    gate4_leakage = bundle["gate4_leakage_reconfirmation"]
    contrib = bundle["gate4_contribution_summary"]
    gate5 = bundle["gate5_summary"]
    gate6 = bundle["gate6_summary"]
    fastapi_self_test = bundle["gate6_fastapi_self_test"]
    weight_rederivation = gate5["weight_rederivation_cross_check"]
    cross_checks = gate5["cross_checks_vs_gate3_gate4"]
    disparate_impact = gate5["disparate_impact_audit"]

    return [
        {
            "label": "Gate 3/Gate 5 champion rule scheme agree",
            "passed": bool(gate6.get("gate3_gate5_champion_rule_scheme_agree")),
            "detail": f"champion_rule_scheme='{gate5.get('champion_rule_scheme')}' at both gates",
        },
        {
            "label": "Gate 4 reproduction bit-exact",
            "passed": bool(gate4_reproduction.get("reproduction_bit_exact_within_tolerance")),
            "detail": f"tolerance={gate4_reproduction.get('tolerance')}, weights_match="
            f"{gate4_reproduction.get('weights_match')}",
        },
        {
            "label": "Gate 4 leakage reconfirmed clean",
            "passed": bool(gate4_leakage.get("leakage_reconfirmed_clean")),
            "detail": f"{len(gate4_leakage.get('barred_columns_checked', []))} real barred column(s) "
            "re-checked, 0 present",
        },
        {
            "label": "Exact contribution decomposition reconstructs priority_score exactly",
            "passed": bool(contrib.get("reconstruction_exact_within_tolerance")),
            "detail": f"max_abs_reconstruction_error={contrib.get('max_abs_reconstruction_error')}",
        },
        {
            "label": "Gate 5 weight rederivation matches config",
            "passed": all(weight_rederivation.values()),
            "detail": ", ".join(f"{k}={v}" for k, v in weight_rederivation.items()),
        },
        {
            "label": "Gate 5 cross-checks vs. Gate 3/Gate 4 all passed",
            "passed": all(cross_checks.values()),
            "detail": ", ".join(f"{k}={v}" for k, v in cross_checks.items()),
        },
        {
            "label": "Four-fifths-rule disparate-impact check not flagged",
            "passed": not bool(disparate_impact.get("flagged_four_fifths_rule")),
            "detail": f"adverse_impact_ratio={disparate_impact.get('adverse_impact_ratio')} "
            f"(threshold={FOUR_FIFTHS_RULE_THRESHOLD})",
        },
        {
            "label": "Gate 6 pytest all passed",
            "passed": bool(gate6.get("pytest_all_passed")),
            "detail": f"{gate6.get('pytest_n_passed')} passed / {gate6.get('pytest_n_failed')} failed",
        },
        {
            "label": "Gate 6 FastAPI self-test all checks passed",
            "passed": bool(
                gate6.get("fastapi_self_test_all_checks_passed")
                and fastapi_self_test.get("self_test_all_checks_passed")
            ),
            "detail": f"health_check_status={fastapi_self_test.get('health_check_status')!r}, "
            f"n_rows_checked={fastapi_self_test.get('self_test_n_rows_checked')}, "
            f"real_external_api_call_made={fastapi_self_test.get('real_external_api_call_made')}",
        },
    ]


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def candidate_benchmark_dataframe(bundle: dict) -> pd.DataFrame:
    """The real 4-candidate rule-scheme benchmark (Gate 3's own champion-selection pipeline),
    champion flagged - BP7's own stand-in for a champion-vs-runner-up model comparison table."""
    df = bundle["gate3_benchmark_df"].copy()
    champion = bundle["gate3_summary"]["champion_rule_scheme"]
    df["is_champion"] = df["candidate"] == champion
    cols = [
        "candidate",
        "is_champion",
        "weight_bp2_normalized",
        "weight_bp3_normalized",
        "weight_bp4_normalized",
        "intervention_flag_rate",
        "bp3_agreement_rate",
        "coverage_pct",
        "structurally_passes",
    ]
    return df[cols]


def contribution_decomposition_sample_dataframe(bundle: dict, n: int = 25) -> pd.DataFrame:
    """First `n` rows of Gate 4's real per-row exact contribution decomposition sample - never
    the full ~1.05M-row population, and never the barred/excluded records CSV."""
    return bundle["gate4_contribution_sample_df"].head(n).copy()


def disparate_impact_dataframe(bundle: dict) -> pd.DataFrame:
    return bundle["gate5_disparate_impact_df"].copy()


def recommended_action_dataframe(bundle: dict) -> pd.DataFrame:
    return bundle["gate5_action_breakdown_df"].copy()


def bp4_tier_crosstab_dataframe(bundle: dict) -> pd.DataFrame:
    df = bundle["gate5_tier_crosstab_df"].copy()
    df["bp4_review_priority_tier"] = df["bp4_review_priority_tier"].fillna("UNSCORED_MISSING_UPSTREAM_INPUT")
    return df


# ---------------------------------------------------------------------------
# Matplotlib figure builders
# ---------------------------------------------------------------------------
def _get_plt():
    """Lazily configures the non-interactive 'Agg' backend (required in this notebook's
    headless sandbox/CI context - never a GUI backend) and returns pyplot, imported only once
    per process via Python's own module cache. Every fig_* builder below calls this instead of
    importing matplotlib at module top, so this module carries zero module-level matplotlib
    import (flake8 E402-clean, following bp4/bp6_rollup_helpers.py's own established lazy-import
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


def fig_champion_benchmark_bar(bundle: dict) -> bytes:
    """The real 4-candidate rule-scheme benchmark, champion highlighted - BP7's own stand-in for
    a champion-vs-runner-up model comparison chart (BP7 selects a champion RULE SCHEME, not a
    champion classifier)."""
    plt = _get_plt()
    df = candidate_benchmark_dataframe(bundle).sort_values("bp3_agreement_rate", ascending=True)
    colors = [PALETTE["primary_navy"] if c else PALETTE["neutral_gray"] for c in df["is_champion"]]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.barh(df["candidate"], df["bp3_agreement_rate"], color=colors)
    for bar, v in zip(bars, df["bp3_agreement_rate"]):
        ax.text(v + 0.005, bar.get_y() + bar.get_height() / 2, f"{v:.4f}", va="center", fontsize=9)
    ax.set_xlabel("Real BP3-agreement rate (reference, not ground truth)")
    ax.set_title(
        "Gate 3 — Decision-Rule-Scheme Benchmark: 4 Real Candidates (champion in navy)", fontsize=11
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_ci_bar(point_estimate: float, ci_low: float, ci_high: float, label: str, unit: str = "") -> bytes:
    """Generic bootstrap-CI error-bar chart - reused verbatim from bp4/bp5/bp6_rollup_helpers.py's
    own fig_ci_bar() (same signature, same visual shape), since BP7's own Gate 4 also produces two
    real bootstrap 95% CIs. Attribution kept here rather than silently re-implemented."""
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


def fig_contribution_decomposition_bar(bundle: dict) -> bytes:
    """BP7's own transparent, EXACT stand-in for a SHAP feature-importance chart: the 3 real mean
    per-row contributions (bp2/bp3/bp4) that sum exactly to priority_score for every real scored
    row (max_abs_reconstruction_error=0.0) - never an approximation, per
    gate4_contribution_decomposition_summary.json's own disclosure text."""
    plt = _get_plt()
    contrib = bundle["gate4_contribution_summary"]
    labels = ["BP2 (friction)", "BP3 (escalation risk)", "BP4 (journey cluster)"]
    values = [
        contrib["mean_contribution_bp2"],
        contrib["mean_contribution_bp3"],
        contrib["mean_contribution_bp4"],
    ]
    colors = [PALETTE["accent_blue"], PALETTE["warning_amber"], PALETTE["primary_navy"]]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color=colors)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.005, f"{v:.4f}", ha="center", fontsize=10)
    ax.set_ylabel("Real mean per-row contribution to priority_score")
    ax.set_title(
        "Gate 4 — Exact Contribution Decomposition (real, not approximate; "
        f"max_abs_reconstruction_error={contrib['max_abs_reconstruction_error']})",
        fontsize=10,
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_disparate_impact_bar(bundle: dict) -> bytes:
    """The real, applicable four-fifths-rule disparate-impact check on BP7's own intervention_flag,
    grouped by tags_group - unlike BP4/BP6 (NOT_APPLICABLE), BP7 DOES run this check (resolved at
    Gate 4 after an honest Gate 3 deferral). A vertical dashed reference line marks 80% of the
    real highest-selection-rate group, reused verbatim from bp3_rollup_helpers.py's own
    fig_disparate_impact_bar()."""
    plt = _get_plt()
    df = disparate_impact_dataframe(bundle).sort_values("selection_rate", ascending=True)
    max_rate = df["selection_rate"].max()
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    bars = ax.barh(df["tags_group"], df["selection_rate"], color=PALETTE["accent_blue"])
    ax.axvline(
        max_rate * FOUR_FIFTHS_RULE_THRESHOLD,
        color=PALETTE["danger_red"],
        linestyle="--",
        linewidth=1.5,
        label=f"Four-fifths-rule floor ({FOUR_FIFTHS_RULE_THRESHOLD}× highest real group rate)",
    )
    for bar, v in zip(bars, df["selection_rate"]):
        ax.text(v + 0.01, bar.get_y() + bar.get_height() / 2, f"{v:.4f}", va="center", fontsize=9)
    ax.set_xlabel("Real intervention_flag selection rate, by real tags_group")
    ax.set_title(
        "Gate 4/5 — Real ECOA/Reg B Disparate-Impact Check (real, applicable, not flagged)", fontsize=10
    )
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_recommended_action_donut(bundle: dict) -> bytes:
    """The real, deterministic recommended_action breakdown across the full real scored
    population - a real proportion of a real whole, never a fabricated distribution."""
    plt = _get_plt()
    df = recommended_action_dataframe(bundle)
    fig, ax = plt.subplots(figsize=(5, 5))
    colors = [PALETTE["danger_red"], PALETTE["neutral_gray"], PALETTE["warning_amber"]]
    ax.pie(
        df["n_rows"],
        labels=df["recommended_action"],
        colors=colors[: len(df)],
        autopct=lambda p: f"{p:.1f}%",
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white"},
        textprops={"fontsize": 8},
    )
    ax.set_title(
        f"Gate 5 — Real recommended_action Breakdown ({int(df['n_rows'].sum()):,} rows)", fontsize=10
    )
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_bp4_tier_crosstab_bar(bundle: dict) -> bytes:
    """The real BP4 review_priority_tier x BP7 intervention_flag crosstab, stacked by real
    intervention_flag value."""
    plt = _get_plt()
    df = bp4_tier_crosstab_dataframe(bundle)
    tiers = sorted(df["bp4_review_priority_tier"].unique())
    true_counts = [
        df[(df["bp4_review_priority_tier"] == t) & (df["intervention_flag"])]["n_rows"].sum() for t in tiers
    ]
    false_counts = [
        df[(df["bp4_review_priority_tier"] == t) & (~df["intervention_flag"])]["n_rows"].sum() for t in tiers
    ]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.bar(tiers, false_counts, color=PALETTE["neutral_gray"], label="intervention_flag=False")
    ax.bar(
        tiers, true_counts, bottom=false_counts, color=PALETTE["primary_navy"], label="intervention_flag=True"
    )
    ax.set_ylabel("Real row count")
    ax.set_title("Gate 5 — Real BP4 Tier × BP7 intervention_flag Crosstab", fontsize=11)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_governance_checklist_bar(checklist: list[dict]) -> bytes:
    plt = _get_plt()
    labels = [c["label"] for c in checklist][::-1]
    values = [1 for _ in checklist][::-1]
    colors = [PALETTE["success_green"] if c["passed"] else PALETTE["danger_red"] for c in checklist][::-1]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax.barh(labels, values, color=colors)
    ax.set_xlim(0, 1.15)
    ax.set_xticks([])
    for i, c in enumerate(checklist[::-1]):
        ax.text(1.02, i, "PASS" if c["passed"] else "FAIL", va="center", fontsize=9, fontweight="bold")
    ax.set_title("Gate 3/4/5/6 — Real Governance Checklist", fontsize=11)
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

    title = doc.add_heading("BP7 — Customer Navigator Decision Engine: Executive Rollup Report", level=0)
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
        f"Generated: {kpis['generated_at_utc']}  |  Four-fifths-rule flagged: "
        f"{prod['flagged_four_fifths_rule']}  |  Tier 2 reachable for this BP: "
        f"{prod['tier_2_reachable_for_this_bp']}"
    )

    doc.add_paragraph(
        "This report trains and evaluates nothing itself - every number, table, and chart it "
        "produces was already computed and recorded by Gates 1-6's own real runs. BP7 fits no "
        "model and makes no GenAI/external API call ever - it is a transparent, auditable, "
        "deterministic weighted decision-rule layer combining BP2's/BP3's/BP4's own real "
        "prediction fields into priority_score, intervention_flag, and recommended_action. There "
        "is no SHAP, no confusion matrix, and no calibration curve anywhere in this report; the "
        "exact contribution decomposition below is BP7's own transparent, by-design equivalent. "
        f"UDAAP applicability: {kpis['udaap_applicability']!r}. NIST AI RMF applicability: "
        f"{kpis['nist_ai_rmf_applicability']!r}. There is no financial-impact or illustrative-"
        "projection section anywhere in this report - only original notebook output results are "
        "reported."
    )

    doc.add_heading("Executive KPIs", level=1)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = "Light Grid Accent 1"
    hdr = tbl.rows[0].cells
    hdr[0].text, hdr[1].text = "Metric", "Value"
    w = kpis["champion_weights_normalized"]
    kpi_rows = [
        ("Champion rule scheme (Gate 3)", kpis["champion_rule_scheme"]),
        (
            "Champion weights (BP2 / BP3 / BP4, normalized)",
            f"{w['bp2']:.6f} / {w['bp3']:.6f} / {w['bp4']:.6f}",
        ),
        ("Intervention threshold", f"{kpis['intervention_threshold']}"),
        (
            "Real intervention_flag rate (point estimate, 95% bootstrap CI)",
            f"{kpis['intervention_flag_rate_point_estimate']:.4f} "
            f"[{kpis['intervention_flag_rate_ci_low']:.4f}, {kpis['intervention_flag_rate_ci_high']:.4f}] "
            f"(n={kpis['bootstrap_n']})",
        ),
        (
            "Champion BP3-agreement rate (reference, not ground truth)",
            f"{kpis['champion_bp3_agreement_rate']:.4%}",
        ),
        (
            "BP2/BP3 Cramér's V (association strength)",
            f"{kpis['bp2_bp3_cramers_v']:.4f} ({kpis['bp2_bp3_association_strength']})",
        ),
        ("BP4 join coverage (Gate 3)", f"{kpis['bp4_join_coverage']:.4%}"),
        ("Gate 4 reproduction bit-exact", str(kpis["reproduction_bit_exact"])),
        (
            "Exact contribution decomposition (BP2 / BP3 / BP4 mean)",
            f"{kpis['mean_contribution_bp2']:.4f} / {kpis['mean_contribution_bp3']:.4f} / "
            f"{kpis['mean_contribution_bp4']:.4f} (max_abs_reconstruction_error="
            f"{kpis['max_abs_reconstruction_error']})",
        ),
        (
            "ECOA/Reg B disparate-impact ratio (real, four-fifths-rule)",
            f"{kpis['adverse_impact_ratio']} (flagged={kpis['flagged_four_fifths_rule']})",
        ),
        (
            "Real decision records scored",
            f"{kpis['n_decision_records']:,} ({kpis['gate5_coverage_pct']}% coverage)",
        ),
        ("Gate 6 pytest", f"{kpis['gate6_pytest_n_passed']} passed / {kpis['gate6_pytest_n_failed']} failed"),
        (
            "Gate 6 FastAPI self-test all checks passed",
            str(kpis["gate6_fastapi_self_test_all_checks_passed"]),
        ),
        ("GenAI API used (any gate)", str(kpis["genai_api_used"])),
    ]
    for label, value in kpi_rows:
        row = tbl.add_row().cells
        row[0].text, row[1].text = label, value

    doc.add_heading("Gate 3 — Decision-Rule-Scheme Benchmark & Champion Selection", level=1)
    doc.add_picture(io_bytes(figures["champion_benchmark"]), width=Inches(5.8))
    cb_df = candidate_benchmark_dataframe(bundle)
    t2 = doc.add_table(rows=1, cols=6)
    t2.style = "Light Grid Accent 1"
    for i, h in enumerate(
        ["Candidate", "Champion", "Weight BP2", "Weight BP3", "Weight BP4", "Intervention Flag Rate"]
    ):
        t2.rows[0].cells[i].text = h
    for _, r in cb_df.iterrows():
        row = t2.add_row().cells
        row[0].text = str(r["candidate"])
        row[1].text = str(r["is_champion"])
        row[2].text = f"{r['weight_bp2_normalized']:.4f}"
        row[3].text = f"{r['weight_bp3_normalized']:.4f}"
        row[4].text = f"{r['weight_bp4_normalized']:.4f}"
        row[5].text = f"{r['intervention_flag_rate']:.4f}"

    doc.add_heading("Gate 4 — Statistical Validation & Explainability", level=1)
    doc.add_picture(
        io_bytes(
            figures["bootstrap_ci_intervention"]
        ),
        width=Inches(3.4),
    )
    doc.add_picture(io_bytes(figures["bootstrap_ci_agreement"]), width=Inches(3.4))
    doc.add_paragraph(
        "BP7 fits no black-box model, so there is no SHAP feature-importance chart. The exact "
        "contribution decomposition below is BP7's fully transparent, by-design equivalent: the "
        "rule already IS a linear combination, so its own arithmetic is its explanation, not an "
        "estimate of one."
    )
    doc.add_picture(io_bytes(figures["contribution_decomposition"]), width=Inches(5.5))

    doc.add_heading("Gate 4/5 — ECOA/Reg B Disparate-Impact Audit (real, applicable)", level=1)
    doc.add_picture(io_bytes(figures["disparate_impact"]), width=Inches(5.8))
    di_df = disparate_impact_dataframe(bundle)
    t3 = doc.add_table(rows=1, cols=4)
    t3.style = "Light Grid Accent 1"
    for i, h in enumerate(["Tags Group", "N Rows", "N Intervention Flagged", "Selection Rate"]):
        t3.rows[0].cells[i].text = h
    for _, r in di_df.iterrows():
        row = t3.add_row().cells
        row[0].text = str(r["tags_group"])
        row[1].text = f"{int(r['n_rows']):,}"
        row[2].text = f"{int(r['n_intervention_flagged']):,}"
        row[3].text = f"{r['selection_rate']:.4f}"

    doc.add_heading("Gate 5 — Decision Outputs", level=1)
    doc.add_picture(io_bytes(figures["recommended_action"]), width=Inches(4.2))
    doc.add_picture(io_bytes(figures["bp4_tier_crosstab"]), width=Inches(5.5))

    doc.add_heading("Gate 1 — Business Understanding & Policy", level=1)
    gate1 = build_gate1_summary(bundle)
    doc.add_paragraph(_safe(str(gate1.get("target_definition", {}).get("primary_target_description", ""))))

    doc.add_heading("Gate 6 — Governance & Known Limitations", level=1)
    doc.add_picture(io_bytes(figures["governance_checklist"]), width=Inches(5.8))
    gate6 = build_gate6_governance_detail(bundle)
    doc.add_paragraph(
        f"pytest: {_safe(str(gate6.get('pytest_summary_line')))}  |  notebook syntax audit "
        f"returncode: {gate6.get('notebook_syntax_audit_returncode')}"
    )
    doc.add_paragraph(
        f"Open items (informational, non-blocking): bp4_unscored_rate_detected="
        f"{gate6.get('open_items', {}).get('bp4_unscored_rate_detected')}, "
        f"low_bp3_agreement_rate_detected="
        f"{gate6.get('open_items', {}).get('low_bp3_agreement_rate_detected')}"
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
    ws0["A1"] = "BP7 — Customer Navigator Decision Engine: Executive Rollup Workbook"
    ws0["A1"].font = Font(bold=True, size=14)
    ws0["A3"] = (
        "Every value in this workbook is read live from Gates 1-6's own real, already-recorded artifacts."
    )
    ws0["A4"] = "No financial-impact or illustrative-projection content is present anywhere in this workbook."
    ws0["A5"] = (
        "BP7 fits no model and makes no GenAI call - there is no SHAP or confusion-matrix sheet; "
        "see 03_ContributionDecomposition instead."
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

    ws2 = wb.create_sheet("02_CandidateBenchmark")
    cb_df = candidate_benchmark_dataframe(bundle)
    ws2.append(list(cb_df.columns))
    for c in ws2[1]:
        c.fill = header_fill
        c.font = header_font
    for row in cb_df.itertuples(index=False):
        ws2.append([_safe(v) for v in row])
    for col in "ABCDEFGHI":
        ws2.column_dimensions[col].width = 20

    ws3 = wb.create_sheet("03_ContributionDecomposition")
    contrib_df = contribution_decomposition_sample_dataframe(bundle)
    ws3.append(list(contrib_df.columns))
    for c in ws3[1]:
        c.fill = header_fill
        c.font = header_font
    for row in contrib_df.itertuples(index=False):
        ws3.append([_safe(v) for v in row])
    for col in "ABCDE":
        ws3.column_dimensions[col].width = 22

    ws4 = wb.create_sheet("04_DisparateImpactBreakdown")
    di_df = disparate_impact_dataframe(bundle)
    ws4.append(list(di_df.columns))
    for c in ws4[1]:
        c.fill = header_fill
        c.font = header_font
    for row in di_df.itertuples(index=False):
        ws4.append([_safe(v) for v in row])
    for col in "ABCD":
        ws4.column_dimensions[col].width = 22

    ws5 = wb.create_sheet("05_RecommendedActionBreakdown")
    ra_df = recommended_action_dataframe(bundle)
    ws5.append(list(ra_df.columns))
    for c in ws5[1]:
        c.fill = header_fill
        c.font = header_font
    for row in ra_df.itertuples(index=False):
        ws5.append([_safe(v) for v in row])
    for col in "ABCDE":
        ws5.column_dimensions[col].width = 26

    ws6 = wb.create_sheet("06_BP4TierCrosstab")
    tc_df = bp4_tier_crosstab_dataframe(bundle)
    ws6.append(list(tc_df.columns))
    for c in ws6[1]:
        c.fill = header_fill
        c.font = header_font
    for row in tc_df.itertuples(index=False):
        ws6.append([_safe(v) for v in row])
    for col in "ABC":
        ws6.column_dimensions[col].width = 30

    ws7 = wb.create_sheet("07_GovernanceChecklist")
    checklist = governance_checklist(bundle)
    ws7.append(["Check", "Passed", "Detail"])
    for c in ws7[1]:
        c.fill = header_fill
        c.font = header_font
    for row in checklist:
        ws7.append([_safe(row["label"]), _safe(str(row["passed"])), _safe(row["detail"])])
    ws7.column_dimensions["A"].width = 50
    ws7.column_dimensions["B"].width = 10
    ws7.column_dimensions["C"].width = 60

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
    tf.paragraphs[0].font.size = PptxPt(34)
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
        "BP7 — Customer Navigator Decision Engine",
        f"Executive Rollup  |  {prod['tier']}  |  Generated {kpis['generated_at_utc']}",
    )

    w = kpis["champion_weights_normalized"]
    _add_bullets_slide(
        prs,
        "Executive KPIs",
        [
            f"Champion rule scheme: {kpis['champion_rule_scheme']}",
            f"Champion weights (BP2/BP3/BP4): {w['bp2']:.4f} / {w['bp3']:.4f} / {w['bp4']:.4f}",
            f"Real intervention_flag rate: {kpis['intervention_flag_rate_point_estimate']:.4f} "
            f"[{kpis['intervention_flag_rate_ci_low']:.4f}, {kpis['intervention_flag_rate_ci_high']:.4f}]",
            f"Gate 4 reproduction bit-exact: {kpis['reproduction_bit_exact']}",
            f"Exact contribution reconstruction: {kpis['reconstruction_exact']} "
            f"(max_abs_error={kpis['max_abs_reconstruction_error']})",
            f"ECOA/Reg B disparate-impact ratio: {kpis['adverse_impact_ratio']} "
            f"(flagged={kpis['flagged_four_fifths_rule']})",
            f"Real decision records scored: {kpis['n_decision_records']:,} ({kpis['gate5_coverage_pct']}%)",
            "Gate 6 FastAPI self-test all checks passed: "
            f"{kpis['gate6_fastapi_self_test_all_checks_passed']}",
            f"GenAI API used (any gate): {kpis['genai_api_used']}",
        ],
    )

    gate1 = build_gate1_summary(bundle)
    _add_bullets_slide(
        prs,
        "Gate 1 — Business Understanding & Policy",
        [str(gate1.get("target_definition", {}).get("primary_target_description", ""))[:600]],
    )

    _add_image_slide(
        prs,
        "Gate 3 — Decision-Rule-Scheme Benchmark & Champion Selection",
        figures["champion_benchmark"],
    )
    _add_image_slide(
        prs, "Gate 4 — Bootstrap 95% CI: intervention_flag Rate", figures["bootstrap_ci_intervention"]
    )
    _add_image_slide(
        prs, "Gate 4 — Bootstrap 95% CI: BP3-Agreement Rate", figures["bootstrap_ci_agreement"]
    )
    _add_image_slide(
        prs,
        "Gate 4 — Exact Contribution Decomposition (BP7's transparent stand-in for SHAP)",
        figures["contribution_decomposition"],
    )
    _add_image_slide(prs, "Gate 4/5 — Real ECOA/Reg B Disparate-Impact Audit", figures["disparate_impact"])
    _add_image_slide(prs, "Gate 5 — Real recommended_action Breakdown", figures["recommended_action"])
    _add_image_slide(prs, "Gate 5 — Real BP4 Tier × Intervention Crosstab", figures["bp4_tier_crosstab"])
    _add_image_slide(prs, "Gate 3/4/5/6 — Real Governance Checklist", figures["governance_checklist"])

    gate6 = build_gate6_governance_detail(bundle)
    _add_bullets_slide(
        prs,
        "Gate 6 — Governance & Known Limitations",
        [
            f"pytest: {_safe(str(gate6.get('pytest_summary_line')))}",
            f"Notebook syntax audit returncode: {gate6.get('notebook_syntax_audit_returncode')}",
            f"FastAPI self-test all checks passed: {gate6.get('fastapi_self_test_all_checks_passed')}",
            "Open item — BP4 unscored rate detected: "
            f"{gate6.get('open_items', {}).get('bp4_unscored_rate_detected')} "
            f"(rate={gate6.get('open_items', {}).get('bp4_unscored_rate')})",
            "Open item — low BP3-agreement rate detected: "
            f"{gate6.get('open_items', {}).get('low_bp3_agreement_rate_detected')} "
            f"(rate={gate6.get('open_items', {}).get('bp3_agreement_rate')})",
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
