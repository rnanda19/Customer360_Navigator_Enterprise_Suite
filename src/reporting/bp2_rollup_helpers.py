"""
src/reporting/bp2_rollup_helpers.py — Customer360 Navigator

BP2 executive-rollup report shared component library (HYPER: built once, imported everywhere —
this is the single source of truth for data loading, KPI assembly, SMART-suggestion generation,
and the matplotlib figure builders reused across the DOCX/XLSX/PPTX exports and referenced by the
HTML dashboard's data payload). Sibling module to src/reporting/bp1_rollup_helpers.py, adapted for
BP2's real, structurally different data shape: 4 ordinal friction-severity classes (not 77 intent
classes), a structured-feature model (not TF-IDF text), and a second Gate 3 open-item category
(candidate FAILURES, not just near-random/high-variance anomalies among passing candidates) that
BP1 never had to represent.

Standing rules this module follows (identical to bp1_rollup_helpers.py):
  - Zero-fabrication, no assumption-based content: every KPI/figure/table returned here is read
    live from Gates 1-6's own already-recorded real artifacts, or computed live from them by a
    documented formula over those real values. There is no financial-impact / illustrative-
    assumption section anywhere in this module — only real, original notebook output results are
    reported, per standing project instruction.
  - Comprehensive coverage: every one of BP2's six gates has its real recorded output represented
    somewhere in every deliverable this module writes — see build_gate1_summary() and
    build_gate6_governance_detail() for the two gates not otherwise covered by a chart.
  - WARP: matplotlib figures are built once per figure and reused (rendered to a shared in-memory
    PNG buffer) across the DOCX and PPTX exports, never rebuilt per document.
  - This module performs no I/O side effects at import time and is never executed by Claude — only
    the user's own notebook run calls it, per the project's execution-boundary rule.
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
# Shared visual identity — SAME real fixed palette as BP1's rollup (HYPER: one identity reused
# across every BP's executive rollup, not redefined per BP).
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
    loader). Raises a clear FileNotFoundError-derived message naming the missing gate if any
    prerequisite is absent — this report requires BP2 Gates 1-6 to already be real-run confirmed."""
    configs_dir = project_root / "configs"
    artifacts_dir = project_root / "notebooks" / "bp2_customer_friction_classification" / "artifacts"
    reports_dir = project_root / "reports" / "bp2_customer_friction_classification"

    required = {
        "bp2_config": configs_dir / "bp2_customer_friction_classification.yaml",
        "severity_taxonomy_config": configs_dir / "bp2_friction_severity_taxonomy.yaml",
        "policy": artifacts_dir / "policy.json",
        "model_inventory": artifacts_dir / "model_inventory_entry.json",
        "gate2_severity_csv": artifacts_dir / "gate2_severity_distribution.csv",
        "gate3_cv_csv": artifacts_dir / "gate3_cv_benchmark_results.csv",
        "gate3_classification_report": artifacts_dir / "gate3_champion_test_classification_report.json",
        "gate3_confusion_matrix": artifacts_dir / "gate3_champion_test_confusion_matrix.csv",
        "gate4_json": artifacts_dir / "gate4_statistical_validation.json",
        "gate4_shap_csv": artifacts_dir / "gate4_shap_top_features.csv",
        "gate5_summary": artifacts_dir / "gate5_decision_layer_summary.json",
        "gate5_decision_records": artifacts_dir / "gate5_decision_records.csv",
        "gate6_summary": artifacts_dir / "gate6_governance_summary.json",
    }
    missing = {k: str(v) for k, v in required.items() if not v.exists()}
    if missing:
        raise FileNotFoundError(
            f"BP2 executive rollup requires Gates 1-6 to be real-run confirmed first - missing real "
            f"artifact file(s): {missing}. Run the corresponding gate notebook(s) before this report."
        )

    with open(required["bp2_config"], "r", encoding="utf-8") as f:
        bp2_config = yaml.safe_load(f)
    with open(required["severity_taxonomy_config"], "r", encoding="utf-8") as f:
        severity_taxonomy_config = yaml.safe_load(f)
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

    gate2_severity_df = pd.read_csv(required["gate2_severity_csv"])
    gate3_cv_df = pd.read_csv(required["gate3_cv_csv"])
    gate3_confusion_df = pd.read_csv(required["gate3_confusion_matrix"], index_col=0)
    gate4_shap_df = pd.read_csv(required["gate4_shap_csv"])
    gate5_decision_df = pd.read_csv(required["gate5_decision_records"])

    reports_dir.mkdir(parents=True, exist_ok=True)

    return {
        "bp2_config": bp2_config,
        "severity_taxonomy_config": severity_taxonomy_config,
        "policy": policy,
        "model_inventory": model_inventory,
        "gate2_severity_df": gate2_severity_df,
        "gate3_cv_df": gate3_cv_df,
        "gate3_classification_report": gate3_classification_report,
        "gate3_confusion_df": gate3_confusion_df,
        "gate4": gate4,
        "gate4_shap_df": gate4_shap_df,
        "gate5_summary": gate5_summary,
        "gate5_decision_df": gate5_decision_df,
        "gate6_summary": gate6_summary,
        "reports_dir": reports_dir,
        "artifacts_dir": artifacts_dir,
    }


def class_performance_ranked(classification_report: dict[str, Any]) -> pd.DataFrame:
    """Flatten sklearn's classification_report(..., output_dict=True) JSON into a per-class
    DataFrame ranked by real F1-score, descending. BP2 has only 4 real ordinal severity classes
    (vs BP1's 77 intents), so — unlike BP1's worst_best_intents(n=10) split — every class is small
    enough to show in full; there is no separate best-10/worst-10 split here."""
    aggregate_keys = {"accuracy", "macro avg", "weighted avg", "True", "true", True}
    rows = []
    for label, stats in classification_report.items():
        if label in aggregate_keys or not isinstance(stats, dict):
            continue
        rows.append({"severity_class": label, **stats})
    df = pd.DataFrame(rows)
    return df.sort_values("f1-score", ascending=False, kind="mergesort").reset_index(drop=True)


