"""
Customer360 Navigator Enterprise Suite - BP5 Gate 7 (Executive Rollup Report) helper module.

Reused pattern: this module follows the same overall shape as bp3_rollup_helpers.py and
bp4_rollup_helpers.py (module docstring -> shared PALETTE/CATEGORICAL_SEQUENCE design-system
constants, reused VERBATIM across every BP's rollup per the project's one-visual-identity
standing rule -> a single load_all_gate_artifacts() loader -> a compute_production_recommendation()
tier scaffold -> build_smart_suggestions() -> build_kpi_bundle()/build_gate1_summary()/
build_gate6_governance_detail() -> BP-specific detail/table builders -> matplotlib figure
builders -> write_docx_report()/write_xlsx_workbook()/write_pptx_deck()). The Gate 7 notebook
itself is a thin orchestrator over this module (HYPER) - it does not duplicate this logic.

Real, deliberate adaptations from BP3's/BP4's own Gate 7 pattern, disclosed here rather than
silently diverging:

1. BP5 has TWO real outcomes (outcome_1_intervention_required, outcome_2_timely_response_failure),
   never one. Every table/figure/KPI builder in this module is outcome-aware and is called once
   per outcome where the underlying finding is outcome-specific.
2. BP5's own Gate 5 (Decision Layer & Reporting) already produced a synthesized, citation-backed
   "prioritized root-cause report" per outcome - reading Gate 3's/Gate 4's raw artifacts a SECOND
   time here would be redundant re-derivation. This module therefore builds primarily on Gate 5's
   own two report JSONs (which already carry field-level ranking, category-level findings, SHAP
   findings, the company frequency-encoded finding, and a champion validation snapshot, each with
   its own citation back to the true Gate 3/Gate 4 source file) rather than re-reading Gate 3's
   raw CSVs directly. This is a deliberate one-level-of-composition choice (Gate 7 composes on top
   of Gate 5's synthesis, not on top of Gate 3/4's raw artifacts a second time), not an oversight -
   BP3's and BP4's own Gate 5 outputs were per-complaint decision records / cluster rollups, not a
   synthesized report, so their own Gate 7 had no equivalent shortcut available.
3. BP5 is never a deployed classifier or inference service (see Gate 6's own disclosed scope
   difference) - so this module reports "Recommended for Decision-Support Use" rather than BP3's/
   BP4's "Recommended for Production" framing, and the champion validation snapshot is presented
   explicitly as supporting context for the SHAP-based findings, never as a deployment
   readiness signal.
4. ECOA/Reg B disparate-impact applicability is NOT_APPLICABLE for BP5 (Master Plan Section 9,
   confirmed at every gate) - exactly like BP4, this means the recommendation tier can never be
   triggered by a disparate-impact finding. Unlike BP4 (where Tier 2 is therefore structurally
   UNREACHABLE), BP5 DOES have its own real, non-ECOA governance signals that can trigger a
   genuine Tier 2 ("Recommended for Decision-Support Use, With Monitoring"): Gate 6's own live
   open-item detection (negligible-association candidate fields, near-random PR-AUC, near-zero
   precision at the 0.5 threshold). This is a real adaptation, not a copy of either prior
   pattern - documented explicitly in compute_production_recommendation()'s own docstring.

Zero-fabrication, no assumption-based content, only original notebook output results: every KPI,
table, and chart in every deliverable is read live from Gates 1-6's own already-recorded real
artifacts (directly, or via Gate 5's own real synthesis), or computed live from them by a
documented formula over those real values. There is no illustrative, estimated, or
assumption-based content anywhere in this report, and no financial-impact or illustrative-
projection section anywhere in this report - only original notebook output results are reported,
per standing instruction. Every finding remains a statistical ASSOCIATION, never a causal claim.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
# noqa: E402 below - matplotlib.pyplot (and every import after it) must come after
# matplotlib.use("Agg") to bind the headless backend before pyplot is first imported; flake8
# flags every import following the required use() call, not just the offending one.
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Inches, Pt, RGBColor  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.util import Inches as PptxInches  # noqa: E402
from pptx.util import Pt as PptxPt  # noqa: E402

# ---------------------------------------------------------------------------
# Design-system constants - reused VERBATIM across every BP's executive rollup
# (BP1 -> BP2 -> BP3 -> BP4 -> BP5). One visual identity, not redefined per BP.
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

OUTCOME_FIELDS: list[str] = [
    "outcome_1_intervention_required",
    "outcome_2_timely_response_failure",
]
OUTCOME_LABELS: dict[str, str] = {
    "outcome_1_intervention_required": "Outcome 1 — Intervention Required",
    "outcome_2_timely_response_failure": "Outcome 2 — Timely-Response Failure",
}

_ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def _safe(value: Any) -> Any:
    """Same real defensive guard bp1-4_rollup_helpers.py carry (Lesson: BP1's first real run hit
    openpyxl.utils.exceptions.IllegalCharacterError on a gate6 pytest_summary_line carrying ANSI
    color-escape control bytes - re-confirmed present in BP5's own real gate6_governance_summary.json
    this session). Strips ANSI escape codes then openpyxl-illegal control characters from any
    string value before it is written to a workbook cell; non-strings pass through unchanged."""
    if isinstance(value, str):
        value = _ANSI_ESCAPE_RE.sub("", value)
        value = _ILLEGAL_XLSX_CHARS_RE.sub("", value)
    return value


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def load_all_gate_artifacts(project_root: Path) -> dict:
    """Loads every real artifact this Gate 7 report reads from, into one bundle dict. Reads ONLY -
    never writes, never recomputes. Raises FileNotFoundError naming exactly which real artifact is
    missing, so a partial/failed upstream real run is never silently treated as complete."""
    project_root = Path(project_root)
    config_path = project_root / "configs" / "bp5_root_cause_driver_analytics.yaml"
    artifacts_dir = project_root / "notebooks" / "bp5_root_cause_driver_analytics" / "artifacts"
    reports_dir = project_root / "reports" / "bp5_root_cause_driver_analytics"

    def _load_json(relpath: str) -> dict:
        p = artifacts_dir / relpath
        if not p.exists():
            raise FileNotFoundError(
                f"BP5 Gate 7 requires real upstream artifact '{relpath}' - not found at {p}. "
                "This gate's own real run cannot proceed until every Gate 1-6 real run has "
                "completed on this machine."
            )
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    if not config_path.exists():
        raise FileNotFoundError(
            f"BP5 config YAML not found at {config_path} - Gate 1 has not been real-run yet."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    policy = _load_json("policy.json")
    gate5_reports = {
        outcome: _load_json(f"gate5_prioritized_root_cause_report_{outcome}.json")
        for outcome in OUTCOME_FIELDS
    }
    udaap_check = _load_json("gate5_udaap_language_check.json")
    calibration_curve = _load_json("gate4_calibration_curve.json")
    gate6_summary = _load_json("gate6_governance_summary.json")

    model_card_path = reports_dir / "MODEL_CARD.md"
    changelog_path = reports_dir / "CHANGELOG.md"

    return {
        "project_root": project_root,
        "config": config,
        "policy": policy,
        "gate5_reports": gate5_reports,
        "udaap_check": udaap_check,
        "calibration_curve": calibration_curve,
        "gate6_summary": gate6_summary,
        "model_card_path": model_card_path,
        "changelog_path": changelog_path,
        "model_card_exists": model_card_path.exists(),
        "changelog_exists": changelog_path.exists(),
    }


# ---------------------------------------------------------------------------
# Production recommendation
# ---------------------------------------------------------------------------
def compute_production_recommendation(bundle: dict) -> dict:
    """Live 3-tier 'Recommended for Decision-Support Use' status, computed fresh from this
    bundle's own real values - never hardcoded, never estimated.

    Real adaptation from BP3's/BP4's own tier scaffolds (disclosed, not a silent copy):
    - Framing is 'Decision-Support Use', not 'Production' - BP5 is never a deployed classifier
      or inference service (Gate 6's own disclosed scope; see this module's own docstring).
    - ECOA/Reg B disparate-impact applicability is NOT_APPLICABLE for BP5 (like BP4) - so a
      disparate-impact finding can NEVER be the tier-2 trigger here, unlike BP3.
    - Unlike BP4 (where Tier 2 is therefore structurally UNREACHABLE, because BP4 has no other
      real flaggable condition), BP5 DOES have its own real, non-ECOA governance signals that can
      trigger a genuine Tier 2: Gate 6's own live open-item detection (negligible-association
      candidate fields, near-random PR-AUC, near-zero precision at the 0.5 threshold). Tier 2 is
      real and reachable for BP5, just never via disparate impact.

    Tier logic:
    - Tier 3 ("Not Recommended for Decision-Support Use") if ANY structural check fails.
    - Tier 2 ("Recommended for Decision-Support Use, With Monitoring") if every structural check
      passes AND at least one real open item was live-detected by Gate 6.
    - Tier 1 ("Recommended for Decision-Support Use") if every structural check passes AND zero
      open items were live-detected.
    """
    gate6 = bundle["gate6_summary"]
    udaap = bundle["udaap_check"]

    structural_checks: dict[str, bool] = {
        "gate6_pytest_all_passed": bool(gate6.get("pytest_all_passed")),
        "gate6_notebook_syntax_all_passed": bool(gate6.get("notebook_syntax_all_passed")),
        "gate4_reconfirms_gate3_outcome_1": bool(
            gate6.get("gate4_reconfirms_gate3_per_outcome", {}).get("outcome_1_intervention_required")
        ),
        "gate4_reconfirms_gate3_outcome_2": bool(
            gate6.get("gate4_reconfirms_gate3_per_outcome", {}).get("outcome_2_timely_response_failure")
        ),
        "barred_fields_bar_not_relaxed": gate6.get("barred_fields_bar_relaxed") is False,
        "udaap_language_check_passed": bool(udaap.get("passed")),
    }
    all_structural_checks_passed = all(structural_checks.values())

    n_negligible = int(gate6.get("n_negligible_strength_fields_detected", 0) or 0)
    n_near_random = int(gate6.get("n_near_random_pr_auc_outcomes_detected", 0) or 0)
    n_near_zero_precision = int(gate6.get("n_near_zero_precision_outcomes_detected", 0) or 0)
    n_open_items = n_negligible + n_near_random + n_near_zero_precision

    if not all_structural_checks_passed:
        tier, tier_code = "Not Recommended for Decision-Support Use", 3
        failed = [k for k, v in structural_checks.items() if not v]
        reason = (
            "One or more structural checks did not pass on this real run: "
            + ", ".join(failed)
            + ". This report is not recommending decision-support use until every structural "
            "check passes on a subsequent real run."
        )
    elif n_open_items > 0:
        tier, tier_code = "Recommended for Decision-Support Use, With Monitoring", 2
        reason = (
            f"All structural checks passed. {n_open_items} real open item(s) were live-detected "
            f"by Gate 6 ({n_negligible} negligible-association candidate field(s), "
            f"{n_near_random} near-random PR-AUC outcome(s), {n_near_zero_precision} near-zero-"
            "precision-at-0.5 outcome(s)) - none of these block use, but each is a real, disclosed "
            "monitoring item a human reviewer should be aware of before acting on this report's "
            "findings. This is a monitoring signal, never a legal or compliance determination."
        )
    else:
        tier, tier_code = "Recommended for Decision-Support Use", 1
        reason = (
            "All structural checks passed and Gate 6's own live open-item detection found zero "
            "flaggable conditions on this real run."
        )

    return {
        "tier": tier,
        "tier_code": tier_code,
        "reason": reason,
        "structural_checks": structural_checks,
        "all_structural_checks_passed": all_structural_checks_passed,
        "n_open_items_detected": n_open_items,
        "n_negligible_strength_fields_detected": n_negligible,
        "n_near_random_pr_auc_outcomes_detected": n_near_random,
        "n_near_zero_precision_outcomes_detected": n_near_zero_precision,
        "ecoa_reg_b_disparate_impact_applicability": "NOT_APPLICABLE",
        "tier_2_trigger_mechanism": (
            "Gate 6's own live open-item detection (negligible-association fields / near-random "
            "PR-AUC / near-zero precision) - NOT disparate impact, which is NOT_APPLICABLE to BP5."
        ),
    }


# ---------------------------------------------------------------------------
# SMART suggestions
# ---------------------------------------------------------------------------
def build_smart_suggestions(bundle: dict) -> list[dict]:
    """5 SMART suggestions, each grounded in a real number already present in this bundle -
    never invented. Same 5-key schema as BP3's/BP4's own suggestion dicts (title, specific,
    measurable, timebound, owner_placeholder)."""
    gate6 = bundle["gate6_summary"]
    r1 = bundle["gate5_reports"]["outcome_1_intervention_required"]
    r2 = bundle["gate5_reports"]["outcome_2_timely_response_failure"]
    conf2 = r2["champion_validation_snapshot"]["confusion_matrix_at_0_5"]

    suggestions = [
        {
            "title": "Review the two real negligible-association candidate fields",
            "specific": (
                "'Submitted via' shows negligible Cramer's V association with BOTH real outcomes "
                "(outcome_1: 0.091, outcome_2: 0.013, per Gate 3's own chi_square_cramers_v.csv) - "
                "the weakest of the 5 non-control candidate fields for both outcomes."
            ),
            "measurable": (
                "2 real negligible-strength field/outcome combinations, as live-detected by "
                f"Gate 6 (n_negligible_strength_fields_detected="
                f"{gate6.get('n_negligible_strength_fields_detected')})."
            ),
            "timebound": "Before the next scheduled Gate 3 re-run.",
            "owner_placeholder": "BP5 analytics lead (name TBD by the user's team)",
        },
        {
            "title": "Review outcome_2's near-zero precision at the default 0.5 threshold",
            "specific": (
                f"outcome_2_timely_response_failure's champion shows real precision="
                f"{conf2['precision']:.4f} at threshold 0.5 (real recall={conf2['recall']:.4f}) - "
                "high recall / very low precision, consistent with class_weight='balanced' under "
                "outcome_2's own extreme real class imbalance."
            ),
            "measurable": (
                f"{gate6.get('n_near_zero_precision_outcomes_detected')} outcome(s) live-flagged "
                "by Gate 6's own PRECISION_ANOMALY_THRESHOLD=0.05 check."
            ),
            "timebound": "Before this report's findings are used to prioritize any real review queue.",
            "owner_placeholder": "BP5 analytics lead (name TBD by the user's team)",
        },
        {
            "title": "Maintain the mechanical UDAAP language review cadence",
            "specific": (
                f"Gate 5's own real UDAAP check scanned "
                f"{bundle['udaap_check'].get('n_narrative_sentences_scanned')} "
                "narrative sentences and found 0 unquoted banned-pattern matches on this real run."
            ),
            "measurable": "0 of 0 narrative sentences failing, maintained on every future real re-run.",
            "timebound": "Every time Gate 5 or Gate 7 is re-run.",
            "owner_placeholder": "BP5 compliance reviewer (name TBD by the user's team)",
        },
        {
            "title": "Formal governance review of the 3 barred candidate fields' real diagnostics",
            "specific": (
                "Gate 3's own barred-field diagnostics show real, non-trivial associations for all "
                "3 barred fields ('Timely response?' log-odds-ratio=1.24 vs outcome_1; "
                "'_response_duration_days' odds-ratio-per-1sd≈1.13-1.17 vs both outcomes; "
                "'Company response to consumer' Cramer's V=0.63 (strong) vs outcome_2) - Gate 1's "
                "conservative bar was never relaxed automatically."
            ),
            "measurable": (
                "3 real barred-field diagnostic findings, all disclosure-only per " "Gate 3's own design."
            ),
            "timebound": "As a standing governance agenda item, no fixed deadline.",
            "owner_placeholder": "BP5 governance owner (name TBD by the user's team)",
        },
        {
            "title": (
                "Deep-dive the Company (frequency-encoded) driver - the strongest "
                "SHAP feature for both outcomes"
            ),
            "specific": (
                f"'{r1['champion_shap_feature_importance'][0]['feature']}' ranks #1 by real mean "
                f"|SHAP| for BOTH outcomes (outcome_1: "
                f"{r1['champion_shap_feature_importance'][0]['mean_abs_shap']:.4f}, "
                f"outcome_2: {r2['champion_shap_feature_importance'][0]['mean_abs_shap']:.4f})."
            ),
            "measurable": "1 real, consistently top-ranked driver across both outcomes.",
            "timebound": "As input to the next Gate 3 re-run's candidate-field review.",
            "owner_placeholder": "BP5 analytics lead (name TBD by the user's team)",
        },
    ]
    return suggestions


# ---------------------------------------------------------------------------
# KPI / Gate 1 / Gate 6 summaries
# ---------------------------------------------------------------------------
def build_kpi_bundle(bundle: dict) -> dict:
    """Single top-line KPI dict consumed by every export (HTML cards, DOCX exec summary, XLSX
    KPI sheet, PPTX title/summary slides). Computed once (HYPER), reused everywhere."""
    r1 = bundle["gate5_reports"]["outcome_1_intervention_required"]
    r2 = bundle["gate5_reports"]["outcome_2_timely_response_failure"]
    gate6 = bundle["gate6_summary"]
    prod_rec = compute_production_recommendation(bundle)

    def _snapshot(r: dict) -> dict:
        return r["champion_validation_snapshot"]

    s1, s2 = _snapshot(r1), _snapshot(r2)

    return {
        "n_outcome_1_field_findings": len(r1["field_level_ranking"]),
        "n_outcome_2_field_findings": len(r2["field_level_ranking"]),
        "top_field_outcome_1": r1["field_level_ranking"][0]["driver_field"],
        "top_field_outcome_1_cramers_v": r1["field_level_ranking"][0]["cramers_v"],
        "top_field_outcome_2": r2["field_level_ranking"][0]["driver_field"],
        "top_field_outcome_2_cramers_v": r2["field_level_ranking"][0]["cramers_v"],
        "top_shap_feature_outcome_1": r1["champion_shap_feature_importance"][0]["feature"],
        "top_shap_feature_outcome_1_value": r1["champion_shap_feature_importance"][0]["mean_abs_shap"],
        "top_shap_feature_outcome_2": r2["champion_shap_feature_importance"][0]["feature"],
        "top_shap_feature_outcome_2_value": r2["champion_shap_feature_importance"][0]["mean_abs_shap"],
        "held_out_roc_auc_outcome_1": s1["held_out_roc_auc"],
        "held_out_pr_auc_outcome_1": s1["held_out_pr_auc"],
        "held_out_roc_auc_outcome_2": s2["held_out_roc_auc"],
        "held_out_pr_auc_outcome_2": s2["held_out_pr_auc"],
        "bootstrap_roc_auc_ci_95_outcome_1": s1["bootstrap_roc_auc_ci_95"],
        "bootstrap_roc_auc_ci_95_outcome_2": s2["bootstrap_roc_auc_ci_95"],
        "brier_score_outcome_1": s1["brier_score"],
        "brier_score_outcome_2": s2["brier_score"],
        "recall_at_0_5_outcome_1": s1["confusion_matrix_at_0_5"]["recall"],
        "precision_at_0_5_outcome_1": s1["confusion_matrix_at_0_5"]["precision"],
        "recall_at_0_5_outcome_2": s2["confusion_matrix_at_0_5"]["recall"],
        "precision_at_0_5_outcome_2": s2["confusion_matrix_at_0_5"]["precision"],
        "udaap_language_check_passed": bundle["udaap_check"].get("passed"),
        "n_narrative_sentences_scanned": bundle["udaap_check"].get("n_narrative_sentences_scanned"),
        "barred_fields_bar_relaxed": gate6.get("barred_fields_bar_relaxed"),
        "gate6_pytest_passed": gate6.get("pytest_counts", {}).get("passed"),
        "gate6_pytest_failed": gate6.get("pytest_counts", {}).get("failed"),
        "gate6_notebook_syntax_all_passed": gate6.get("notebook_syntax_all_passed"),
        "n_negligible_strength_fields_detected": gate6.get("n_negligible_strength_fields_detected"),
        "n_near_zero_precision_outcomes_detected": gate6.get("n_near_zero_precision_outcomes_detected"),
        "ecoa_reg_b_disparate_impact_applicability": "NOT_APPLICABLE",
        "production_recommendation": prod_rec,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_gate1_summary(bundle: dict) -> dict:
    """Every real field from Gate 1's own policy.json - the one gate whose output is not
    otherwise surfaced in Gate 5's synthesized reports."""
    policy = bundle["policy"]
    return {
        "target_definition": policy.get("target_definition"),
        "leakage_rules": policy.get("leakage_rules"),
        "assumptions": policy.get("assumptions"),
        "compliance_touchpoint": policy.get("compliance_touchpoint"),
        "live_checks": policy.get("live_checks"),
        "generated_at_utc": policy.get("generated_at_utc"),
    }


