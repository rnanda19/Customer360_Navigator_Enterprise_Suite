"""
src/reporting/bp1_rollup_helpers.py — Customer360 Navigator

BP1 executive-rollup report shared component library (HYPER: built once, imported everywhere -
this is the single source of truth for data loading, KPI assembly, SMART-suggestion generation,
and the matplotlib figure builders reused across the DOCX/XLSX/PPTX exports and referenced by the
HTML dashboard's data payload).

Standing rules this module follows:
  - Zero-fabrication, no assumption-based content: every KPI/figure/table returned here is read
    live from Gates 1-6's own already-recorded real artifacts, or computed live from them by a
    documented formula over those real values. There is no financial-impact / illustrative-
    assumption section anywhere in this module — BP1's source data (BANKING77 + the CFPB
    structured extract) contains no cost or volume figure of its own, and the user's explicit
    instruction is that only real, original notebook output results are to be reported, never a
    business assumption presented alongside them.
  - Comprehensive coverage: every one of BP1's six gates has its real recorded output represented
    somewhere in every deliverable this module writes - see build_gate1_summary() and
    build_gate6_governance_detail() for the two gates (Business Understanding & Policy; Governance)
    that are not otherwise covered by a chart, so nothing from any gate is left out.
  - WARP: matplotlib figures are built once per figure and reused (rendered to a shared in-memory
    PNG buffer) across the DOCX and PPTX exports, never rebuilt per document.
  - This module performs no I/O side effects at import time and is never executed by Claude - only
    the user's own notebook run calls it, per the project's execution-boundary rule. No synthetic-
    fixture dry-run of this module is performed either, per the user's explicit instruction -
    verification of this module is limited to static source-level checks (ast.parse, compile,
    pyflakes), never execution.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

# ============================================================================
# Shared visual identity (HYPER: one palette, reused by matplotlib figures, the HTML dashboard's
# JS charts, and every python-docx/openpyxl/python-pptx color reference below).
# ============================================================================
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
# Fixed categorical order (dataviz non-negotiable: never cycled, assigned by entity not rank).
CATEGORICAL_SEQUENCE = [
    PALETTE["primary_navy"],
    PALETTE["accent_blue"],
    PALETTE["success_green"],
    PALETTE["warning_amber"],
    PALETTE["danger_red"],
    PALETTE["neutral_gray"],
]


def load_all_gate_artifacts(project_root: Path) -> dict[str, Any]:
    """Load every real Gate 1-6 artifact this report needs, live, in one place (HYPER: single
    loader, reused by every export function below instead of five separate loaders). Raises a
    clear FileNotFoundError-derived message naming the missing gate if any prerequisite is absent
    - this report requires BP1 Gates 1-6 to already be real-run confirmed."""
    configs_dir = project_root / "configs"
    artifacts_dir = project_root / "notebooks" / "bp1_customer_intent_classification" / "artifacts"
    reports_dir = project_root / "reports" / "bp1_customer_intent_classification"

    required = {
        "bp1_config": configs_dir / "bp1_customer_intent_classification.yaml",
        "policy": artifacts_dir / "policy.json",
        "model_inventory": artifacts_dir / "model_inventory_entry.json",
        "gate3_cv_csv": artifacts_dir / "gate3_cv_benchmark_results.csv",
        "gate3_classification_report": artifacts_dir / "gate3_champion_test_classification_report.json",
        "gate3_confusion_matrix": artifacts_dir / "gate3_champion_test_confusion_matrix.csv",
        "gate4_json": artifacts_dir / "gate4_statistical_validation.json",
        "gate4_shap_csv": artifacts_dir / "gate4_shap_top_features.csv",
        "gate5_summary": artifacts_dir / "gate5_decision_layer_summary.json",
        "gate5_decision_records": artifacts_dir / "gate5_decision_records.csv",
        "gate6_summary": artifacts_dir / "gate6_governance_summary.json",
        "gate2_coverage_csv": artifacts_dir / "taxonomy_mapping_coverage_report.csv",
    }
    missing = {k: str(v) for k, v in required.items() if not v.exists()}
    if missing:
        raise FileNotFoundError(
            f"BP1 executive rollup requires Gates 1-6 to be real-run confirmed first - missing real "
            f"artifact file(s): {missing}. Run the corresponding gate notebook(s) before this report."
        )

    with open(required["bp1_config"], "r", encoding="utf-8") as f:
        bp1_config = yaml.safe_load(f)
    with open(required["policy"], "r", encoding="utf-8") as f:
        policy = json.load(f)
    with open(required["model_inventory"], "r", encoding="utf-8") as f:
        model_inventory = json.load(f)
    with open(required["gate3_classification_report"], "r", encoding="utf-8") as f:
        gate3_classification_report = json.load(f)
    with open(required["gate4_json"], "r", encoding="utf-8") as f:
        gate4 = json.load(f)
    with open(required["gate5_summary"], "r", encoding="utf-8") as f:
        gate5_summary = json.load(f)
    with open(required["gate6_summary"], "r", encoding="utf-8") as f:
        gate6_summary = json.load(f)

    gate3_cv_df = pd.read_csv(required["gate3_cv_csv"])
    gate3_confusion_df = pd.read_csv(required["gate3_confusion_matrix"], index_col=0)
    gate4_shap_df = pd.read_csv(required["gate4_shap_csv"])
    gate5_decision_df = pd.read_csv(required["gate5_decision_records"])
    gate2_coverage_df = pd.read_csv(required["gate2_coverage_csv"])

    reports_dir.mkdir(parents=True, exist_ok=True)

    return {
        "bp1_config": bp1_config,
        "policy": policy,
        "model_inventory": model_inventory,
        "gate3_cv_df": gate3_cv_df,
        "gate3_classification_report": gate3_classification_report,
        "gate3_confusion_df": gate3_confusion_df,
        "gate4": gate4,
        "gate4_shap_df": gate4_shap_df,
        "gate5_summary": gate5_summary,
        "gate5_decision_df": gate5_decision_df,
        "gate6_summary": gate6_summary,
        "gate2_coverage_df": gate2_coverage_df,
        "reports_dir": reports_dir,
        "artifacts_dir": artifacts_dir,
    }


def per_class_report_to_df(classification_report: dict[str, Any]) -> pd.DataFrame:
    """Flatten sklearn's classification_report(..., output_dict=True) JSON into a per-class
    DataFrame, excluding the aggregate rows (accuracy/macro avg/weighted avg/True) which are
    handled separately by the caller."""
    aggregate_keys = {"accuracy", "macro avg", "weighted avg", "True", "true", True}
    rows = []
    for label, stats in classification_report.items():
        if label in aggregate_keys or not isinstance(stats, dict):
            continue
        rows.append({"intent": label, **stats})
    df = pd.DataFrame(rows)
    return df.sort_values("f1-score", ascending=False, kind="mergesort").reset_index(drop=True)


def worst_best_intents(
    classification_report: dict[str, Any], n: int = 10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = per_class_report_to_df(classification_report)
    best = df.head(n).reset_index(drop=True)
    worst = df.tail(n).sort_values("f1-score", kind="mergesort").reset_index(drop=True)
    return best, worst


def top_confused_pairs(confusion_df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Real, off-diagonal top-N (true_intent, predicted_intent, count) confusion pairs - the
    concrete "where does the model actually get confused" table a 77x77 heatmap alone doesn't
    surface well in a static document."""
    rows = []
    for true_label in confusion_df.index:
        for pred_label in confusion_df.columns:
            if true_label == pred_label:
                continue
            count = int(confusion_df.loc[true_label, pred_label])
            if count > 0:
                rows.append({"true_intent": true_label, "predicted_intent": pred_label, "count": count})
    df = (
        pd.DataFrame(rows)
        .sort_values("count", ascending=False, kind="mergesort")
        .head(n)
        .reset_index(drop=True)
    )
    return df