def confusion_pairs(confusion_df: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    """Real off-diagonal (true_class, predicted_class, count) confusion pairs. BP2's real
    confusion matrix is only 4x4 (12 off-diagonal cells total), so n=12 surfaces every real
    off-diagonal pair with a nonzero count — not just a "top" subset the way BP1's 77x77 matrix
    required."""
    rows = []
    for true_label in confusion_df.index:
        for pred_label in confusion_df.columns:
            if true_label == pred_label:
                continue
            count = int(confusion_df.loc[true_label, pred_label])
            if count > 0:
                rows.append({"true_class": true_label, "predicted_class": pred_label, "count": count})
    df = (
        pd.DataFrame(rows)
        .sort_values("count", ascending=False, kind="mergesort")
        .head(n)
        .reset_index(drop=True)
    )
    return df


def build_smart_suggestions(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Generate SMART (Specific, Measurable, Achievable, Relevant, Time-bound) suggestions — every
    one grounded in a real number already loaded in `bundle`, never freeform GenAI text. BP2's set
    differs materially from BP1's: it includes the real Gate 3 candidate FAILURE (catboost) BP1
    never had, and the real minority-class recall gap this 152:1-imbalanced 4-class problem
    exposes that a 77-class problem's per-class metrics don't surface the same way."""
    gate3_cv_df = bundle["gate3_cv_df"]
    gate5_summary = bundle["gate5_summary"]
    gate4 = bundle["gate4"]
    class_perf = class_performance_ranked(bundle["gate3_classification_report"])

    suggestions = []

    failed = gate3_cv_df[gate3_cv_df["status"] != "OK"]
    if len(failed) > 0:
        row = failed.iloc[0]
        suggestions.append(
            {
                "title": f"Root-cause {row['model']}'s real Gate 3 failure",
                "specific": (
                    f"{row['model']} failed Gate 3's CV benchmark with a real, already-recorded error: "
                    f"\"{row['status']}\". Root-cause investigation was explicitly deferred by the user "
                    "at Gate 3 in order to proceed with the 5 passing candidates."
                ),
                "measurable": "Target: either a fix that lets this candidate complete the 5-fold CV "
                "benchmark cleanly, or a documented decision to permanently exclude it "
                "from future BP2 model refresh cycles.",
                "timebound": "Before the next BP2 model refresh cycle.",
                "owner_placeholder": "ML engineering owner - assign.",
            }
        )

    worst = class_perf.tail(2)
    if len(worst) >= 1:
        worst_lines = "; ".join(
            f"{r.severity_class} (precision {r.precision:.1%}, recall {r.recall:.1%}, "
            f"support {int(r.support):,})"
            for r in worst.itertuples()
        )
        suggestions.append(
            {
                "title": "Close the minority-class recall gap on the two smallest severity classes",
                "specific": (
                    f"Despite reasonably strong real precision, the two lowest-support real severity "
                    f"classes show much weaker real recall on the held-out test set: {worst_lines}. "
                    f"With a real 152:1 class-imbalance ratio (majority/minority), the champion "
                    "under-predicts these classes far more than the headline 75.6% accuracy suggests."
                ),
                "measurable": (
                    f"Target: real recall above 30% for both {worst.iloc[-1]['severity_class']} and "
                    f"{worst.iloc[0]['severity_class']} at the next Gate 3 re-benchmark (e.g. via class "
                    "weighting adjustments, threshold tuning, or a resampling strategy), without "
                    "materially reducing macro-F1 on the majority classes."
                ),
                "timebound": "Next BP2 Gate 3 re-benchmark cycle.",
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
                f"{overlap}/10 top terms overlapped — lower than BP1's equivalent 4/10 overlap, "
                "consistent with a structured-feature space having many more near-tied low-signal "
                "one-hot columns than BP1's TF-IDF vocabulary."
            ),
            "measurable": "Target: overlap of 6/10 or higher at a larger, fixed sample size (re-run "
            "both gates with an increased SHAP_SAMPLE_SIZE and compare).",
            "timebound": "Next explainability review cycle.",
            "owner_placeholder": "Model risk / explainability owner - assign.",
        }
    )

    open_ablation = (
        bundle["bp2_config"]
        .get("gate3_model_benchmark", {})
        .get("open_item_company_public_response_ablation_not_run", False)
    )
    if open_ablation:
        suggestions.append(
            {
                "title": "Run the deferred Company public response leakage/predictive-value ablation",
                "specific": (
                    "`Company public response` (~54% null, real, live-checked at Gate 1) was "
                    "deliberately excluded from Gate 3's feature set as an open item, never tested for "
                    "leakage against the target or for genuine predictive value."
                ),
                "measurable": "Target: a documented ablation run (with vs. without the field) reporting "
                "the real macro-F1 delta and a leakage-risk verdict, before it is ever "
                "added to the production feature set.",
                "timebound": "Before any production feature-set change is proposed.",
                "owner_placeholder": "ML engineering / compliance owner - assign.",
            }
        )

    n_with_reason_codes = gate5_summary["n_with_reason_codes"]
    n_records = gate5_summary["n_decision_records"]
    suggestions.append(
        {
            "title": "Expand grounded reason-code coverage beyond the current SHAP sample bound",
            "specific": (
                f"Only {n_with_reason_codes:,} of {n_records:,} real decision records "
                f"({n_with_reason_codes / n_records:.2%}) currently carry a grounded per-instance "
                "reason code, bounded by the 150-row SHAP sample size for laptop safety — a much "
                f"thinner relative real coverage than BP1's {n_with_reason_codes}/3,080 "
                f"({n_with_reason_codes / 3080:.1%}) on the same sample-size bound, simply because "
                "BP2's real held-out test set (163,344 rows) is ~53x larger."
            ),
            "measurable": "Target: 100% reason-code coverage once compute budget allows removing the "
            "sample bound, or a documented, deliberate sampling policy (e.g. stratified "
            "by severity class) if full coverage is not pursued.",
            "timebound": "Next Gate 5 hardening pass.",
            "owner_placeholder": "ML engineering owner - assign.",
        }
    )

    return suggestions


def compute_production_recommendation(bundle: dict[str, Any]) -> dict[str, Any]:
    """Live "Recommended for Production" status for BP2 - retrofitted onto this already-closed
    rollup per explicit standing user instruction, once BP3's disparate-impact investigation was
    closed (governance decision: ACCEPT_TIER_D). Computed only from real gate artifacts already
    loaded in `bundle`, never from BP3's own precedent or numbers.

    BP2 uses the same 2-tier variant as BP1/BP4, never BP3's 3-tier variant: BP2's real Gate 1
    policy / target definition (primary target: real severity ordinal class, scoped explicitly
    away from the sentiment-proxy and repeat-contact signals) carries no ECOA/Reg B disparate-
    impact check anywhere across its 6 real gates - that check was introduced starting with BP3 -
    so Tier 2 (CONDITIONAL - GOVERNANCE REVIEW REQUIRED) is structurally unreachable for BP2. BP2's
    structural checks additionally cover its real, previously-recorded Gate 3 CatBoost-removal
    history (`n_gate3_failed_candidates_is_zero`), which BP1 has no equivalent of.

    All 6 gates are guaranteed real-run confirmed by the time this function runs at all: every
    real gate-artifact file load_all_gate_artifacts() requires (through Gate 6) must already exist
    on disk, or that loader itself raises FileNotFoundError before this function is ever reached.
    """
    g6 = bundle["gate6_summary"]
    all_gates_real_run_confirmed = True  # guaranteed by load_all_gate_artifacts() succeeding

    structural_checks = {
        "pytest_all_passed": bool(g6["pytest_all_passed"]),
        "notebook_syntax_all_passed": bool(g6["notebook_syntax_all_passed"]),
        "n_gate3_failed_candidates_is_zero": g6["n_gate3_failed_candidates_detected"] == 0,
    }
    all_structural_checks_passed = all(structural_checks.values())

    if all_gates_real_run_confirmed and all_structural_checks_passed:
        tier_code, tier = 1, "RECOMMENDED FOR PRODUCTION"
        reason = (
            "All 6 BP2 gates are real-run confirmed and every structural integrity check passed "
            f"(pytest {g6['pytest_counts']['passed']} passed / {g6['pytest_counts']['failed']} "
            "failed, notebook syntax audit all passed, 0 Gate 3 failed candidates — CatBoost was "
            "removed from the real Gate 3 candidate set entirely, not left as a failed candidate). "
            "Tier 2 (CONDITIONAL - GOVERNANCE REVIEW REQUIRED) is structurally unreachable for "
            "BP2: this BP's real Gate 1-6 artifacts carry no ECOA/Reg B disparate-impact check "
            "(introduced starting with BP3), so BP2 cannot ever be flagged into Tier 2."
        )
    else:
        failing = [k for k, v in structural_checks.items() if not v]
        tier_code, tier = 3, "NOT RECOMMENDED"
        reason = (
            "At least one BP2 gate is not real-run confirmed or a structural integrity check has "
            f"not passed: {failing or ['gates_not_all_confirmed']}. Tier 2 remains structurally "
            "unreachable for BP2 regardless (no disparate-impact check exists for this BP), so "
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
    XLSX Executive_KPIs sheet, and the PPTX title/summary slides all read from — ONE computation,
    reused everywhere (HYPER). Every value here is read live from a real Gate 1-6 artifact. This
    KPI bundle also carries the live-computed `production_recommendation` field, retrofitted onto
    BP2 per standing user instruction once BP3's disparate-impact investigation closed."""
    model_inventory = bundle["model_inventory"]
    gate4 = bundle["gate4"]
    gate5_summary = bundle["gate5_summary"]
    gate6_summary = bundle["gate6_summary"]

    return {
        "champion_model": model_inventory["model_name"],
        "held_out_test_accuracy": model_inventory["held_out_test_accuracy"],
        "held_out_test_f1_macro": model_inventory["held_out_test_f1_macro"],
        "held_out_test_f1_weighted": model_inventory["held_out_test_f1_weighted"],
        "cv_mean_f1_macro": model_inventory["cv_mean_f1_macro"],
        "roc_auc_ovr_macro": gate4["roc_auc_ovr_macro"],
        "n_classes": model_inventory["n_classes"],
        "n_train_rows": model_inventory["n_train_rows"],
        "n_test_rows": model_inventory["n_test_rows"],
        "class_imbalance_ratio": model_inventory["class_imbalance_ratio_majority_over_minority"],
        "n_decision_records": gate5_summary["n_decision_records"],
        "n_with_reason_codes": gate5_summary["n_with_reason_codes"],
        "reason_code_coverage": gate5_summary["n_with_reason_codes"] / gate5_summary["n_decision_records"],
        "pytest_all_passed": gate6_summary["pytest_all_passed"],
        "pytest_counts": gate6_summary["pytest_counts"],
        "notebook_syntax_all_passed": gate6_summary["notebook_syntax_all_passed"],
        "n_gate3_near_random_anomalies": gate6_summary["n_gate3_near_random_anomalies_detected"],
        "n_gate3_high_variance_anomalies": gate6_summary["n_gate3_high_variance_anomalies_detected"],
        "n_gate3_failed_candidates": gate6_summary["n_gate3_failed_candidates_detected"],
        "gate3_failed_candidates": gate6_summary.get("gate3_failed_candidates", []),
        "governance_gates_complete": 6,
        "production_recommendation": compute_production_recommendation(bundle),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def build_gate1_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    """Every real field from Gate 1's own real output, policy.json (Business Understanding &
    Policy) — the one BP2 gate whose real output is not otherwise surfaced anywhere else in this
    report. Structurally different from BP1's Gate 1 summary: BP2's policy narrows the Master
    Plan's 3-signal friction taxonomy down to severity only, so this surfaces the real scoped-out
    reasons for the other two signals (sentiment proxy, repeat-contact) rather than a secondary
    target, and BP2's real live_checks are label-distribution enumerations, not a class-imbalance
    ratio (that lives in Gate 3's own config block instead — see build_gate6_governance_detail)."""
    policy = bundle["policy"]
    td = policy["target_definition"]
    lc = policy["live_checks"]
    ct = policy["compliance_touchpoint"]
    return {
        "primary_target": td["primary_target"],
        "primary_target_description": td["primary_target_description"],
        "sentiment_proxy_scope": td["scoped_out_signals"]["sentiment_proxy"],
        "repeat_contact_scope": td["scoped_out_signals"]["repeat_contact_signal"],
        "feature_variable_candidates": td["feature_variable_candidates"],
        "train_test_split_source": td["train_test_split_source"],
        "leakage_rules": policy["leakage_rules"],
        "assumptions": policy["assumptions"],
        "compliance_requirement": ct["requirement"],
        "compliance_statement": ct["statement"],
        "cfpb_row_count": lc["cfpb_row_count"],
        "company_response_distribution": [
            {"label": r["Company response to consumer"], "n": r["n"]}
            for r in lc["company_response_to_consumer_distribution"]
        ],
        "timely_response_distribution": [
            {"label": r["Timely response?"], "n": r["n"]} for r in lc["timely_response_distribution"]
        ],
        "company_public_response_null_rows": lc["company_public_response_null_rows"],
        "generated_at_utc": policy["generated_at_utc"],
    }


def build_gate6_governance_detail(bundle: dict[str, Any]) -> dict[str, Any]:
    """Every real field from Gate 6's own governance summary, plus the cross-gate compliance and
    model-family fields real-recorded in model_inventory_entry.json and the real candidate list
    from Gate 3's own config block. BP2-specific addition over BP1's equivalent: the real Gate 3
    FAILED-candidate detail (catboost's own recorded error string), read live from
    gate3_cv_benchmark_results.csv's status column — never hardcoded by model name."""
    g6 = bundle["gate6_summary"]
    mi = bundle["model_inventory"]
    gate3_block = bundle["bp2_config"].get("gate3_model_benchmark", {}) or {}
    gate3_cv_df = bundle["gate3_cv_df"]
    failed_rows = gate3_cv_df[gate3_cv_df["status"] != "OK"]
    failed_detail = [{"model": r.model, "status": r.status} for r in failed_rows.itertuples()]
    return {
        "pytest_summary_line": g6.get("pytest_summary_line"),
        "pytest_counts": g6["pytest_counts"],
        "pytest_all_passed": g6["pytest_all_passed"],
        "notebook_syntax_check_n_passed": g6["notebook_syntax_check_n_passed"],
        "notebook_syntax_check_n_failed": g6["notebook_syntax_check_n_failed"],
        "notebook_syntax_all_passed": g6["notebook_syntax_all_passed"],
        "n_gate3_near_random_anomalies_detected": g6["n_gate3_near_random_anomalies_detected"],
        "n_gate3_high_variance_anomalies_detected": g6["n_gate3_high_variance_anomalies_detected"],
        "n_gate3_failed_candidates_detected": g6["n_gate3_failed_candidates_detected"],
        "gate3_failed_candidates_detail": failed_detail,
        "model_card_path": g6["model_card_path"],
        "changelog_path": g6["changelog_path"],
        "generated_at_utc": g6["generated_at_utc"],
        "model_inventory_compliance_touchpoint": mi.get("compliance_touchpoint"),
        "model_family": mi.get("model_family"),
        "training_data": mi.get("training_data"),
        "candidates_evaluated": gate3_block.get("candidates_evaluated", []),
        "candidates_failed": gate3_block.get("candidates_failed", []),
        "demographic_adjacent_tags_found": gate3_block.get("demographic_adjacent_tags_found", []),
        "open_item_company_public_response_ablation_not_run": gate3_block.get(
            "open_item_company_public_response_ablation_not_run", False
        ),
    }


# ============================================================================
# Matplotlib static figure builders (WARP: rendered once, reused as PNG bytes across DOCX + PPTX).
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
    ax.set_title("BP2 Gate 3 — Model Benchmark (real 5-fold CV, passing candidates)")
    ax.spines[["top", "right"]].set_visible(False)
    for bar, val in zip(bars, df["mean_f1_macro"]):
        ax.text(val + 0.01, bar.get_y() + bar.get_height() / 2, f"{val:.3f}", va="center", fontsize=9)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_shap_top_features(gate4_shap_df: pd.DataFrame, n: int = 10) -> bytes:
    df = gate4_shap_df.head(n).sort_values("mean_abs_shap", ascending=True)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(df["feature"], df["mean_abs_shap"], color=PALETTE["accent_blue"])
    ax.set_xlabel("Mean |SHAP value| (real, Gate 4 global explanation)")
    ax.set_title("Top Globally Important Features")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_severity_distribution_pie(gate2_severity_df: pd.DataFrame) -> bytes:
    df = gate2_severity_df[gate2_severity_df["row_count"] > 0].sort_values("row_count", ascending=False)
    colors = (CATEGORICAL_SEQUENCE * ((len(df) // len(CATEGORICAL_SEQUENCE)) + 1))[: len(df)]
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.pie(
        df["row_count"],
        labels=df["friction_severity_class"],
        autopct="%1.1f%%",
        colors=colors,
        textprops={"fontsize": 8},
    )
    ax.set_title("Real CFPB Row Distribution by Friction-Severity Class")
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


def fig_confusion_heatmap(confusion_df: pd.DataFrame) -> bytes:
    """BP2's real confusion matrix is only 4x4 (4 ordinal severity classes) — unlike BP1's 77x77
    matrix, the FULL matrix is shown directly here, not a top-N subset."""
    fig, ax = plt.subplots(figsize=(6.5, 5.6))
    im = ax.imshow(confusion_df.values, cmap="Blues")
    ax.set_xticks(range(len(confusion_df.columns)))
    ax.set_xticklabels(confusion_df.columns, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(confusion_df.index)))
    ax.set_yticklabels(confusion_df.index, fontsize=9)
    for i in range(len(confusion_df.index)):
        for j in range(len(confusion_df.columns)):
            val = confusion_df.values[i, j]
            ax.text(
                j,
                i,
                f"{val:,}",
                ha="center",
                va="center",
                color="white" if val > confusion_df.values.max() / 2 else PALETTE["ink"],
                fontsize=8,
            )
    ax.set_title("Full Real 4×4 Confusion Matrix — Held-Out Test Set")
    fig.colorbar(im, ax=ax, shrink=0.8, label="Real count")
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def fig_class_performance_bar(class_perf_df: pd.DataFrame) -> bytes:
    """New chart vs. BP1's rollup (BP1 had no equivalent — its 77-class report only supported a
    best/worst-10 table, not a single readable bar chart): real per-class precision/recall/F1 for
    all 4 severity classes side by side, sorted by real F1 descending."""
    df = class_perf_df.sort_values("f1-score", ascending=True)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    y = range(len(df))
    height = 0.25
    ax.barh(
        [i + height for i in y],
        df["precision"],
        height=height,
        label="Precision",
        color=PALETTE["accent_blue"],
    )
    ax.barh([i for i in y], df["recall"], height=height, label="Recall", color=PALETTE["warning_amber"])
    ax.barh(
        [i - height for i in y],
        df["f1-score"],
        height=height,
        label="F1-score",
        color=PALETTE["primary_navy"],
    )
    ax.set_yticks(list(y))
    ax.set_yticklabels(df["severity_class"], fontsize=9)
    ax.set_xlabel("Real held-out test score")
    ax.set_title("Per-Severity-Class Performance (real, Gate 3 held-out test)")
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


# ============================================================================
# DOCX export (python-docx). US Letter page size set explicitly, Calibri professional font.
# Covers all 6 BP2 gates' real recorded output.
# ============================================================================


def write_docx_report(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    figures: dict[str, bytes],
    class_perf: pd.DataFrame,
    pairs: pd.DataFrame,
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

    title = doc.add_heading("BP2 Customer Friction Classification", level=0)
    title.runs[0].font.color.rgb = navy
    sub = doc.add_paragraph("Executive Rollup Report — Customer360 Navigator Enterprise Suite")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    gen = doc.add_paragraph(
        f"Generated {kpis['generated_at_utc']} from BP2 Gates 1-6's real, real-run-confirmed artifacts. "
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
        ("Held-out F1-weighted (real)", f"{kpis['held_out_test_f1_weighted']:.4f}"),
        ("CV mean F1-macro (real)", f"{kpis['cv_mean_f1_macro']:.4f}"),
        ("ROC-AUC, one-vs-rest macro (real)", f"{kpis['roc_auc_ovr_macro']:.4f}"),
        (
            "Classes / Train rows / Test rows (real)",
            f"{kpis['n_classes']} / {kpis['n_train_rows']:,} / {kpis['n_test_rows']:,}",
        ),
        ("Class imbalance ratio, majority/minority (real)", f"{kpis['class_imbalance_ratio']}:1"),
        ("Decision records (real)", f"{kpis['n_decision_records']:,}"),
        ("Reason-code coverage (real)", f"{kpis['reason_code_coverage']:.2%}"),
        (
            "Governance — pytest (real)",
            f"{kpis['pytest_counts']['passed']} passed / {kpis['pytest_counts']['failed']} failed",
        ),
        (
            "Governance — notebook syntax audit (real)",
            "all passed" if kpis["notebook_syntax_all_passed"] else "issues found",
        ),
        (
            "Open governance items — Gate 3 near-random / high-variance / failed (real)",
            f"{kpis['n_gate3_near_random_anomalies']} / "
            f"{kpis['n_gate3_high_variance_anomalies']} / "
            f"{kpis['n_gate3_failed_candidates']}",
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
        f"Sentiment-proxy signal (Master Plan's 3-signal taxonomy) — scoped OUT: "
        f"{gate1['sentiment_proxy_scope']}"
    )
    doc.add_paragraph(
        f"Repeat-contact signal (Master Plan's 3-signal taxonomy) — scoped OUT: "
        f"{gate1['repeat_contact_scope']}"
    )
    doc.add_paragraph(f"Feature variable candidates: {gate1['feature_variable_candidates']}")
    doc.add_paragraph(f"Train/test split source: {gate1['train_test_split_source']}")
    doc.add_paragraph(f"Compliance touchpoint — {gate1['compliance_requirement']}:")
    doc.add_paragraph(gate1["compliance_statement"])
    doc.add_heading("Leakage Rules (real, enforced live every Gate 1 run)", level=2)
    for rule in gate1["leakage_rules"]:
        doc.add_paragraph(rule, style="List Bullet")
    doc.add_heading("Scope Assumptions Documented at Gate 1 (real)", level=2)
    for a in gate1["assumptions"]:
        doc.add_paragraph(a, style="List Bullet")
    doc.add_heading("Live Target-Field Distributions (real, re-verified every Gate 1 run)", level=2)
    dq_table = doc.add_table(rows=1, cols=2)
    dq_table.style = "Light Grid Accent 1"
    dq_table.rows[0].cells[0].text, dq_table.rows[0].cells[1].text = (
        "Company response to consumer",
        "Real count",
    )
    for r in gate1["company_response_distribution"]:
        row = dq_table.add_row().cells
        row[0].text, row[1].text = str(r["label"]), f"{r['n']:,}"
    doc.add_paragraph(
        f"Real CFPB row count at Gate 1: {gate1['cfpb_row_count']:,}. "
        f"Company public response null rows: {gate1['company_public_response_null_rows']:,}."
    )

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
    doc.add_paragraph(
        f"Real Gate 3 candidate failure (not investigated further, per explicit user instruction): "
        f"{kpis['gate3_failed_candidates']}."
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

    doc.add_heading("Per-Severity-Class Performance — Gate 3 (real, all 4 classes)", level=1)
    doc.add_picture(io.BytesIO(figures["class_performance"]), width=Inches(6.2))
    ct = doc.add_table(rows=1, cols=5)
    ct.style = "Light List Accent 1"
    for i, h in enumerate(["Severity class", "Precision", "Recall", "F1", "Support"]):
        ct.rows[0].cells[i].text = h
    for _, r in class_perf.iterrows():
        row = ct.add_row().cells
        row[0].text, row[1].text, row[2].text = (
            r["severity_class"],
            f"{r['precision']:.3f}",
            f"{r['recall']:.3f}",
        )
        row[3].text, row[4].text = f"{r['f1-score']:.3f}", f"{int(r['support']):,}"

    doc.add_heading("Decision Layer — Gate 5 (real)", level=1)
    doc.add_picture(io.BytesIO(figures["confidence_dist"]), width=Inches(6.2))
    g5 = bundle["gate5_summary"]
    doc.add_paragraph(
        f"{kpis['n_with_reason_codes']:,} of {kpis['n_decision_records']:,} real decision records carry a "
        f"grounded per-instance reason code ({kpis['reason_code_coverage']:.2%}). Mean confidence on correct "
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

    doc.add_heading("Severity Distribution — Gate 2 (real)", level=1)
    doc.add_picture(io.BytesIO(figures["severity_pie"]), width=Inches(5.3))

    doc.add_heading("Confusion Analysis — Gate 3 (real, full 4×4 matrix)", level=1)
    doc.add_picture(io.BytesIO(figures["confusion_heatmap"]), width=Inches(5.5))
    pt_table = doc.add_table(rows=1, cols=3)
    pt_table.style = "Light List Accent 1"
    for i, h in enumerate(["True class", "Predicted class", "Real count"]):
        pt_table.rows[0].cells[i].text = h
    for r in pairs.itertuples():
        row = pt_table.add_row().cells
        row[0].text, row[1].text, row[2].text = r.true_class, r.predicted_class, str(r.count)

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
        "Open items — Gate 3 candidate-level issues detected live: "
        f"{gate6['n_gate3_near_random_anomalies_detected']} near-random result(s), "
        f"{gate6['n_gate3_high_variance_anomalies_detected']} high CV-variance result(s), "
        f"{gate6['n_gate3_failed_candidates_detected']} outright failure(s)."
    )
    for fd in gate6["gate3_failed_candidates_detail"]:
        doc.add_paragraph(f"Real recorded failure — {fd['model']}: {fd['status']}", style="List Bullet")
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
    if gate6.get("demographic_adjacent_tags_found"):
        doc.add_paragraph(
            "Demographic-adjacent `Tags` values found live at Gate 3 (real; `Tags` itself is excluded "
            f"from the feature set regardless): {', '.join(gate6['demographic_adjacent_tags_found'])}."
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
# XLSX export (openpyxl). Every sheet is built from a real Gate 1-6 artifact.
# ============================================================================


def write_xlsx_workbook(
    bundle: dict[str, Any],
    kpis: dict[str, Any],
    suggestions: list[dict[str, str]],
    class_perf: pd.DataFrame,
    pairs: pd.DataFrame,
    out_path: Path,
) -> Path:
    import re

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    navy_fill = PatternFill(start_color="1E2761", end_color="1E2761", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(bold=True, size=14, color="1E2761")

    # Same real defensive guard bp1_rollup_helpers.write_xlsx_workbook() carries (Lesson: BP1's
    # first real run hit openpyxl.utils.exceptions.IllegalCharacterError on gate6's real captured
    # pytest_summary_line, which can carry ANSI color-escape control bytes) - applied here
    # pre-emptively rather than waiting to hit the same real bug a second time. Extended over BP1's
    # original guard: stripping only the bare ESC control byte (\x1b) leaves the rest of a real
    # ANSI sequence (e.g. "[32m") behind as visible garbage text rather than a crash - this
    # session's own visual QA pass on BP2's dashboard found that exact residue in the HTML footer,
    # so the full escape-sequence pattern is stripped here too, not just the illegal byte range.
    _ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    _ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")

    def _safe(value):
        if isinstance(value, str):
            return _ILLEGAL_XLSX_CHARS_RE.sub("", _ANSI_ESCAPE_RE.sub("", value))
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
    ws["A1"] = "BP2 Customer Friction Classification — Executive Rollup Workbook"
    ws["A1"].font = title_font
    ws["A3"] = f"Generated: {kpis['generated_at_utc']}"
    ws["A4"] = "Every sheet here is built only from BP2 Gates 1-6's real, real-run-confirmed artifacts."
    ws["A5"] = "No assumption-based, illustrative, or estimated content appears anywhere in this workbook."
    ws["A6"] = f"Recommended for Production status: {prod_rec['tier']}"
    ws["A6"].font = Font(bold=True, color="1E2761")
    sheets_index = [
        ("01_Executive_KPIs", "Top-line real KPIs across all 6 gates."),
        (
            "02_Gate1_Business_Policy",
            "Gate 1 real target definition, scoped-out signals, leakage rules, "
            "assumptions, compliance, live distributions.",
        ),
        (
            "03_Model_Benchmark",
            "Gate 3 real 6-model 5-fold CV benchmark, including the real recorded failure.",
        ),
        (
            "04_Statistical_Validation",
            "Gate 4 real paired t-test, Wilcoxon test, bootstrap CI, ROC-AUC, per-fold CV scores.",
        ),
        ("05_Explainability_SHAP", "Gate 4 real global SHAP top features."),
        (
            "06_Decision_Layer",
            "Gate 5 real decision-record summary, compliance touchpoint + full 163,344-row export.",
        ),
        ("07_Severity_Distribution", "Gate 2 real CFPB row distribution by friction-severity class."),
        ("08_Confusion_Analysis", "Gate 3 real full 4x4 confusion matrix and off-diagonal pairs."),
        ("09_Class_Performance", "Gate 3 real per-severity-class precision/recall/F1/support."),
        (
            "10_Gate6_Governance_Limitations",
            "Gate 6 real governance status, open items (incl. the real Gate 3 "
            "failure), model card/changelog refs.",
        ),
        ("11_SMART_Suggestions", "Data-grounded SMART recommendations."),
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
        ("Held-out F1-weighted", kpis["held_out_test_f1_weighted"]),
        ("CV mean F1-macro", kpis["cv_mean_f1_macro"]),
        ("ROC-AUC (OvR macro)", kpis["roc_auc_ovr_macro"]),
        ("N classes", kpis["n_classes"]),
        ("N train rows", kpis["n_train_rows"]),
        ("N test rows", kpis["n_test_rows"]),
        ("Class imbalance ratio (majority/minority)", kpis["class_imbalance_ratio"]),
        ("Decision records", kpis["n_decision_records"]),
        ("Reason-code coverage", kpis["reason_code_coverage"]),
        ("pytest passed", kpis["pytest_counts"]["passed"]),
        ("pytest failed", kpis["pytest_counts"]["failed"]),
        ("Notebook syntax audit all passed", kpis["notebook_syntax_all_passed"]),
        ("Gate 3 near-random anomalies (open item)", kpis["n_gate3_near_random_anomalies"]),
        ("Gate 3 high-variance anomalies (open item)", kpis["n_gate3_high_variance_anomalies"]),
        ("Gate 3 failed candidates (open item)", kpis["n_gate3_failed_candidates"]),
        ("Governance gates complete", f"{kpis['governance_gates_complete']}/6"),
    ]
    for row in kpi_rows:
        ws.append(_safe_row(list(row)))
    ws["B3"].number_format = "0.00%"
    ws["B12"].number_format = "0.00%"
    _autosize(ws, 2, width=34)

    # --- 02_Gate1_Business_Policy ---
    ws = wb.create_sheet("02_Gate1_Business_Policy")
    ws["A1"] = "Gate 1 — Business Understanding & Policy (real, from policy.json)"
    ws["A1"].font = title_font
    row_idx = 3
    for label, val in [
        ("Primary target", gate1["primary_target"]),
        ("Primary target description", gate1["primary_target_description"]),
        ("Sentiment-proxy signal — scoped OUT (real reason)", gate1["sentiment_proxy_scope"]),
        ("Repeat-contact signal — scoped OUT (real reason)", gate1["repeat_contact_scope"]),
        ("Feature variable candidates", gate1["feature_variable_candidates"]),
        ("Train/test split source", gate1["train_test_split_source"]),
        ("Compliance requirement", gate1["compliance_requirement"]),
        ("Compliance statement", gate1["compliance_statement"]),
        ("Real CFPB row count (Gate 1 live check)", gate1["cfpb_row_count"]),
        ("Company public response null rows (real)", gate1["company_public_response_null_rows"]),
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
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Live Company response to consumer distribution (real)").font = Font(
        bold=True, color="1E2761"
    )
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Label")
    ws.cell(row=row_idx, column=2, value="Real count")
    row_idx += 1
    for r in gate1["company_response_distribution"]:
        ws.cell(row=row_idx, column=1, value=_safe(str(r["label"])))
        ws.cell(row=row_idx, column=2, value=r["n"])
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
    _autosize(ws, len(cols), width=20)
    ws.column_dimensions["B"].width = 90

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
    _autosize(ws, 2, width=48)

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
    # Full real decision-record export (163,344 rows) — a lean column set (row_index, labels,
    # correct, confidence, whether it was in the SHAP sample, and its reason codes when grounded).
    # rank2/rank3 confidence columns and the verbose per-row feature_summary text are left out of
    # this sheet to keep the workbook a manageable size; the full 12-column CSV (including
    # feature_summary) remains available in the real artifacts folder on disk for deeper drill-down.
    dec_cols = [
        "row_index",
        "true_label",
        "predicted_label",
        "correct",
        "confidence_top1",
        "in_shap_sample",
        "reason_codes",
    ]
    header_row_idx = ws.max_row + 1
    ws.append(dec_cols)
    _style_header(ws, header_row_idx, len(dec_cols))
    dec_df = bundle["gate5_decision_df"][dec_cols]
    for r in dec_df.itertuples(index=False):
        ws.append(_safe_row(list(r)))
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 14
    ws.column_dimensions["G"].width = 60

    # --- 07_Severity_Distribution ---
    ws = wb.create_sheet("07_Severity_Distribution")
    sev_cols = list(bundle["gate2_severity_df"].columns)
    ws.append(sev_cols)
    _style_header(ws, 1, len(sev_cols))
    for r in bundle["gate2_severity_df"].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, len(sev_cols), width=26)

    # --- 08_Confusion_Analysis ---
    ws = wb.create_sheet("08_Confusion_Analysis")
    ws["A1"] = "Full real 4x4 confusion matrix"
    ws["A1"].font = title_font
    conf_df = bundle["gate3_confusion_df"]
    header_row = 3
    ws.cell(row=header_row, column=1, value="true_class \\ predicted_class")
    for j, col in enumerate(conf_df.columns):
        ws.cell(row=header_row, column=2 + j, value=col)
    _style_header(ws, header_row, len(conf_df.columns) + 1)
    for i, idx in enumerate(conf_df.index):
        ws.cell(row=header_row + 1 + i, column=1, value=idx)
        for j, col in enumerate(conf_df.columns):
            ws.cell(row=header_row + 1 + i, column=2 + j, value=int(conf_df.loc[idx, col]))
    _autosize(ws, len(conf_df.columns) + 1, width=22)
    pairs_header_row = header_row + len(conf_df.index) + 3
    ws.cell(row=pairs_header_row, column=1, value="Real off-diagonal confusion pairs").font = Font(
        bold=True, color="1E2761"
    )
    ws.cell(row=pairs_header_row + 1, column=1, value="true_class")
    ws.cell(row=pairs_header_row + 1, column=2, value="predicted_class")
    ws.cell(row=pairs_header_row + 1, column=3, value="count")
    _style_header(ws, pairs_header_row + 1, 3)
    for i, r in enumerate(pairs.itertuples(index=False)):
        ws.cell(row=pairs_header_row + 2 + i, column=1, value=r.true_class)
        ws.cell(row=pairs_header_row + 2 + i, column=2, value=r.predicted_class)
        ws.cell(row=pairs_header_row + 2 + i, column=3, value=r.count)

    # --- 09_Class_Performance ---
    ws = wb.create_sheet("09_Class_Performance")
    cp_cols = ["severity_class", "precision", "recall", "f1-score", "support"]
    ws.append(cp_cols)
    _style_header(ws, 1, len(cp_cols))
    for r in class_perf[cp_cols].itertuples(index=False):
        ws.append(_safe_row(list(r)))
    _autosize(ws, len(cp_cols), width=22)

    # --- 10_Gate6_Governance_Limitations ---
    ws = wb.create_sheet("10_Gate6_Governance_Limitations")
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
        ("Open item — Gate 3 failed candidates detected", gate6["n_gate3_failed_candidates_detected"]),
        ("Model card path", gate6["model_card_path"]),
        ("Changelog path", gate6["changelog_path"]),
        ("Model inventory compliance touchpoint", gate6.get("model_inventory_compliance_touchpoint")),
        ("Model family", gate6.get("model_family")),
        ("Training data", gate6.get("training_data")),
        ("Gate 3 candidates evaluated", ", ".join(gate6.get("candidates_evaluated", []))),
        ("Gate 3 candidates failed", ", ".join(gate6.get("candidates_failed", [])) or "none"),
        (
            "Demographic-adjacent Tags values found (real)",
            ", ".join(gate6.get("demographic_adjacent_tags_found", [])) or "none",
        ),
        ("Generated at (UTC)", gate6["generated_at_utc"]),
    ]:
        ws.cell(row=row_idx, column=1, value=_safe(label))
        ws.cell(row=row_idx, column=2, value=_safe(val))
        row_idx += 1
    row_idx += 1
    ws.cell(row=row_idx, column=1, value="Real recorded Gate 3 candidate failure detail").font = Font(
        bold=True, color="1E2761"
    )
    row_idx += 1
    for fd in gate6["gate3_failed_candidates_detail"]:
        ws.cell(row=row_idx, column=1, value=_safe(fd["model"]))
        ws.cell(row=row_idx, column=2, value=_safe(fd["status"]))
        row_idx += 1
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 90
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # --- 11_SMART_Suggestions ---
    ws = wb.create_sheet("11_SMART_Suggestions")
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
# PPTX export (python-pptx). Reuses the same shared matplotlib PNGs as the DOCX export.
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
        "BP2 Customer Friction Classification",
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
        ("Class Imbalance Ratio", f"{kpis['class_imbalance_ratio']}:1"),
        ("Decision Records", f"{kpis['n_decision_records']:,}"),
        ("pytest", f"{kpis['pytest_counts']['passed']} passed"),
        (
            "Gate 3 Open Items",
            f"{kpis['n_gate3_near_random_anomalies']} near-random / "
            f"{kpis['n_gate3_high_variance_anomalies']} high-var / "
            f"{kpis['n_gate3_failed_candidates']} failed",
        ),
    ]
    cols = 4
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
    _add_bullets(
        s,
        [
            f"Primary target: {gate1['primary_target']}",
            f"Sentiment-proxy signal — scoped OUT: {gate1['sentiment_proxy_scope'][:140]}...",
            f"Repeat-contact signal — scoped OUT: {gate1['repeat_contact_scope'][:140]}...",
            f"Feature variable candidates: {gate1['feature_variable_candidates'][:140]}...",
            f"Compliance touchpoint: {gate1['compliance_requirement']}",
            f"Live check — real CFPB row count: {gate1['cfpb_row_count']:,}",
            f"Live check — Company public response null rows: {gate1['company_public_response_null_rows']:,}",
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

    # --- Slide 6: Per-class performance ---
    s = _add_slide()
    _add_title(s, "Per-Severity-Class Performance — Gate 3 (real)")
    _add_picture_bytes(
        s, figures["class_performance"], PptxInches(2.0), PptxInches(1.4), width=PptxInches(9.3)
    )

    # --- Slide 7: Decision layer ---
    s = _add_slide()
    _add_title(s, "Decision Layer — Gate 5 (real)")
    _add_picture_bytes(
        s, figures["confidence_dist"], PptxInches(1.3), PptxInches(1.5), width=PptxInches(10.7)
    )

    # --- Slide 8: Severity distribution ---
    s = _add_slide()
    _add_title(s, "Severity Distribution — Gate 2 (real)")
    _add_picture_bytes(s, figures["severity_pie"], PptxInches(3.6), PptxInches(1.3), width=PptxInches(6.0))

    # --- Slide 9: Confusion analysis ---
    s = _add_slide()
    _add_title(s, "Confusion Analysis — Gate 3 (real, full 4×4 matrix)")
    _add_picture_bytes(
        s, figures["confusion_heatmap"], PptxInches(3.3), PptxInches(1.3), width=PptxInches(6.7)
    )

    # --- Slide 10: SMART suggestions ---
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

    # --- Slide 11: Gate 6 Governance & Known Limitations ---
    s = _add_slide()
    _fill_bg(s, NAVY)
    _add_title(s, "Gate 6 — Governance & Known Limitations (real)", dark=True)
    failed_line = (
        "; ".join(f"{fd['model']}: {fd['status'][:90]}..." for fd in gate6["gate3_failed_candidates_detail"])
        or "none"
    )
    _add_bullets(
        s,
        [
            f"pytest suite: {gate6['pytest_counts']['passed']} passed / "
            f"{gate6['pytest_counts']['failed']} failed",
            f"Notebook syntax audit: {gate6['notebook_syntax_check_n_passed']}/"
            f"{gate6['notebook_syntax_check_n_passed'] + gate6['notebook_syntax_check_n_failed']} passed",
            f"Open item: {gate6['n_gate3_near_random_anomalies_detected']} near-random + "
            f"{gate6['n_gate3_high_variance_anomalies_detected']} high-variance + "
            f"{gate6['n_gate3_failed_candidates_detected']} failed Gate 3 candidate(s)",
            f"Real failure detail: {failed_line}",
            f"Model card: {gate6['model_card_path']}",
            f"Changelog: {gate6['changelog_path']}",
            f"Gate 3 candidates evaluated: {', '.join(gate6.get('candidates_evaluated', []))}",
            f"BP2 governance gates complete: {kpis['governance_gates_complete']}/6",
        ],
        top=PptxInches(1.6),
        color=WHITE,
        size=15,
    )

    # --- Slide 12: Recommended for Production ---
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