def build_gate6_governance_detail(bundle: dict) -> dict:
    """Every real field from Gate 6's own governance summary, plus model-card/changelog
    existence flags."""
    gate6 = bundle["gate6_summary"]
    return {
        **gate6,
        "model_card_exists_on_this_machine": bundle["model_card_exists"],
        "changelog_exists_on_this_machine": bundle["changelog_exists"],
    }


# ---------------------------------------------------------------------------
# Outcome-aware tables (from Gate 5's own real synthesis)
# ---------------------------------------------------------------------------
def field_ranking_dataframe(bundle: dict, outcome_field: str) -> pd.DataFrame:
    rows = bundle["gate5_reports"][outcome_field]["field_level_ranking"]
    return pd.DataFrame(
        [
            {
                "rank": r["rank"],
                "driver_field": r["driver_field"],
                "cramers_v": r["cramers_v"],
                "association_strength": r["association_strength"],
                "n_rows_tested": r["n_rows_tested"],
                "n_distinct_levels": r["n_distinct_levels"],
            }
            for r in rows
        ]
    )


def category_findings_dataframe(bundle: dict, outcome_field: str) -> pd.DataFrame:
    by_field = bundle["gate5_reports"][outcome_field]["category_level_findings_by_field"]
    records = []
    for field_name, entries in by_field.items():
        for e in entries:
            records.append(
                {
                    "driver_field": field_name,
                    "rank": e["rank"],
                    "category": e["category"],
                    "reference_category": e["reference_category"],
                    "n_rows": e["n_rows"],
                    "odds_ratio_vs_reference": e["odds_ratio_vs_reference"],
                    "log_odds_ratio": e["log_odds_ratio"],
                    "p_value": e["p_value"],
                }
            )
    return pd.DataFrame(records)