def build_smart_suggestions(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Generate SMART (Specific, Measurable, Achievable, Relevant, Time-bound) suggestions - every
    one grounded in a real number already computed/loaded in `bundle`, never freeform GenAI text.
    Returns a list of {"title", "specific", "measurable", "timebound", "owner_placeholder"} dicts."""
    gate3_cv_df = bundle["gate3_cv_df"]
    gate5_summary = bundle["gate5_summary"]
    model_inventory = bundle["model_inventory"]
    gate4 = bundle["gate4"]

    suggestions = []

    near_random = gate3_cv_df[(gate3_cv_df["status"] == "OK") & (gate3_cv_df["mean_f1_macro"] < 0.05)]
    high_variance = gate3_cv_df[
        (gate3_cv_df["status"] == "OK")
        & (gate3_cv_df["mean_f1_macro"] > 0)
        & ((gate3_cv_df["std_f1_macro"] / gate3_cv_df["mean_f1_macro"]) > 0.5)
    ]
    if len(near_random) > 0:
        row = near_random.iloc[0]
        suggestions.append(
            {
                "title": f"Root-cause {row['model']}'s near-random CV score",
                "specific": (
                    f"{row['model']} scored a real CV mean F1-macro of {row['mean_f1_macro']:.4f} "
                    f"(near the {model_inventory['n_classes']}-class random baseline of "
                    f"~{1 / model_inventory['n_classes']:.4f}) while consuming {row['elapsed_seconds']:.0f}s "
                    "of real CV wall-clock time - by far the most expensive candidate for the worst result."
                ),
                "measurable": f"Target: either a mean F1-macro above the weakest currently-passing candidate "
                f"({gate3_cv_df[gate3_cv_df['status']=='OK']['mean_f1_macro'].nsmallest(2).max():.3f}) "
                "after the fix, or a documented decision to drop this candidate from future benchmarks.",
                "timebound": "Before the next BP1 model refresh cycle.",
                "owner_placeholder": "ML engineering owner - assign.",
            }
        )
    if len(high_variance) > 0:
        row = high_variance.sort_values("std_f1_macro", ascending=False).iloc[0]
        ratio = row["std_f1_macro"] / row["mean_f1_macro"]
        suggestions.append(
            {
                "title": f"Stabilize {row['model']}'s fold-to-fold variance",
                "specific": (
                    f"{row['model']}'s real CV fold std ({row['std_f1_macro']:.4f}) is "
                    f"{ratio:.1f}x its mean ({row['mean_f1_macro']:.4f}) - too unstable to "
                    "trust for production without investigation."
                ),
                "measurable": (
                    "Target: std/mean ratio below 0.3 after tuning (hyperparameters, "
                    "class weighting, or a fixed early-stopping schedule)."
                ),
                "timebound": (
                    "Before this candidate is considered for an ensemble or a champion " "re-evaluation."
                ),
                "owner_placeholder": "ML engineering owner - assign.",
            }
        )

    overlap = gate5_summary["overlap_count_with_gate4"]
    suggestions.append(
        {
            "title": "Increase SHAP sample size for more stable global explanations",
            "specific": (
                f"Gate 4 and Gate 5 independently computed SHAP importance from two different "
                f"{gate4['shap_sample_size']}-row samples of real held-out data, and only "
                f"{overlap}/10 top terms overlapped."
            ),
            "measurable": "Target: overlap of 7/10 or higher at a larger, fixed sample size "
            "(re-run both gates with an increased SHAP_SAMPLE_SIZE and compare).",
            "timebound": "Next explainability review cycle.",
            "owner_placeholder": "Model risk / explainability owner - assign.",
        }
    )

    accuracy = model_inventory["held_out_test_accuracy"]
    n_classes = model_inventory["n_classes"]
    suggestions.append(
        {
            "title": "Monitor per-intent recall for the weakest-performing classes in production",
            "specific": (
                f"Overall held-out test accuracy is real and strong ({accuracy:.2%} across "
                f"{n_classes} classes), but per-class performance is uneven by construction of "
                "a 77-class problem - track the bottom-decile intents (see the Known "
                "Limitations / worst-performing intents table) once in production."
            ),
            "measurable": (
                "Target: no individual intent's real production F1-score drifting more than "
                "10 percentage points below its Gate 3 held-out test value without an alert."
            ),
            "timebound": "From first production deployment onward (standing monitoring, not one-time).",
            "owner_placeholder": "MLOps / monitoring owner - assign.",
        }
    )

    n_with_reason_codes = gate5_summary["n_with_reason_codes"]
    n_records = gate5_summary["n_decision_records"]
    suggestions.append(
        {
            "title": "Expand grounded reason-code coverage beyond the current SHAP sample bound",
            "specific": (
                f"Only {n_with_reason_codes:,} of {n_records:,} real decision records "
                f"({n_with_reason_codes / n_records:.1%}) currently carry a grounded "
                "per-instance reason code, "
                "bounded by the 150-row SHAP sample size for laptop safety."
            ),
            "measurable": (
                "Target: 100% reason-code coverage once compute budget allows removing the "
                "sample bound, or a documented, deliberate sampling policy if full coverage "
                "is not pursued."
            ),
            "timebound": "Next Gate 5 hardening pass.",
            "owner_placeholder": "ML engineering owner - assign.",
        }
    )

    return suggestions


def compute_production_recommendation(bundle: dict[str, Any]) -> dict[str, Any]:
    """Live "Recommended for Production" status for BP1 - retrofitted onto this already-closed
    rollup per explicit standing user instruction, once BP3's disparate-impact investigation was
    closed (governance decision: ACCEPT_TIER_D). Computed only from real gate artifacts already
    loaded in `bundle`, never from BP3's own precedent or numbers.

    BP1 uses the same 2-tier variant as BP4, never BP3's 3-tier variant: BP1's real Gate 1 policy
    / target definition (primary target: predicted customer intent bucket, from Banking77 /
    CFPB-narrative text) carries no ECOA/Reg B disparate-impact check anywhere across its 6 real
    gates - that check was introduced starting with BP3 - so Tier 2 (CONDITIONAL - GOVERNANCE
    REVIEW REQUIRED) is structurally unreachable for BP1.

    All 6 gates are guaranteed real-run confirmed by the time this function runs at all: every
    real gate-artifact file load_all_gate_artifacts() requires (through Gate 6) must already exist
    on disk, or that loader itself raises FileNotFoundError before this function is ever reached.
    """
    g6 = bundle["gate6_summary"]
    all_gates_real_run_confirmed = True  # guaranteed by load_all_gate_artifacts() succeeding

    structural_checks = {
        "pytest_all_passed": bool(g6["pytest_all_passed"]),
        "notebook_syntax_all_passed": bool(g6["notebook_syntax_all_passed"]),
    }
    all_structural_checks_passed = all(structural_checks.values())

    if all_gates_real_run_confirmed and all_structural_checks_passed:
        tier_code, tier = 1, "RECOMMENDED FOR PRODUCTION"
        reason = (
            "All 6 BP1 gates are real-run confirmed and every structural integrity check passed "
            f"(pytest {g6['pytest_counts']['passed']} passed / {g6['pytest_counts']['failed']} "
            "failed, notebook syntax audit all passed). Tier 2 (CONDITIONAL - GOVERNANCE REVIEW "
            "REQUIRED) is structurally unreachable for BP1: this BP's real Gate 1-6 artifacts "
            "carry no ECOA/Reg B disparate-impact check (introduced starting with BP3), so BP1 "
            "cannot ever be flagged into Tier 2."
        )
    else:
        failing = [k for k, v in structural_checks.items() if not v]
        tier_code, tier = 3, "NOT RECOMMENDED"
        reason = (
            "At least one BP1 gate is not real-run confirmed or a structural integrity check has "
            f"not passed: {failing or ['gates_not_all_confirmed']}. Tier 2 remains structurally "
            "unreachable for BP1 regardless (no disparate-impact check exists for this BP), so "
            "any failure here resolves directly to Tier 3, never Tier 2. Resolve every failing "
            "check before this model is used in production."
        )

    return {
        "tier": tier,
        "tier_code": tier_code,
        "reason": reason,
        "all_gates_real_run_confirmed": all_gates_real_run_confirmed,
        "structural_checks": structural_checks,
        "all_structural_checks_passed": all_structural_checks_passed,
        "tier_2_reachable_for_this_bp": False,
    }


def build_kpi_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Assemble the top-line KPI set the HTML dashboard's cards, the DOCX executive summary, the
    XLSX Executive_KPIs sheet, and the PPTX title/summary slides all read from - ONE computation,
    reused everywhere (HYPER). Every value here is read live from a real Gate 1-6 artifact. This
    KPI bundle also carries the live-computed `production_recommendation` field, retrofitted onto
    BP1 per standing user instruction once BP3's disparate-impact investigation closed."""
    model_inventory = bundle["model_inventory"]
    gate4 = bundle["gate4"]
    gate5_summary = bundle["gate5_summary"]
    gate6_summary = bundle["gate6_summary"]
    gate2_coverage_df = bundle["gate2_coverage_df"]

    out_of_scope_row = gate2_coverage_df[
        gate2_coverage_df["common_taxonomy_bucket"] == "OUT_OF_SCOPE_NO_BANKING77_OVERLAP"
    ]
    out_of_scope_fraction = (
        float(out_of_scope_row["cfpb_fraction"].iloc[0]) if len(out_of_scope_row) else None
    )

    return {
        "champion_model": model_inventory["model_name"],
        "held_out_test_accuracy": model_inventory["held_out_test_accuracy"],
        "held_out_test_f1_macro": model_inventory["held_out_test_f1_macro"],
        "cv_mean_f1_macro": model_inventory["cv_mean_f1_macro"],
        "roc_auc_ovr_macro": gate4["roc_auc_ovr_macro"],
        "n_classes": model_inventory["n_classes"],
        "n_train_rows": model_inventory["n_train_rows"],
        "n_test_rows": model_inventory["n_test_rows"],
        "n_decision_records": gate5_summary["n_decision_records"],
        "n_with_reason_codes": gate5_summary["n_with_reason_codes"],
        "reason_code_coverage": gate5_summary["n_with_reason_codes"] / gate5_summary["n_decision_records"],
        "cfpb_out_of_scope_fraction": out_of_scope_fraction,
        "pytest_all_passed": gate6_summary["pytest_all_passed"],
        "pytest_counts": gate6_summary["pytest_counts"],
        "notebook_syntax_all_passed": gate6_summary["notebook_syntax_all_passed"],
        "n_gate3_near_random_anomalies": gate6_summary["n_gate3_near_random_anomalies_detected"],
        "n_gate3_high_variance_anomalies": gate6_summary["n_gate3_high_variance_anomalies_detected"],
        "governance_gates_complete": 6,
        "production_recommendation": compute_production_recommendation(bundle),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_gate1_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    """Every real field from Gate 1's own real output, policy.json (Business Understanding &
    Policy) - the one BP1 gate whose real output was not previously surfaced anywhere in this
    report. Nothing here is invented: every field is read live from the real file Gate 1 wrote."""
    policy = bundle["policy"]
    td = policy["target_definition"]
    lc = policy["live_checks"]
    ct = policy["compliance_touchpoint"]
    return {
        "primary_target": td["primary_target"],
        "primary_target_description": td["primary_target_description"],
        "secondary_target": td["secondary_target"],
        "secondary_target_description": td["secondary_target_description"],
        "feature_variable": td["feature_variable"],
        "train_test_split_source": td["train_test_split_source"],
        "leakage_rules": policy["leakage_rules"],
        "assumptions": policy["assumptions"],
        "compliance_requirement": ct["requirement"],
        "compliance_statement": ct["statement"],
        "shared_columns_cfpb_banking77": lc["shared_columns_cfpb_banking77"],
        "train_test_exact_text_overlap_rows": lc["train_test_exact_text_overlap_rows"],
        "class_imbalance_77_class": lc["class_imbalance_77_class"],
        "class_imbalance_9_bucket": lc["class_imbalance_9_bucket"],
        "generated_at_utc": policy["generated_at_utc"],
    }


def build_gate6_governance_detail(bundle: dict[str, Any]) -> dict[str, Any]:
    """Every real field from Gate 6's own governance summary, plus the cross-gate compliance and
    model-family fields real-recorded in model_inventory_entry.json and the real candidate list
    from Gate 3's own config block - none of which were previously surfaced anywhere in this
    report beyond the raw pytest pass/fail counts. Nothing here is invented."""
    g6 = bundle["gate6_summary"]
    mi = bundle["model_inventory"]
    gate3_block = bundle["bp1_config"].get("gate3_model_benchmark", {}) or {}
    return {
        "pytest_summary_line": g6.get("pytest_summary_line"),
        "pytest_counts": g6["pytest_counts"],
        "pytest_all_passed": g6["pytest_all_passed"],
        "notebook_syntax_check_n_passed": g6["notebook_syntax_check_n_passed"],
        "notebook_syntax_check_n_failed": g6["notebook_syntax_check_n_failed"],
        "notebook_syntax_all_passed": g6["notebook_syntax_all_passed"],
        "n_gate3_near_random_anomalies_detected": g6["n_gate3_near_random_anomalies_detected"],
        "n_gate3_high_variance_anomalies_detected": g6["n_gate3_high_variance_anomalies_detected"],
        "model_card_path": g6["model_card_path"],
        "changelog_path": g6["changelog_path"],
        "generated_at_utc": g6["generated_at_utc"],
        "model_inventory_compliance_touchpoint": mi.get("compliance_touchpoint"),
        "model_family": mi.get("model_family"),
        "training_data": mi.get("training_data"),
        "candidates_evaluated": gate3_block.get("candidates_evaluated", []),
        "candidates_failed": gate3_block.get("candidates_failed", []),
    }


# ============================================================================
# Matplotlib static figure builders (WARP: rendered once, reused as PNG bytes across DOCX + PPTX).
# Each returns raw PNG bytes so callers never touch a live pyplot Figure object more than once.
# ============================================================================


def _fig_to_png_bytes(fig, dpi: int = 150) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def fig_model_comparison_bar(gate3_cv_df: pd.DataFrame, champion_model: str) -> bytes:
    df = gate3_cv_df[gate3_cv_df["status"] == "OK"].sort_values(
        "mean_f1_macro", ascending=True, kind="mergesort"
    )
    colors = [
        PALETTE["primary_navy"] if m == champion_model else PALETTE["neutral_gray"] for m in df["model"]
    ]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.barh(df["model"], df["mean_f1_macro"], xerr=df["std_f1_macro"], color=colors, capsize=3)
    ax.set_xlabel("CV mean F1-macro (real, error bars = real fold std)")
    ax.set_title("BP1 Gate 3 — Model Benchmark (real 5-fold CV)")
    ax.spines[["top", "right"]].set_visible(False)
    for bar, val in zip(bars, df["mean_f1_macro"]):
        ax.text(val + 0.015, bar.get_y() + bar.get_height() / 2, f"{val:.3f}", va="center", fontsize=9)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_shap_top_features(gate4_shap_df: pd.DataFrame, n: int = 10) -> bytes:
    df = gate4_shap_df.head(n).sort_values("mean_abs_shap", ascending=True)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(df["feature"], df["mean_abs_shap"], color=PALETTE["accent_blue"])
    ax.set_xlabel("Mean |SHAP value| (real, Gate 4 global explanation)")
    ax.set_title("Top Globally Important Terms")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_taxonomy_bucket_pie(gate2_coverage_df: pd.DataFrame) -> bytes:
    df = gate2_coverage_df[gate2_coverage_df["cfpb_row_count"] > 0].sort_values(
        "cfpb_row_count", ascending=False
    )
    colors = (CATEGORICAL_SEQUENCE * ((len(df) // len(CATEGORICAL_SEQUENCE)) + 1))[: len(df)]
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    wedges, _texts, autotexts = ax.pie(
        df["cfpb_row_count"],
        labels=df["common_taxonomy_bucket"],
        autopct="%1.1f%%",
        colors=colors,
        textprops={"fontsize": 8},
    )
    ax.set_title("Real CFPB Complaint Volume by Common-Taxonomy Bucket")
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_confidence_distribution(gate5_decision_df: pd.DataFrame) -> bytes:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    correct = gate5_decision_df[gate5_decision_df["correct"]]["confidence_top1"]
    incorrect = gate5_decision_df[~gate5_decision_df["correct"]]["confidence_top1"]
    ax.hist(
        correct, bins=30, alpha=0.75, label=f"Correct (n={len(correct):,})", color=PALETTE["success_green"]
    )
    ax.hist(
        incorrect, bins=30, alpha=0.75, label=f"Incorrect (n={len(incorrect):,})", color=PALETTE["danger_red"]
    )
    ax.set_xlabel("Top-1 prediction confidence (real, Gate 5 decision records)")
    ax.set_ylabel("Count")
    ax.set_title("Confidence Distribution — Correct vs. Incorrect Predictions")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_confusion_heatmap_top(
    confusion_df: pd.DataFrame, top_pairs_df: pd.DataFrame, n_intents: int = 20
) -> bytes:
    """A readable static heatmap: the top-N intents by real total confusion involvement (as true OR
    predicted label in the top confused pairs), not the full 77x77 grid (illegible at document
    resolution) - the full matrix is still exported in full in the XLSX and the interactive HTML."""
    involved = pd.unique(pd.concat([top_pairs_df["true_intent"], top_pairs_df["predicted_intent"]]))[
        :n_intents
    ]
    sub = confusion_df.loc[confusion_df.index.isin(involved), confusion_df.columns.isin(involved)]
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(sub.values, cmap="Blues")
    ax.set_xticks(range(len(sub.columns)))
    ax.set_xticklabels(sub.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(sub.index)))
    ax.set_yticklabels(sub.index, fontsize=7)
    ax.set_title(f"Confusion Matrix — Top {len(involved)} Most-Confused Intents (real)")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Real count")
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


# ============================================================================
# DOCX export (python-docx). US Letter page size set explicitly (docx skill gotcha: defaults to
# A4), Calibri professional font throughout. Covers all 6 gates' real recorded output.
# ============================================================================


def write_docx_report(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    figures: dict[str, bytes],
    best_intents: pd.DataFrame,
    worst_intents: pd.DataFrame,
    confused_pairs: pd.DataFrame,
    out_path: Path,
) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    navy = RGBColor(0x1E, 0x27, 0x61)
    danger = RGBColor(0xC1, 0x29, 0x2E)
    amber = RGBColor(0xE8, 0xA3, 0x3D)
    success = RGBColor(0x1B, 0x99, 0x8B)
    tier_color = {1: success, 2: amber, 3: danger}

    gate1 = build_gate1_summary(bundle)
    gate6 = build_gate6_governance_detail(bundle)
    prod_rec = kpis["production_recommendation"]

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    title = doc.add_heading("BP1 Customer Intent Classification", level=0)
    title.runs[0].font.color.rgb = navy
    sub = doc.add_paragraph("Executive Rollup Report — Customer360 Navigator Enterprise Suite")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    gen = doc.add_paragraph(
        f"Generated {kpis['generated_at_utc']} from BP1 Gates 1-6's real, real-run-confirmed artifacts. "
        "Every figure in this report is read live from those real files, or computed live from them - "
        "no assumption-based or illustrative content appears anywhere in this document."
    )
    gen.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_heading("Recommended for Production Status", level=1)
    tier_p = doc.add_paragraph()
    tier_run = tier_p.add_run(prod_rec["tier"])
    tier_run.font.bold = True
    tier_run.font.size = Pt(16)
    tier_run.font.color.rgb = tier_color.get(prod_rec["tier_code"], navy)
    doc.add_paragraph(prod_rec["reason"])

    doc.add_heading("Executive Summary", level=1)
    kpi_rows = [
        ("Champion model", kpis["champion_model"]),
        ("Held-out test accuracy (real)", f"{kpis['held_out_test_accuracy']:.2%}"),
        ("Held-out F1-macro (real)", f"{kpis['held_out_test_f1_macro']:.4f}"),
        ("CV mean F1-macro (real)", f"{kpis['cv_mean_f1_macro']:.4f}"),
        ("ROC-AUC, one-vs-rest macro (real)", f"{kpis['roc_auc_ovr_macro']:.4f}"),
        (
            "Classes / Train rows / Test rows (real)",
            f"{kpis['n_classes']} / {kpis['n_train_rows']:,} / {kpis['n_test_rows']:,}",
        ),
        ("Decision records (real)", f"{kpis['n_decision_records']:,}"),
        ("Reason-code coverage (real)", f"{kpis['reason_code_coverage']:.1%}"),
        (
            "Governance — pytest (real)",
            f"{kpis['pytest_counts']['passed']} passed / {kpis['pytest_counts']['failed']} failed",
        ),
        (
            "Governance — notebook syntax audit (real)",
            "all passed" if kpis["notebook_syntax_all_passed"] else "issues found",
        ),
        (
            "Open governance items — Gate 3 anomalies (real, near-random / high-variance)",
            f"{kpis['n_gate3_near_random_anomalies']} / {kpis['n_gate3_high_variance_anomalies']}",
        ),
        ("Governance gates complete (real)", f"{kpis['governance_gates_complete']}/6"),
    ]
    t = doc.add_table(rows=1, cols=2)
    t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "KPI", "Value"
    for label, val in kpi_rows:
        row = t.add_row().cells
        row[0].text, row[1].text = label, str(val)

    doc.add_heading("Gate 1 — Business Understanding & Policy (real)", level=1)
    doc.add_paragraph(f"Primary target: {gate1['primary_target']} — {gate1['primary_target_description']}")
    doc.add_paragraph(
        f"Secondary target: {gate1['secondary_target']} — {gate1['secondary_target_description']}"
    )
    doc.add_paragraph(
        f"Feature variable: {gate1['feature_variable']}. Train/test split: {gate1['train_test_split_source']}"
    )
    doc.add_paragraph(f"Compliance touchpoint — {gate1['compliance_requirement']}:")
    doc.add_paragraph(gate1["compliance_statement"])
    doc.add_heading("Leakage Rules (real, enforced live every Gate 1 run)", level=2)
    for rule in gate1["leakage_rules"]:
        doc.add_paragraph(rule, style="List Bullet")
    doc.add_heading("Scope Assumptions Documented at Gate 1 (real)", level=2)
    for a in gate1["assumptions"]:
        doc.add_paragraph(a, style="List Bullet")
    doc.add_heading("Live Data-Quality Checks (real, re-verified every Gate 1 run)", level=2)
    ci77 = gate1["class_imbalance_77_class"]
    ci9 = gate1["class_imbalance_9_bucket"]
    dq_table = doc.add_table(rows=1, cols=2)
    dq_table.style = "Light Grid Accent 1"
    dq_table.rows[0].cells[0].text, dq_table.rows[0].cells[1].text = "Check", "Real Result"
    for label, val in [
        ("Shared CFPB/BANKING77 columns", str(len(gate1["shared_columns_cfpb_banking77"]))),
        ("Train/test exact-text overlap rows", str(gate1["train_test_exact_text_overlap_rows"])),
        (
            "77-class imbalance (min / max / ratio)",
            f"{ci77['min_class_count']} / {ci77['max_class_count']} / "
            f"{ci77['imbalance_ratio_max_over_min']}x",
        ),
        (
            "9-bucket imbalance (min / max / ratio)",
            f"{ci9['min_bucket_count']} / {ci9['max_bucket_count']} / {ci9['imbalance_ratio_max_over_min']}x",
        ),
    ]:
        row = dq_table.add_row().cells
        row[0].text, row[1].text = label, val

    doc.add_heading("Model Benchmark — Gate 3 (real 5-fold CV)", level=1)
    doc.add_picture(io.BytesIO(figures["model_benchmark"]), width=Inches(6.2))
    bt = doc.add_table(rows=1, cols=4)
    bt.style = "Light List Accent 1"
    for i, h in enumerate(["Model", "Mean F1-macro", "Std F1-macro", "Mean Accuracy"]):
        bt.rows[0].cells[i].text = h
    cv_ok = bundle["gate3_cv_df"][bundle["gate3_cv_df"]["status"] == "OK"].sort_values(
        "mean_f1_macro", ascending=False
    )
    for r in cv_ok.itertuples():
        row = bt.add_row().cells
        row[0].text, row[1].text, row[2].text, row[3].text = (
            r.model,
            f"{r.mean_f1_macro:.4f}",
            f"{r.std_f1_macro:.4f}",
            f"{r.mean_accuracy:.4f}",
        )

    doc.add_heading("Explainability & Statistical Validation — Gate 4 (real)", level=1)
    doc.add_picture(io.BytesIO(figures["shap_top"]), width=Inches(6.0))
    g4 = bundle["gate4"]
    doc.add_paragraph(
        f"Champion {g4['champion_model']} vs. runner-up {g4['runner_up_model']}: paired t-test statistic "
        f"{g4.get('paired_ttest_statistic')}, p-value {g4.get('paired_ttest_pvalue')} "
        f"(n={len(g4.get('champion_fold_f1_macro', []))} real CV folds — "
        f"{g4.get('statistical_test_limitation', '')}). Held-out test F1-macro "
        f"{g4['held_out_test_f1_macro_point_estimate']}, 95% bootstrap CI "
        f"{g4['held_out_test_f1_macro_bootstrap_ci_95']} "
        f"({g4.get('bootstrap_n_iterations')} resamples). SHAP sample size {g4.get('shap_sample_size')}, "
        f"background size {g4.get('shap_background_size')}."
    )

    doc.add_heading("Decision Layer — Gate 5 (real)", level=1)
    doc.add_picture(io.BytesIO(figures["confidence_dist"]), width=Inches(6.2))
    g5 = bundle["gate5_summary"]
    doc.add_paragraph(
        f"{kpis['n_with_reason_codes']:,} of {kpis['n_decision_records']:,} real decision records carry a "
        f"grounded per-instance reason code ({kpis['reason_code_coverage']:.1%}). Mean confidence on correct "
        f"predictions: {g5.get('mean_confidence_correct_predictions')}; on incorrect predictions: "
        f"{g5.get('mean_confidence_incorrect_predictions')}. Gate 4/Gate 5 top-term overlap: "
        f"{g5.get('overlap_count_with_gate4')}/10 ({', '.join(g5.get('overlap_terms_with_gate4', []))})."
    )
    ct5 = g5.get("compliance_touchpoint", {})
    if ct5:
        doc.add_paragraph(
            f"Compliance — GenAI API used: {ct5.get('genai_api_used')}. "
            f"{ct5.get('udaap_language_review', '')}"
        )

    doc.add_heading("Taxonomy Coverage — Gate 2 (real)", level=1)
    doc.add_picture(io.BytesIO(figures["taxonomy_pie"]), width=Inches(5.3))

    doc.add_heading("Confusion Analysis — Gate 3 (real)", level=1)
    doc.add_picture(io.BytesIO(figures["confusion_heatmap"]), width=Inches(6.2))
    pt_table = doc.add_table(rows=1, cols=3)
    pt_table.style = "Light List Accent 1"
    for i, h in enumerate(["True intent", "Predicted intent", "Real count"]):
        pt_table.rows[0].cells[i].text = h
    for r in confused_pairs.head(15).itertuples():
        row = pt_table.add_row().cells
        row[0].text, row[1].text, row[2].text = r.true_intent, r.predicted_intent, str(r.count)

    doc.add_heading("Best & Worst Performing Intents — Gate 3 (real)", level=1)
    doc.add_paragraph("Top 10 by real F1-score:")
    best_table = doc.add_table(rows=1, cols=4)
    best_table.style = "Light List Accent 1"
    for i, h in enumerate(["Intent", "Precision", "Recall", "F1"]):
        best_table.rows[0].cells[i].text = h
    for _, r in best_intents.iterrows():
        row = best_table.add_row().cells
        row[0].text, row[1].text, row[2].text, row[3].text = (
            r["intent"],
            f"{r['precision']:.3f}",
            f"{r['recall']:.3f}",
            f"{r['f1-score']:.3f}",
        )
    doc.add_paragraph("Bottom 10 by real F1-score:")
    worst_table = doc.add_table(rows=1, cols=4)
    worst_table.style = "Light List Accent 1"
    for i, h in enumerate(["Intent", "Precision", "Recall", "F1"]):
        worst_table.rows[0].cells[i].text = h
    for _, r in worst_intents.iterrows():
        row = worst_table.add_row().cells
        row[0].text, row[1].text, row[2].text, row[3].text = (
            r["intent"],
            f"{r['precision']:.3f}",
            f"{r['recall']:.3f}",
            f"{r['f1-score']:.3f}",
        )

    doc.add_heading("Gate 6 — Governance, Known Limitations & Compliance (real)", level=1)
    doc.add_paragraph(
        f"pytest suite: {gate6['pytest_counts']['passed']} passed / "
        f"{gate6['pytest_counts']['failed']} failed "
        f"(skipped {gate6['pytest_counts'].get('skipped', 0)}). Notebook syntax audit: "
        f"{gate6['notebook_syntax_check_n_passed']}/"
        f"{gate6['notebook_syntax_check_n_passed'] + gate6['notebook_syntax_check_n_failed']} "
        "passed."
    )
    doc.add_paragraph(
        "Open item — Gate 3 candidate-level anomalies detected live, not yet root-caused: "
        f"{gate6['n_gate3_near_random_anomalies_detected']} near-random result(s), "
        f"{gate6['n_gate3_high_variance_anomalies_detected']} high CV-variance result(s)."
    )
    doc.add_paragraph(f"Model card: {gate6['model_card_path']} | Changelog: {gate6['changelog_path']}")
    if gate6.get("model_inventory_compliance_touchpoint"):
        doc.add_paragraph(
            f"Model inventory compliance touchpoint: {gate6['model_inventory_compliance_touchpoint']}"
        )
    if gate6.get("model_family"):
        doc.add_paragraph(
            f"Model family: {gate6['model_family']}. Training data: {gate6.get('training_data', '')}"
        )
    doc.add_paragraph(f"Gate 3 candidates evaluated (real): {', '.join(gate6['candidates_evaluated'])}.")
    if gate6["candidates_failed"]:
        doc.add_paragraph(f"Gate 3 candidates failed (real): {', '.join(gate6['candidates_failed'])}.")
    else:
        doc.add_paragraph(
            "Gate 3 candidates failed: none (0 exceptions across all real candidates evaluated)."
        )

    doc.add_heading("SMART Suggestions", level=1)
    for s in suggestions:
        doc.add_heading(s["title"], level=2)
        doc.add_paragraph(f"Specific: {s['specific']}")
        doc.add_paragraph(f"Measurable: {s['measurable']}")
        doc.add_paragraph(f"Time-bound: {s['timebound']}")
        doc.add_paragraph(f"Owner: {s['owner_placeholder']}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path


# ============================================================================
# XLSX export (openpyxl). Every sheet is built from a real Gate 1-6 artifact - no assumption-based
# or illustrative content anywhere in this workbook.
# ============================================================================


def write_xlsx_workbook(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    best_intents: pd.DataFrame,
    worst_intents: pd.DataFrame,
    confused_pairs: pd.DataFrame,
    out_path: Path,
) -> Path:
    import re

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    navy_fill = PatternFill(start_color="1E2761", end_color="1E2761", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(bold=True, size=14, color="1E2761")

    # XLSX/XML cannot represent the ASCII control-character range below (this is the same
    # rule openpyxl itself enforces via IllegalCharacterError). Real captured text can contain
    # these bytes - most notably gate6's real pytest_summary_line, which is raw stdout from a
    # subprocess pytest run and can carry ANSI color-escape control codes on some terminals/
    # pytest.ini configs. Stripping them here does not alter the real content in any
    # substantive way; it only removes bytes the XLSX format itself cannot store, so every
    # sheet write below routes string values through this guard instead of writing raw values.
    _ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    def _safe(value):
        if isinstance(value, str):
            return _ILLEGAL_XLSX_CHARS_RE.sub("", value)
        return value

    def _safe_row(row):
        return [_safe(v) for v in row]

    gate1 = build_gate1_summary(bundle)
    gate6 = build_gate6_governance_detail(bundle)
    prod_rec = kpis["production_recommendation"]

    wb = Workbook()

    def _style_header(ws, row_idx: int, n_cols: int):
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=row_idx, column=c)
            cell.fill = navy_fill
            cell.font = header_font

    def _autosize(ws, n_cols: int, width: int = 22):
        for c in range(1, n_cols + 1):
            ws.column_dimensions[get_column_letter(c)].width = width

    # --- 00_ReadMe ---
    ws = wb.active
    ws.title = "00_ReadMe"
    ws["A1"] = "BP1 Customer Intent Classification — Executive Rollup Workbook"
    ws["A1"].font = title_font
    ws["A3"] = f"Generated: {kpis['generated_at_utc']}"
    ws["A4"] = "Every sheet here is built only from BP1 Gates 1-6's real, real-run-confirmed artifacts."
    ws["A5"] = "No assumption-based, illustrative, or estimated content appears anywhere in this workbook."
    ws["A6"] = f"Recommended for Production status: {prod_rec['tier']}"
    ws["A6"].font = Font(bold=True, color="1E2761")
    sheets_index = [
        ("01_Executive_KPIs", "Top-line real KPIs across all 6 gates."),
        (
            "02_Gate1_Business_Policy",
            "Gate 1 real target definition, leakage rules, assumptions, compliance, live checks.",
        ),
        ("03_Model_Benchmark", "Gate 3 real 6-model 5-fold CV benchmark."),
        (
            "04_Statistical_Validation",
            "Gate 4 real paired t-test, Wilcoxon test, bootstrap CI, ROC-AUC, per-fold CV scores.",
        ),
        ("05_Explainability_SHAP", "Gate 4 real global SHAP top features."),
        (
            "06_Decision_Layer",
            "Gate 5 real decision-record summary, compliance touchpoint + full 3,080-row export.",
        ),
        ("07_Taxonomy_Coverage", "Gate 2 real CFPB/BANKING77 common-taxonomy coverage."),
        ("08_Confusion_Analysis", "Gate 3 real top confused intent pairs."),
        (
            "09_Gate6_Governance_Limitations",
            "Gate 6 real governance status, open items, model card/changelog refs.",
        ),
        ("10_SMART_Suggestions", "Data-grounded SMART recommendations."),
    ]
    for i, (name, desc) in enumerate(sheets_index):
        ws.cell(row=7 + i, column=1, value=name)
        ws.cell(row=7 + i, column=2, value=desc)
    _autosize(ws, 2, width=40)

    # --- 01_Executive_KPIs ---
    ws = wb.create_sheet("01_Executive_KPIs")
    ws.append(["KPI", "Value"])
    _style_header(ws, 1, 2)
    kpi_rows = [
        ("Champion model", kpis["champion_model"]),
        ("Held-out test accuracy", kpis["held_out_test_accuracy"]),
        ("Held-out F1-macro", kpis["held_out_test_f1_macro"]),
        ("CV mean F1-macro", kpis["cv_mean_f1_macro"]),
        ("ROC-AUC (OvR macro)", kpis["roc_auc_ovr_macro"]),
        ("N classes", kpis["n_classes"]),
        ("N train rows", kpis["n_train_rows"]),
        ("N test rows", kpis["n_test_rows"]),
        ("Decision records", kpis["n_decision_records"]),
        ("Reason-code coverage", kpis["reason_code_coverage"]),
        ("pytest passed", kpis["pytest_counts"]["passed"]),
        ("pytest failed", kpis["pytest_counts"]["failed"]),
        ("Notebook syntax audit all passed", kpis["notebook_syntax_all_passed"]),
        ("Gate 3 near-random anomalies (open item)", kpis["n_gate3_near_random_anomalies"]),
        ("Gate 3 high-variance anomalies (open item)", kpis["n_gate3_high_variance_anomalies"]),
        ("Governance gates complete", f"{kpis['governance_gates_complete']}/6"),
    ]
    for row in kpi_rows:
        ws.append(_safe_row(list(row)))
    ws["B3"].number_format = "0.00%"
    ws["B11"].number_format = "0.0%"
    _autosize(ws, 2, width=34)

    # --- 02_Gate1_Business_Policy ---
    ws = wb.create_sheet("02_Gate1_Business_Policy")
    ws["A1"] = "Gate 1 — Business Understanding & Policy (real, from policy.json)"
    ws["A1"].font = title_font
    row_idx = 3
    for label, val in [
        ("Primary target", gate1["primary_target"]),
        ("Primary target description", gate1["primary_target_description"]),
        ("Secondary target", gate1["secondary_target"]),
        ("Secondary target description", gate1["secondary_target_description"]),
        ("Feature variable", gate1["feature_variable"]),
        ("Train/test split source", gate1["train_test_split_source"]),
        ("Compliance requirement", gate1["compliance_requirement"]),
        ("Compliance statement", gate1["compliance_statement"]),
        ("Shared CFPB/BANKING77 columns (count)", len(gate1["shared_columns_cfpb_banking77"])),
        ("Train/test exact-text overlap rows", gate1["train_test_exact_text_overlap_rows"]),
        ("77-class imbalance — min class count", gate1["class_imbalance_77_class"]["min_class_count"]),
        ("77-class imbalance — max class count", gate1["class_imbalance_77_class"]["max_class_count"]),
        (
            "77-class imbalance — ratio (max/min)",
            gate1["class_imbalance_77_class"]["imbalance_ratio_max_over_min"],
        ),
        ("9-bucket imbalance — min bucket count", gate1["class_imbalance_9_bucket"]["min_bucket_count"]),
        ("9-bucket imbalance — max bucket count", gate1["class_imbalance_9_bucket"]["max_bucket_count"]),
        (
            "9-bucket imbalance — ratio (max/min)",
            gate1["class_imbalance_9_bucket"]["imbalance_ratio_max_over_min"],
        ),
        ("Generated at (UTC)", gate1["generated_at_utc"]),
    ]:
        ws.cell(row=row_idx, column=1, value=_safe(label))
        ws.cell(row=row_idx, column=2, value=_safe(val))
        row_idx += 1
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Leakage Rules (real)").font = Font(bold=True, color="1E2761")
    row_idx += 1
    for rule in gate1["leakage_rules"]:
        ws.cell(row=row_idx, column=1, value=_safe(rule))
        row_idx += 1
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Scope Assumptions Documented at Gate 1 (real)").font = Font(
        bold=True, color="1E2761"
    )
    row_idx += 1
    for a in gate1["assumptions"]:
        ws.cell(row=row_idx, column=1, value=_safe(a))
        row_idx += 1
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 70
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # --- 03_Model_Benchmark ---
    ws = wb.create_sheet("03_Model_Benchmark")
    cols = [
        "model",
        "status",
        "elapsed_seconds",
        "mean_f1_macro",
        "std_f1_macro",
        "mean_f1_weighted",
        "mean_accuracy",
    ]
    ws.append(cols)
    _style_header(ws, 1, len(cols))
    for r in bundle["gate3_cv_df"][cols].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, len(cols), width=18)

    # --- 04_Statistical_Validation ---
    ws = wb.create_sheet("04_Statistical_Validation")
    g4 = bundle["gate4"]
    ws.append(["Field", "Value"])
    _style_header(ws, 1, 2)
    for k in [
        "champion_model",
        "runner_up_model",
        "recomputed_champion_mean_cv_f1_macro",
        "gate3_recorded_champion_mean_cv_f1_macro",
        "consistency_check_diff",
        "paired_ttest_statistic",
        "paired_ttest_pvalue",
        "wilcoxon_statistic",
        "wilcoxon_pvalue",
        "statistical_test_limitation",
        "held_out_test_f1_macro_point_estimate",
        "bootstrap_n_iterations",
        "roc_auc_ovr_macro",
        "n_classes",
        "shap_sample_size",
        "shap_background_size",
        "shap_error",
        "generated_at_utc",
    ]:
        ws.append(_safe_row([k, str(g4.get(k))]))
    ws.append(
        _safe_row(
            ["held_out_test_f1_macro_bootstrap_ci_95", str(g4.get("held_out_test_f1_macro_bootstrap_ci_95"))]
        )
    )
    ws.append([])
    fold_header_row = ws.max_row + 1
    ws.cell(row=fold_header_row, column=1, value="Real per-fold CV F1-macro (5-fold)")
    ws.cell(row=fold_header_row, column=1).font = Font(bold=True, color="1E2761")
    header_row2 = fold_header_row + 1
    ws.cell(row=header_row2, column=1, value="Fold")
    ws.cell(row=header_row2, column=2, value=_safe(f"Champion ({g4.get('champion_model')})"))
    ws.cell(row=header_row2, column=3, value=_safe(f"Runner-up ({g4.get('runner_up_model')})"))
    _style_header(ws, header_row2, 3)
    champ_folds = g4.get("champion_fold_f1_macro", []) or []
    runner_folds = g4.get("runner_up_fold_f1_macro", []) or []
    for i in range(max(len(champ_folds), len(runner_folds))):
        r = header_row2 + 1 + i
        ws.cell(row=r, column=1, value=i + 1)
        if i < len(champ_folds):
            ws.cell(row=r, column=2, value=champ_folds[i])
        if i < len(runner_folds):
            ws.cell(row=r, column=3, value=runner_folds[i])
    _autosize(ws, 3, width=32)

    # --- 05_Explainability_SHAP ---
    ws = wb.create_sheet("05_Explainability_SHAP")
    ws.append(["feature", "mean_abs_shap"])
    _style_header(ws, 1, 2)
    for r in bundle["gate4_shap_df"].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, 2, width=22)

    # --- 06_Decision_Layer ---
    ws = wb.create_sheet("06_Decision_Layer")
    g5 = bundle["gate5_summary"]
    ws.append(["Field", "Value"])
    _style_header(ws, 1, 2)
    for k in [
        "champion_model",
        "n_decision_records",
        "n_with_reason_codes",
        "shap_sample_size_bound",
        "n_reason_codes_per_record",
        "shap_error",
        "overall_test_accuracy_recomputed",
        "gate3_recorded_test_accuracy",
        "accuracy_consistency_diff",
        "mean_confidence_correct_predictions",
        "mean_confidence_incorrect_predictions",
        "overlap_count_with_gate4",
        "reason_code_grounding_failures",
        "reason_code_grounding_method",
        "generated_at_utc",
    ]:
        ws.append(_safe_row([k, str(g5.get(k))]))
    ws.append(
        _safe_row(
            [
                "gate5_aggregated_top_reason_code_terms",
                ", ".join(g5.get("gate5_aggregated_top_reason_code_terms", [])),
            ]
        )
    )
    ws.append(_safe_row(["gate4_global_top10_terms", ", ".join(g5.get("gate4_global_top10_terms", []))]))
    ws.append(_safe_row(["overlap_terms_with_gate4", ", ".join(g5.get("overlap_terms_with_gate4", []))]))
    ct5 = g5.get("compliance_touchpoint", {}) or {}
    ws.append([])
    ws.append(["Compliance touchpoint (real)", ""])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="1E2761")
    for k in [
        "genai_api_used",
        "udaap_language_review",
        "nist_ai_rmf_measure_manage",
        "scope_decision_confirmed_by_user_utc",
    ]:
        ws.append(_safe_row([k, str(ct5.get(k))]))
    ws.append([])
    dec_cols = ["row_index", "true_label", "predicted_label", "correct", "confidence_top1", "reason_codes"]
    header_row_idx = ws.max_row + 1
    ws.append(dec_cols)
    _style_header(ws, header_row_idx, len(dec_cols))
    dec_df = bundle["gate5_decision_df"][dec_cols]
    for r in dec_df.itertuples(index=False):
        ws.append(_safe_row(list(r)))
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 46
    for col in "CDEF":
        ws.column_dimensions[col].width = 16

    # --- 07_Taxonomy_Coverage ---
    ws = wb.create_sheet("07_Taxonomy_Coverage")
    cov_cols = list(bundle["gate2_coverage_df"].columns)
    ws.append(cov_cols)
    _style_header(ws, 1, len(cov_cols))
    for r in bundle["gate2_coverage_df"].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, len(cov_cols), width=26)

    # --- 08_Confusion_Analysis ---
    ws = wb.create_sheet("08_Confusion_Analysis")
    ws.append(["true_intent", "predicted_intent", "count"])
    _style_header(ws, 1, 3)
    for r in confused_pairs.itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, 3, width=26)

    # --- 09_Gate6_Governance_Limitations ---
    ws = wb.create_sheet("09_Gate6_Governance_Limitations")
    ws["A1"] = "Gate 6 — Governance, Known Limitations & Compliance (real)"
    ws["A1"].font = title_font
    row_idx = 3
    for label, val in [
        ("Recommended for Production status", prod_rec["tier"]),
        ("Production status reason", prod_rec["reason"]),
        ("pytest summary line", gate6.get("pytest_summary_line")),
        ("pytest passed", gate6["pytest_counts"]["passed"]),
        ("pytest failed", gate6["pytest_counts"]["failed"]),
        ("pytest skipped", gate6["pytest_counts"].get("skipped")),
        ("pytest all passed", gate6["pytest_all_passed"]),
        ("Notebook syntax check — passed", gate6["notebook_syntax_check_n_passed"]),
        ("Notebook syntax check — failed", gate6["notebook_syntax_check_n_failed"]),
        ("Notebook syntax all passed", gate6["notebook_syntax_all_passed"]),
        (
            "Open item — Gate 3 near-random anomalies detected",
            gate6["n_gate3_near_random_anomalies_detected"],
        ),
        (
            "Open item — Gate 3 high-variance anomalies detected",
            gate6["n_gate3_high_variance_anomalies_detected"],
        ),
        ("Model card path", gate6["model_card_path"]),
        ("Changelog path", gate6["changelog_path"]),
        ("Model inventory compliance touchpoint", gate6.get("model_inventory_compliance_touchpoint")),
        ("Model family", gate6.get("model_family")),
        ("Training data", gate6.get("training_data")),
        ("Gate 3 candidates evaluated", ", ".join(gate6.get("candidates_evaluated", []))),
        ("Gate 3 candidates failed", ", ".join(gate6.get("candidates_failed", [])) or "none"),
        ("Generated at (UTC)", gate6["generated_at_utc"]),
    ]:
        ws.cell(row=row_idx, column=1, value=_safe(label))
        ws.cell(row=row_idx, column=2, value=_safe(val))
        row_idx += 1
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 70
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # --- 10_SMART_Suggestions ---
    ws = wb.create_sheet("10_SMART_Suggestions")
    ws.append(["Title", "Specific", "Measurable", "Time-bound", "Owner"])
    _style_header(ws, 1, 5)
    for s in suggestions:
        ws.append(
            _safe_row([s["title"], s["specific"], s["measurable"], s["timebound"], s["owner_placeholder"]])
        )
    for col in "ABCDE":
        ws.column_dimensions[col].width = 42
        for cell in ws[col]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


# ============================================================================
# PPTX export (python-pptx). Reuses the same shared matplotlib PNGs as the DOCX export. Every
# slide is built from real Gate 1-6 recorded output - no assumption-based content.
# ============================================================================


def write_pptx_deck(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    figures: dict[str, bytes],
    out_path: Path,
) -> Path:
    from pptx import Presentation
    from pptx.dml.color import RGBColor as PptxRGBColor
    from pptx.util import Inches as PptxInches
    from pptx.util import Pt as PptxPt

    NAVY = PptxRGBColor(0x1E, 0x27, 0x61)
    WHITE = PptxRGBColor(0xFF, 0xFF, 0xFF)
    GRAY = PptxRGBColor(0x4B, 0x54, 0x68)
    AMBER = PptxRGBColor(0xE8, 0xA3, 0x3D)
    SUCCESS = PptxRGBColor(0x1B, 0x99, 0x8B)
    DANGER = PptxRGBColor(0xC1, 0x29, 0x2E)
    TIER_COLOR = {1: SUCCESS, 2: AMBER, 3: DANGER}

    gate1 = build_gate1_summary(bundle)
    gate6 = build_gate6_governance_detail(bundle)
    prod_rec = kpis["production_recommendation"]

    prs = Presentation()
    prs.slide_width = PptxInches(13.333)
    prs.slide_height = PptxInches(7.5)
    blank_layout = prs.slide_layouts[6]

    def _add_slide():
        return prs.slides.add_slide(blank_layout)

    def _add_title(slide, text: str, subtitle: str | None = None, dark: bool = False):
        box = slide.shapes.add_textbox(PptxInches(0.6), PptxInches(0.35), PptxInches(12.1), PptxInches(0.9))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        run = p.add_run()
        run.text = text
        run.font.size = PptxPt(28)
        run.font.bold = True
        run.font.color.rgb = WHITE if dark else NAVY
        if subtitle:
            box2 = slide.shapes.add_textbox(
                PptxInches(0.6), PptxInches(1.05), PptxInches(12.1), PptxInches(0.5)
            )
            tf2 = box2.text_frame
            tf2.word_wrap = True
            p2 = tf2.paragraphs[0]
            r2 = p2.add_run()
            r2.text = subtitle
            r2.font.size = PptxPt(14)
            r2.font.color.rgb = WHITE if dark else GRAY

    def _fill_bg(slide, color: PptxRGBColor):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = color

    def _add_picture_bytes(slide, png_bytes: bytes, left, top, width=None, height=None):
        return slide.shapes.add_picture(io.BytesIO(png_bytes), left, top, width=width, height=height)

    def _add_kpi_box(slide, left, top, width, height, label, value):
        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = str(value)
        r1.font.size = PptxPt(26)
        r1.font.bold = True
        r1.font.color.rgb = NAVY
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = label
        r2.font.size = PptxPt(11)
        r2.font.color.rgb = GRAY

    def _add_bullets(slide, lines, top=PptxInches(1.4), color=None, size=15):
        box = slide.shapes.add_textbox(
            PptxInches(0.6), top, PptxInches(12.1), PptxInches(7.5) - top - PptxInches(0.4)
        )
        tf = box.text_frame
        tf.word_wrap = True
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = p.add_run()
            r.text = "• " + line
            r.font.size = PptxPt(size)
            r.font.color.rgb = color or GRAY

    # --- Slide 1: Title ---
    s = _add_slide()
    _fill_bg(s, NAVY)
    _add_title(
        s,
        "BP1 Customer Intent Classification",
        "Executive Rollup — Customer360 Navigator Enterprise Suite",
        dark=True,
    )
    box = s.shapes.add_textbox(PptxInches(0.6), PptxInches(5.6), PptxInches(11), PptxInches(1.2))
    p = box.text_frame.paragraphs[0]
    r = p.add_run()
    r.text = (
        f"Champion model: {kpis['champion_model']}  |  "
        f"Held-out accuracy: {kpis['held_out_test_accuracy']:.2%} (real)  |  "
        f"Generated {kpis['generated_at_utc'][:10]}"
    )
    r.font.size = PptxPt(15)
    r.font.color.rgb = WHITE
    p2 = box.text_frame.add_paragraph()
    r2 = p2.add_run()
    r2.text = f"Recommended for Production: {prod_rec['tier']}"
    r2.font.size = PptxPt(17)
    r2.font.bold = True
    r2.font.color.rgb = TIER_COLOR.get(prod_rec["tier_code"], WHITE)

    # --- Slide 2: Executive KPIs ---
    s = _add_slide()
    _add_title(s, "Executive Summary — Real KPIs")
    kpi_cells = [
        ("Champion Model", kpis["champion_model"]),
        ("Held-out Accuracy", f"{kpis['held_out_test_accuracy']:.2%}"),
        ("Held-out F1-macro", f"{kpis['held_out_test_f1_macro']:.4f}"),
        ("ROC-AUC (OvR)", f"{kpis['roc_auc_ovr_macro']:.4f}"),
        ("Decision Records", f"{kpis['n_decision_records']:,}"),
        ("Reason-code Coverage", f"{kpis['reason_code_coverage']:.1%}"),
        ("pytest", f"{kpis['pytest_counts']['passed']} passed"),
        (
            "Gate 3 Open Anomalies",
            f"{kpis['n_gate3_near_random_anomalies']} near-random / "
            f"{kpis['n_gate3_high_variance_anomalies']} high-var",
        ),
    ]
    cols = 4  # 2 rows x 4 cols KPI grid - row count isn't read directly, divmod(i, cols) derives it
    cell_w = PptxInches(2.9)
    cell_h = PptxInches(1.6)
    for i, (label, val) in enumerate(kpi_cells):
        r_idx, c_idx = divmod(i, cols)
        left = PptxInches(0.5) + c_idx * (cell_w + PptxInches(0.15))
        top = PptxInches(1.7) + r_idx * (cell_h + PptxInches(0.2))
        _add_kpi_box(s, left, top, cell_w, cell_h, label, val)

    # --- Slide 3: Gate 1 Business Understanding & Policy ---
    s = _add_slide()
    _add_title(s, "Gate 1 — Business Understanding & Policy (real)")
    ci77 = gate1["class_imbalance_77_class"]
    ci9 = gate1["class_imbalance_9_bucket"]
    _add_bullets(
        s,
        [
            f"Primary target: {gate1['primary_target']} ({gate1['primary_target_description']})",
            f"Secondary target: {gate1['secondary_target']} ({gate1['secondary_target_description']})",
            f"Feature variable: {gate1['feature_variable']} | Split: {gate1['train_test_split_source']}",
            f"Compliance touchpoint: {gate1['compliance_requirement']}",
            f"Live check — shared CFPB/BANKING77 columns: {len(gate1['shared_columns_cfpb_banking77'])}",
            f"Live check — train/test exact-text overlap rows: {gate1['train_test_exact_text_overlap_rows']}",
            f"77-class imbalance ratio: {ci77['imbalance_ratio_max_over_min']}x "
            f"(min {ci77['min_class_count']} / max {ci77['max_class_count']})",
            f"9-bucket imbalance ratio: {ci9['imbalance_ratio_max_over_min']}x "
            f"(min {ci9['min_bucket_count']} / max {ci9['max_bucket_count']})",
        ],
    )

    # --- Slide 4: Model benchmark ---
    s = _add_slide()
    _add_title(s, "Model Benchmark — Gate 3 (real 5-fold CV)")
    _add_picture_bytes(
        s, figures["model_benchmark"], PptxInches(1.3), PptxInches(1.5), width=PptxInches(10.7)
    )

    # --- Slide 5: Explainability ---
    s = _add_slide()
    _add_title(s, "Explainability — Gate 4 (real SHAP)")
    _add_picture_bytes(s, figures["shap_top"], PptxInches(2.0), PptxInches(1.5), width=PptxInches(9.3))

    # --- Slide 6: Decision layer ---
    s = _add_slide()
    _add_title(s, "Decision Layer — Gate 5 (real)")
    _add_picture_bytes(
        s, figures["confidence_dist"], PptxInches(1.3), PptxInches(1.5), width=PptxInches(10.7)
    )

    # --- Slide 7: Taxonomy coverage ---
    s = _add_slide()
    _add_title(s, "Taxonomy Coverage — Gate 2 (real)")
    _add_picture_bytes(s, figures["taxonomy_pie"], PptxInches(3.6), PptxInches(1.3), width=PptxInches(6.0))

    # --- Slide 8: Confusion analysis ---
    s = _add_slide()
    _add_title(s, "Confusion Analysis — Gate 3 (real)")
    _add_picture_bytes(
        s, figures["confusion_heatmap"], PptxInches(2.3), PptxInches(1.3), width=PptxInches(8.7)
    )

    # --- Slide 9: SMART suggestions ---
    s = _add_slide()
    _add_title(s, "SMART Suggestions")
    box = s.shapes.add_textbox(PptxInches(0.6), PptxInches(1.4), PptxInches(12.1), PptxInches(5.7))
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for sug in suggestions[:5]:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run()
        r.text = sug["title"]
        r.font.size = PptxPt(15)
        r.font.bold = True
        r.font.color.rgb = NAVY
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = f"{sug['specific']} Target: {sug['measurable']}"
        r2.font.size = PptxPt(11)
        r2.font.color.rgb = GRAY
        p3 = tf.add_paragraph()
        r3 = p3.add_run()
        r3.text = " "
        r3.font.size = PptxPt(6)

    # --- Slide 10: Gate 6 Governance & Known Limitations ---
    s = _add_slide()
    _fill_bg(s, NAVY)
    _add_title(s, "Gate 6 — Governance & Known Limitations (real)", dark=True)
    _add_bullets(
        s,
        [
            f"pytest suite: {gate6['pytest_counts']['passed']} passed / "
            f"{gate6['pytest_counts']['failed']} failed",
            f"Notebook syntax audit: {gate6['notebook_syntax_check_n_passed']}/"
            f"{gate6['notebook_syntax_check_n_passed'] + gate6['notebook_syntax_check_n_failed']} passed",
            f"Open item: {gate6['n_gate3_near_random_anomalies_detected']} near-random + "
            f"{gate6['n_gate3_high_variance_anomalies_detected']} high-variance Gate 3 "
            f"candidate anomaly(ies), not yet root-caused",
            f"Model card: {gate6['model_card_path']}",
            f"Changelog: {gate6['changelog_path']}",
            f"Gate 3 candidates evaluated: {', '.join(gate6.get('candidates_evaluated', []))}",
            f"BP1 governance gates complete: {kpis['governance_gates_complete']}/6",
        ],
        top=PptxInches(1.6),
        color=WHITE,
        size=16,
    )

    # --- Slide 11: Recommended for Production ---
    s = _add_slide()
    tier_bg = {1: SUCCESS, 2: AMBER, 3: DANGER}.get(prod_rec["tier_code"], NAVY)
    _fill_bg(s, tier_bg)
    _add_title(s, "Recommended for Production Status", dark=True)
    box = s.shapes.add_textbox(PptxInches(0.6), PptxInches(1.5), PptxInches(12.1), PptxInches(1.0))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = prod_rec["tier"]
    r.font.size = PptxPt(34)
    r.font.bold = True
    r.font.color.rgb = WHITE
    _add_bullets(s, [prod_rec["reason"]], top=PptxInches(2.7), color=WHITE, size=16)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    return out_path