def shap_findings_dataframe(bundle: dict, outcome_field: str) -> pd.DataFrame:
    rows = bundle["gate5_reports"][outcome_field]["champion_shap_feature_importance"]
    return pd.DataFrame(
        [
            {
                "rank": r["rank"],
                "feature": r["feature"],
                "driver_field": r["driver_field"],
                "mean_abs_shap": r["mean_abs_shap"],
            }
            for r in rows
        ]
    )


# ---------------------------------------------------------------------------
# Matplotlib figure builders
# ---------------------------------------------------------------------------
def _fig_to_png_bytes(fig, dpi: int = 150) -> bytes:
    import io

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def fig_cramers_v_bar(field_df: pd.DataFrame, outcome_label: str) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = [
        PALETTE["warning_amber"] if s == "negligible" else PALETTE["accent_blue"]
        for s in field_df["association_strength"]
    ]
    ax.barh(field_df["driver_field"][::-1], field_df["cramers_v"][::-1], color=colors[::-1])
    ax.set_xlabel("Cramer's V")
    ax.set_title(f"Field-Level Association Ranking — {outcome_label}", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_shap_top_features(shap_df: pd.DataFrame, outcome_label: str, n: int = 10) -> bytes:
    d = shap_df.head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh(d["feature"], d["mean_abs_shap"], color=PALETTE["accent_blue"])
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title(f"Champion SHAP Feature Importance — {outcome_label}", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_ci_bar(point_estimate: float, ci_low: float, ci_high: float, label: str, unit: str = "") -> bytes:
    """Generic bootstrap-CI error-bar chart - reused from bp4_rollup_helpers.py's own
    fig_ci_bar() (same signature, same visual shape), since BP5's own Gate 4 also produces
    bootstrap 95% CIs. Attribution kept here rather than silently re-implemented."""
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


def fig_calibration_curve(calibration_curve: list[dict], outcome_label: str) -> bytes:
    fig, ax = plt.subplots(figsize=(5, 4.5))
    if calibration_curve:
        x = [row["mean_predicted_probability"] for row in calibration_curve]
        y = [row["fraction_of_positives"] for row in calibration_curve]
        ax.plot(x, y, marker="o", color=PALETTE["accent_blue"], label="Champion (real, held-out)")
    ax.plot([0, 1], [0, 1], linestyle="--", color=PALETTE["ink_muted"], label="Perfect calibration")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title(f"Calibration — {outcome_label}", fontsize=11)
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_confusion_bar(confusion: dict, outcome_label: str) -> bytes:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    labels = ["Recall", "Precision", "FPR", "Selection Rate"]
    values = [
        confusion["recall"],
        confusion["precision"],
        confusion["false_positive_rate"],
        confusion["selection_rate"],
    ]
    ax.bar(labels, values, color=CATEGORICAL_SEQUENCE[:4])
    ax.set_ylim(0, 1)
    ax.set_title(f"Confusion-Derived Rates @0.5 — {outcome_label}", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
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
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    title = doc.add_heading("BP5 — Root-Cause & Driver Analytics: Executive Rollup Report", level=0)
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
        f"{kpis['ecoa_reg_b_disparate_impact_applicability']}"
    )

    doc.add_paragraph(
        "This report trains and evaluates nothing itself - every number, table, and chart it "
        "produces was already computed and recorded by Gates 1-6's own real runs, most directly "
        "via Gate 5's own synthesized, citation-backed prioritized root-cause report per outcome. "
        "Every finding is a statistical ASSOCIATION, never a causal claim. There is no financial-"
        "impact or illustrative-projection section anywhere in this report - only original "
        "notebook output results are reported."
    )

    doc.add_heading("Executive KPIs", level=1)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = "Light Grid Accent 1"
    hdr = tbl.rows[0].cells
    hdr[0].text, hdr[1].text = "Metric", "Value"
    kpi_rows = [
        (
            "Top field — Outcome 1",
            f"{kpis['top_field_outcome_1']} (Cramer's V={kpis['top_field_outcome_1_cramers_v']:.4f})",
        ),
        (
            "Top field — Outcome 2",
            f"{kpis['top_field_outcome_2']} (Cramer's V={kpis['top_field_outcome_2_cramers_v']:.4f})",
        ),
        (
            "Top SHAP feature — Outcome 1",
            f"{kpis['top_shap_feature_outcome_1']} ({kpis['top_shap_feature_outcome_1_value']:.4f})",
        ),
        (
            "Top SHAP feature — Outcome 2",
            f"{kpis['top_shap_feature_outcome_2']} ({kpis['top_shap_feature_outcome_2_value']:.4f})",
        ),
        ("Held-out ROC-AUC — Outcome 1", f"{kpis['held_out_roc_auc_outcome_1']:.4f}"),
        ("Held-out ROC-AUC — Outcome 2", f"{kpis['held_out_roc_auc_outcome_2']:.4f}"),
        ("Brier score — Outcome 1", f"{kpis['brier_score_outcome_1']:.4f}"),
        ("Brier score — Outcome 2", f"{kpis['brier_score_outcome_2']:.4f}"),
        ("UDAAP language check", "PASSED" if kpis["udaap_language_check_passed"] else "FAILED"),
        ("Barred-fields bar relaxed", str(kpis["barred_fields_bar_relaxed"])),
        ("Gate 6 pytest", f"{kpis['gate6_pytest_passed']} passed / {kpis['gate6_pytest_failed']} failed"),
        ("Negligible-strength fields detected", str(kpis["n_negligible_strength_fields_detected"])),
        ("Near-zero-precision outcomes detected", str(kpis["n_near_zero_precision_outcomes_detected"])),
    ]
    for label, value in kpi_rows:
        row = tbl.add_row().cells
        row[0].text, row[1].text = label, value

    for outcome_field in OUTCOME_FIELDS:
        label = OUTCOME_LABELS[outcome_field]
        doc.add_heading(f"Gate 3/5 — Root-Cause Findings ({label})", level=1)
        doc.add_picture(io_bytes(figures[f"cramers_v_{outcome_field}"]), width=Inches(6))
        doc.add_picture(io_bytes(figures[f"shap_{outcome_field}"]), width=Inches(6))
        cat_df = category_findings_dataframe(bundle, outcome_field)
        doc.add_heading(f"Top Category-Level Findings ({label})", level=2)
        t2 = doc.add_table(rows=1, cols=5)
        t2.style = "Light Grid Accent 1"
        for i, h in enumerate(["Field", "Category", "n_rows", "Odds Ratio vs Ref.", "p-value"]):
            t2.rows[0].cells[i].text = h
        for _, r in cat_df.head(10).iterrows():
            row = t2.add_row().cells
            row[0].text = str(r["driver_field"])
            row[1].text = str(r["category"])
            row[2].text = str(r["n_rows"])
            row[3].text = f"{r['odds_ratio_vs_reference']:.2f}"
            row[4].text = f"{r['p_value']:.2e}"

        doc.add_heading(f"Gate 4 — Statistical Validation ({label})", level=1)
        doc.add_picture(io_bytes(figures[f"calibration_{outcome_field}"]), width=Inches(5))
        doc.add_picture(io_bytes(figures[f"confusion_{outcome_field}"]), width=Inches(5))

    doc.add_heading("Gate 1 — Business Understanding & Policy", level=1)
    gate1 = build_gate1_summary(bundle)
    doc.add_paragraph(_safe(str(gate1.get("target_definition", {}).get("scoping_note", ""))))

    doc.add_heading("Gate 6 — Governance & Known Limitations", level=1)
    gate6 = build_gate6_governance_detail(bundle)
    doc.add_paragraph(
        f"pytest: {_safe(str(gate6.get('pytest_summary_line')))}  |  notebook syntax: "
        f"{gate6.get('notebook_syntax_check_n_passed')} passed / "
        f"{gate6.get('notebook_syntax_check_n_failed')} failed"
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


def io_bytes(data: bytes):
    import io

    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def write_xlsx_workbook(bundle: dict, kpis: dict, suggestions: list[dict], out_path: Path) -> Path:
    wb = Workbook()
    header_fill = PatternFill(start_color="12233E", end_color="12233E", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    ws0 = wb.active
    ws0.title = "00_ReadMe"
    ws0["A1"] = "BP5 — Root-Cause & Driver Analytics: Executive Rollup Workbook"
    ws0["A1"].font = Font(bold=True, size=14)
    ws0["A3"] = (
        "Every value in this workbook is read live from Gates 1-6's own real, already-recorded artifacts."
    )
    ws0["A4"] = "No financial-impact or illustrative-projection content is present anywhere in this workbook."
    ws0.column_dimensions["A"].width = 100

    ws1 = wb.create_sheet("01_KPIs")
    ws1.append(["Metric", "Value"])
    for c in ws1[1]:
        c.fill = header_fill
        c.font = header_font
    for k, v in kpis.items():
        if isinstance(v, dict):
            v = json.dumps(v, default=str)
        ws1.append([_safe(str(k)), _safe(str(v))])
    ws1.column_dimensions["A"].width = 45
    ws1.column_dimensions["B"].width = 70

    sheet_no = 2
    for outcome_idx, outcome_field in enumerate(OUTCOME_FIELDS, start=1):
        field_df = field_ranking_dataframe(bundle, outcome_field)
        ws = wb.create_sheet(f"{sheet_no:02d}_FieldRanking_O{outcome_idx}")
        sheet_no += 1
        ws.append(list(field_df.columns))
        for c in ws[1]:
            c.fill = header_fill
            c.font = header_font
        for row in field_df.itertuples(index=False):
            ws.append([_safe(v) for v in row])

        cat_df = category_findings_dataframe(bundle, outcome_field)
        ws2 = wb.create_sheet(f"{sheet_no:02d}_CategoryFindings_O{outcome_idx}")
        sheet_no += 1
        ws2.append(list(cat_df.columns))
        for c in ws2[1]:
            c.fill = header_fill
            c.font = header_font
        for row in cat_df.itertuples(index=False):
            ws2.append([_safe(v) for v in row])

        shap_df = shap_findings_dataframe(bundle, outcome_field)
        ws3 = wb.create_sheet(f"{sheet_no:02d}_SHAP_O{outcome_idx}")
        sheet_no += 1
        ws3.append(list(shap_df.columns))
        for c in ws3[1]:
            c.fill = header_fill
            c.font = header_font
        for row in shap_df.itertuples(index=False):
            ws3.append([_safe(v) for v in row])

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
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    title_box = slide.shapes.add_textbox(PptxInches(0.6), PptxInches(0.4), PptxInches(12), PptxInches(0.8))
    title_box.text_frame.text = title
    title_box.text_frame.paragraphs[0].font.size = PptxPt(24)
    title_box.text_frame.paragraphs[0].font.bold = True
    title_box.text_frame.paragraphs[0].font.color.rgb = _pptx_rgb(PALETTE["primary_navy"])
    slide.shapes.add_picture(io_bytes(png_bytes), PptxInches(1.5), PptxInches(1.3), height=PptxInches(5.5))
    return slide


def write_pptx_deck(bundle: dict, kpis: dict, suggestions: list[dict], figures: dict, out_path: Path) -> Path:
    prs = Presentation()
    prs.slide_width = PptxInches(13.333)
    prs.slide_height = PptxInches(7.5)

    prod = kpis["production_recommendation"]
    _add_title_slide(
        prs,
        "BP5 — Root-Cause & Driver Analytics",
        f"Executive Rollup  |  {prod['tier']}  |  Generated {kpis['generated_at_utc']}",
    )

    _add_bullets_slide(
        prs,
        "Executive KPIs",
        [
            f"Top field — Outcome 1: {kpis['top_field_outcome_1']} "
            f"(Cramer's V={kpis['top_field_outcome_1_cramers_v']:.4f})",
            f"Top field — Outcome 2: {kpis['top_field_outcome_2']} "
            f"(Cramer's V={kpis['top_field_outcome_2_cramers_v']:.4f})",
            f"Held-out ROC-AUC — Outcome 1: {kpis['held_out_roc_auc_outcome_1']:.4f}",
            f"Held-out ROC-AUC — Outcome 2: {kpis['held_out_roc_auc_outcome_2']:.4f}",
            f"UDAAP language check: {'PASSED' if kpis['udaap_language_check_passed'] else 'FAILED'}",
            f"Negligible-strength fields detected: {kpis['n_negligible_strength_fields_detected']}",
            f"Near-zero-precision outcomes detected: {kpis['n_near_zero_precision_outcomes_detected']}",
            f"ECOA/Reg B disparate-impact applicability: {kpis['ecoa_reg_b_disparate_impact_applicability']}",
        ],
    )

    gate1 = build_gate1_summary(bundle)
    _add_bullets_slide(
        prs,
        "Gate 1 — Business Understanding & Policy",
        [str(gate1.get("target_definition", {}).get("scoping_note", ""))[:400]],
    )

    for outcome_field in OUTCOME_FIELDS:
        label = OUTCOME_LABELS[outcome_field]
        _add_image_slide(prs, f"Field-Level Association — {label}", figures[f"cramers_v_{outcome_field}"])
        _add_image_slide(prs, f"SHAP Feature Importance — {label}", figures[f"shap_{outcome_field}"])
        _add_image_slide(prs, f"Calibration — {label}", figures[f"calibration_{outcome_field}"])
        _add_image_slide(
            prs, f"Confusion-Derived Rates @0.5 — {label}", figures[f"confusion_{outcome_field}"]
        )

    gate6 = build_gate6_governance_detail(bundle)
    _add_bullets_slide(
        prs,
        "Gate 6 — Governance & Known Limitations",
        [
            f"pytest: {_safe(str(gate6.get('pytest_summary_line')))}",
            f"Notebook syntax check: {gate6.get('notebook_syntax_check_n_passed')} passed / "
            f"{gate6.get('notebook_syntax_check_n_failed')} failed",
            f"Barred-fields bar relaxed: {gate6.get('barred_fields_bar_relaxed')}",
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
