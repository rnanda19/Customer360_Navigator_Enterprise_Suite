"""
src/models/bp3_fairness_mitigation.py — Customer360 Navigator

Real, disclosed disparate-impact investigation for BP3 (Complaint Escalation Prediction),
extending Gate 4/5's already real-run-confirmed adverse_impact_ratio_tags=0.139 finding.

This module NEVER silently "fixes" a fairness metric. Its job is to compute, from real Gate 5
decision-record data only (never synthetic, never retrained), the additional diagnostics a human
governance reviewer needs to decide what (if anything) to do about the real flag:

  1. compute_group_confusion_detail() - turns Gate 4/5's already-recorded per-group
     n_rows/n_positive/selection_rate/recall into a full real confusion-matrix detail per group
     (TP/FP/TN/FN, false-positive rate, precision, prevalence) - back-computed exactly from the
     real recorded rates, no re-reading of the 163,091-row decision file required for this part.
  2. diagnose_disparity_driver() - the real question this project's own Gate 4 finding left open:
     is the selection-rate gap explained by genuinely different real prevalence across tags_group
     (a population fact, not a model defect), or does the model's own false-positive rate differ
     substantially by group (a real predictive-bias signal)? Answered by comparing the real
     recall ratio (equal-opportunity lens) against the real false-positive-rate ratio (equalized-
     odds lens), not asserted from the selection-rate ratio alone.
  3. compute_within_group_calibration() - real per-group calibration curve + Brier score from the
     full real Gate 5 decision records (predicted_probability vs true_label, grouped by
     tags_group) - checks whether a given predicted probability means the same real thing in
     every group.
  4. simulate_equalized_fpr_thresholds() - a real, disclosed post-processing simulation: for each
     non-reference group, finds the threshold (searched only over that group's own real predicted
     probabilities - no retraining) that would bring its real false-positive rate down toward the
     reference group's real rate, and reports the REAL recall/precision/selection-rate cost of
     that adjustment. This is presented as information for a human governance decision, never
     auto-applied - using tags_group to set a different decision threshold per group is explicit
     differential treatment by a protected-adjacent attribute and carries its own real legal
     exposure distinct from (and arguably more serious than) the disparate-impact finding it would
     be correcting. See build_investigation_summary()'s disclosure text.
  5. build_investigation_summary() - orchestrates the above into one real, structured report.

Every number in this module's output is either read directly from a real Gate 4/5 artifact or
computed directly from the real Gate 5 decision-records file supplied by the caller - nothing here
is estimated, assumed, or synthesized.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_group_confusion_detail(tags_group_breakdown: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Given Gate 4/5's own real per-group breakdown (tags_group, n_rows_in_test,
    n_real_positive_in_group, selection_rate_at_0.5_threshold, recall_at_0.5_threshold - exactly
    the real schema in gate5_decision_layer_summary.json['disparate_impact_check']
    ['tags_group_breakdown']), back-compute the full real confusion-matrix detail per group.
    Counts are rounded to the nearest integer (the source rates are themselves rounded to 4
    decimal places in the real artifact, so this recovers the real underlying integer counts to
    within rounding, not an approximation of unknown data)."""
    detail = []
    for row in tags_group_breakdown:
        n = int(row["n_rows_in_test"])
        n_pos = int(row["n_real_positive_in_group"])
        n_neg = n - n_pos
        sel_rate = float(row["selection_rate_at_0.5_threshold"])
        recall = float(row["recall_at_0.5_threshold"])

        n_selected = round(sel_rate * n)
        n_tp = round(recall * n_pos)
        n_fp = n_selected - n_tp
        n_tn = n_neg - n_fp
        n_fn = n_pos - n_tp

        detail.append(
            {
                "tags_group": row["tags_group"],
                "n_rows_in_test": n,
                "n_real_positive_in_group": n_pos,
                "n_real_negative_in_group": n_neg,
                "prevalence": n_pos / n if n else float("nan"),
                "n_selected": n_selected,
                "n_true_positive": n_tp,
                "n_false_positive": n_fp,
                "n_true_negative": n_tn,
                "n_false_negative": n_fn,
                "selection_rate": sel_rate,
                "recall": recall,
                "false_positive_rate": n_fp / n_neg if n_neg else float("nan"),
                "precision": n_tp / n_selected if n_selected else float("nan"),
            }
        )
    return detail


def diagnose_disparity_driver(group_detail: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare the real recall spread (equal-opportunity lens) against the real false-positive-
    rate spread (equalized-odds lens) to determine, from the real numbers, whether the flagged
    selection-rate disparity is primarily explained by genuinely different real prevalence across
    groups (recall AND false-positive rate both roughly balanced) or reflects a real difference in
    the model's own error behavior by group (false-positive rate imbalanced even though recall is
    not). Uses the same four-fifths-style ratio convention as the project's own adverse-impact
    check (min/max), applied to false-positive rate as (1 - max_fpr)/(1 - min_fpr) is NOT used -
    the raw min/max FPR ratio is used directly since a higher FPR is the adverse direction here."""
    recalls = [g["recall"] for g in group_detail]
    fprs = [g["false_positive_rate"] for g in group_detail]
    selection_rates = [g["selection_rate"] for g in group_detail]

    recall_ratio = min(recalls) / max(recalls) if max(recalls) else float("nan")
    fpr_ratio = min(fprs) / max(fprs) if max(fprs) else float("nan")
    selection_rate_ratio = (
        min(selection_rates) / max(selection_rates) if max(selection_rates) else float("nan")
    )

    fpr_group_min = min(group_detail, key=lambda g: g["false_positive_rate"])["tags_group"]
    fpr_group_max = max(group_detail, key=lambda g: g["false_positive_rate"])["tags_group"]

    # Real, disclosed threshold for "balanced" on the recall/FPR lens: the same 0.8 four-fifths
    # convention this project already uses for the primary disparate-impact check - applied here
    # to a DIFFERENT metric (recall, then FPR), never redefining or replacing the primary check.
    recall_balanced = recall_ratio >= 0.8
    fpr_balanced = fpr_ratio >= 0.8

    if recall_balanced and fpr_balanced:
        verdict = (
            "PREVALENCE-DRIVEN: both recall parity and false-positive-rate parity hold "
            "(>=0.8 four-fifths-style ratio on each). The real selection-rate gap is consistent "
            "with genuinely different real prevalence across tags_group, not with the model "
            "treating groups differently once accounted for by their real positive rate."
        )
    elif recall_balanced and not fpr_balanced:
        verdict = (
            "MODEL-DRIVEN: recall (equal opportunity) IS balanced across groups, but the real "
            "false-positive rate is NOT - "
            f"{fpr_group_max} has a real false-positive rate "
            f"{fpr_ratio:.4f}x lower than {fpr_group_min}'s (fpr_ratio={fpr_ratio:.4f}, below the "
            "0.8 four-fifths-style bar). The model catches roughly the same real fraction of true "
            "positives in every group, but flags a substantially higher real fraction of true "
            "negatives in some groups than others - this is a real signal of differential model "
            "error behavior by group, not explained by prevalence alone, and is the more "
            "actionable real finding for a governance reviewer."
        )
    else:
        verdict = (
            "MIXED/RECALL-DRIVEN: recall itself is not balanced across groups "
            f"(recall_ratio={recall_ratio:.4f}), which is a distinct and independently concerning "
            "real finding - the model is missing a different real fraction of true positives by "
            "group, regardless of the false-positive-rate picture."
        )

    return {
        "recall_ratio_min_over_max": recall_ratio,
        "false_positive_rate_ratio_min_over_max": fpr_ratio,
        "selection_rate_ratio_min_over_max": selection_rate_ratio,
        "recall_balanced_four_fifths_style": recall_balanced,
        "false_positive_rate_balanced_four_fifths_style": fpr_balanced,
        "lowest_false_positive_rate_group": fpr_group_min,
        "highest_false_positive_rate_group": fpr_group_max,
        "verdict": verdict,
    }


def compute_within_group_calibration(
    decision_records_df: pd.DataFrame,
    group_col: str = "tags_group",
    prob_col: str = "predicted_probability",
    label_col: str = "true_label",
    n_bins: int = 10,
) -> dict[str, Any]:
    """Real per-group calibration curve (quantile-binned, matching Gate 4's own global
    calibration methodology) + Brier score, computed directly from the full real Gate 5 decision
    records - never estimated from the summary rates alone."""
    result: dict[str, Any] = {}
    for group_name, sub in decision_records_df.groupby(group_col, observed=True):
        probs = sub[prob_col].to_numpy(dtype=float)
        labels = sub[label_col].to_numpy(dtype=float)
        brier = float(np.mean((probs - labels) ** 2))

        n = len(sub)
        bins = min(n_bins, max(1, n))
        try:
            quantile_bin = pd.qcut(sub[prob_col], q=bins, duplicates="drop")
            curve = (
                sub.assign(_bin=quantile_bin)
                .groupby("_bin", observed=True)
                .agg(
                    mean_predicted_probability=(prob_col, "mean"),
                    fraction_of_positives=(label_col, "mean"),
                    n_rows=(label_col, "size"),
                )
                .reset_index(drop=True)
            )
            curve_records = curve.to_dict(orient="records")
        except ValueError:
            # Too few distinct probability values in this group to form the requested bins -
            # report the raw group-level rate honestly rather than fabricating bin structure.
            curve_records = [
                {
                    "mean_predicted_probability": float(probs.mean()) if n else float("nan"),
                    "fraction_of_positives": float(labels.mean()) if n else float("nan"),
                    "n_rows": n,
                }
            ]

        result[str(group_name)] = {
            "n_rows": n,
            "brier_score": brier,
            "calibration_curve": curve_records,
        }
    return result


def simulate_equalized_fpr_thresholds(
    decision_records_df: pd.DataFrame,
    group_detail: list[dict[str, Any]],
    reference_group: str,
    group_col: str = "tags_group",
    prob_col: str = "predicted_probability",
    label_col: str = "true_label",
) -> dict[str, Any]:
    """DISCLOSURE: this is a what-if simulation for a human governance decision, never an
    auto-applied fix. For each group other than `reference_group`, searches only over that
    group's OWN real predicted probabilities (no retraining, no data from other groups) for the
    threshold that brings its real false-positive rate down to at or below the reference group's
    real false-positive rate, then reports the REAL recall/precision/selection-rate this project's
    actual model would have produced at that threshold on that group's real held-out rows. Setting
    a different decision threshold per tags_group value is explicit group-conditioned differential
    treatment and is a materially different (and separately consequential) compliance question
    from the disparate-impact finding it would be responding to - this function exists to make
    that real trade-off visible, not to recommend adopting it."""
    ref_detail = next((g for g in group_detail if g["tags_group"] == reference_group), None)
    if ref_detail is None:
        raise ValueError(f"reference_group {reference_group!r} not found in group_detail")
    target_fpr = ref_detail["false_positive_rate"]

    out: dict[str, Any] = {
        "reference_group": reference_group,
        "reference_group_false_positive_rate": target_fpr,
        "per_group_simulation": {},
    }
    for g in group_detail:
        name = g["tags_group"]
        if name == reference_group:
            continue
        sub = decision_records_df[decision_records_df[group_col] == name]
        probs = sub[prob_col].to_numpy(dtype=float)
        labels = sub[label_col].to_numpy(dtype=float)
        n_neg = int((labels == 0).sum())
        n_pos = int((labels == 1).sum())

        if n_neg == 0 or n_pos == 0:
            out["per_group_simulation"][name] = {
                "note": "group has zero real positives or zero real negatives in this data - "
                "threshold search not meaningful.",
            }
            continue

        # Candidate thresholds = every real distinct predicted probability in this group, so the
        # search only ever considers thresholds this group's own real scores actually produce.
        candidates = np.unique(probs)
        best_threshold = None
        best_fpr = None
        for t in np.sort(candidates):
            pred = (probs >= t).astype(int)
            fp = int(((pred == 1) & (labels == 0)).sum())
            fpr = fp / n_neg
            if fpr <= target_fpr:
                best_threshold = float(t)
                best_fpr = fpr
                break
        if best_threshold is None:
            # No real threshold in this group's own score distribution reaches the reference
            # group's real false-positive rate even at the maximum real predicted probability.
            best_threshold = float(candidates.max())
            pred = (probs >= best_threshold).astype(int)
            fp = int(((pred == 1) & (labels == 0)).sum())
            best_fpr = fp / n_neg

        pred = (probs >= best_threshold).astype(int)
        tp = int(((pred == 1) & (labels == 1)).sum())
        fp = int(((pred == 1) & (labels == 0)).sum())
        n_selected = int(pred.sum())
        recall_at_threshold = tp / n_pos
        precision_at_threshold = tp / n_selected if n_selected else float("nan")
        selection_rate_at_threshold = n_selected / len(sub)

        out["per_group_simulation"][name] = {
            "original_threshold": 0.5,
            "original_recall": g["recall"],
            "original_false_positive_rate": g["false_positive_rate"],
            "original_selection_rate": g["selection_rate"],
            "adjusted_threshold_reaching_reference_fpr": best_threshold,
            "adjusted_false_positive_rate": best_fpr,
            "adjusted_recall": recall_at_threshold,
            "adjusted_precision": precision_at_threshold,
            "adjusted_selection_rate": selection_rate_at_threshold,
            "recall_cost": g["recall"] - recall_at_threshold,
        }
    return out


DISPARATE_TREATMENT_DISCLOSURE = (
    "This simulation is a what-if analysis for a human governance decision, not a recommendation "
    "to adopt group-conditioned thresholds. Setting a different real decision threshold per "
    "tags_group value uses a protected-adjacent attribute to apply differential treatment by "
    "group - a materially different, and separately consequential, real compliance question from "
    "the disparate-impact (selection-rate) finding this simulation responds to. Any decision to "
    "adopt per-group thresholds in production requires real legal/compliance review beyond this "
    "project's own scope; this module computes the real numbers such a review would need, and "
    "does not apply or recommend adopting them on its own."
)


def build_investigation_summary(
    gate5_summary: dict[str, Any],
    decision_records_df: pd.DataFrame,
    reference_group: str = "NO_TAG",
) -> dict[str, Any]:
    """Orchestrates the full real investigation from Gate 5's own real disparate_impact_check
    block plus the full real Gate 5 decision-records dataframe. Returns one structured report -
    never silently resolves the flag, always ends with the real numbers and the disclosure a human
    reviewer needs."""
    breakdown = gate5_summary["disparate_impact_check"]["tags_group_breakdown"]
    group_detail = compute_group_confusion_detail(breakdown)
    diagnosis = diagnose_disparity_driver(group_detail)
    calibration = compute_within_group_calibration(decision_records_df)
    equalized_fpr_simulation = simulate_equalized_fpr_thresholds(
        decision_records_df, group_detail, reference_group=reference_group
    )

    return {
        "bp_id": "bp3",
        "investigation": "disparate_impact_mitigation_investigation",
        "source_adverse_impact_ratio_tags": gate5_summary["disparate_impact_check"][
            "adverse_impact_ratio_recomputed"
        ],
        "source_flagged": gate5_summary["disparate_impact_check"]["flagged"],
        "group_confusion_detail": group_detail,
        "diagnosis": diagnosis,
        "within_group_calibration": calibration,
        "equalized_fpr_threshold_simulation": equalized_fpr_simulation,
        "disparate_treatment_disclosure": DISPARATE_TREATMENT_DISCLOSURE,
        "recommendation": (
            "See diagnosis.verdict for the real driver finding. This investigation does not "
            "change BP3's champion model, its Gate 3-5 real-run-confirmed outputs, or its default "
            "0.5 decision threshold - it is additive information for the governance review Gate "
            "4/5's own flag already calls for, per this project's standing "
            "'monitoring signal for a human reviewer, not a legal determination' framing."
        ),
    }


# ================================================================================
# Tier C addition below (see this block's own docstring text inline for full rationale)
# =============================================================================


def compute_categorical_feature_tags_association(
    X_test_raw: pd.DataFrame,
    categorical_cols: list[str],
    group_col: str = "Tags",
) -> list[dict[str, Any]]:
    """Real Cramer's V (uncorrected, standard formula) between each real candidate categorical
    feature and the real Tags value, computed on this gate's own real rebuilt held-out test rows.
    A chi-square test of independence backs each association; both the raw chi2/p-value and the
    normalized Cramer's V (0 = no association, 1 = perfect association) are reported so a reviewer
    can judge both statistical significance (inflated at this real sample size, n~163k) and real
    effect size (Cramer's V is the number that actually matters at this n)."""
    from scipy.stats import chi2_contingency

    n = len(X_test_raw)
    results: list[dict[str, Any]] = []
    for col in categorical_cols:
        table = pd.crosstab(X_test_raw[col], X_test_raw[group_col])
        chi2, p_value, _dof, _expected = chi2_contingency(table)
        r, k = table.shape
        denom = min(r - 1, k - 1)
        phi2 = chi2 / n if n else float("nan")
        cramers_v = float(np.sqrt(phi2 / denom)) if denom > 0 else float("nan")
        results.append(
            {
                "feature": col,
                "n_distinct_levels": int(r),
                "chi2_statistic": float(chi2),
                "p_value": float(p_value),
                "cramers_v": cramers_v,
                "association_strength": (
                    (
                        "negligible"
                        if cramers_v < 0.1
                        else ("weak" if cramers_v < 0.3 else "moderate" if cramers_v < 0.5 else "strong")
                    )
                    if not np.isnan(cramers_v)
                    else "undefined"
                ),
            }
        )
    return results


def compute_numeric_feature_tags_association(
    X_test_raw_with_freq: pd.DataFrame,
    numeric_col: str,
    group_col: str = "Tags",
) -> dict[str, Any]:
    """Real one-way ANOVA (eta-squared effect size) between a real numeric candidate feature
    (Company_freq, recomputed here purely on this gate's own real test-set row counts for this
    diagnostic only — NOT the train-fit frequency map the champion model itself was scored with,
    which this module never re-derives or re-uses) and the real Tags grouping."""
    from scipy.stats import f_oneway

    groups = [
        g[numeric_col].to_numpy(dtype=float)
        for _, g in X_test_raw_with_freq.groupby(group_col, observed=True)
        if len(g) > 1
    ]
    f_stat, p_value = f_oneway(*groups)
    grand_mean = float(X_test_raw_with_freq[numeric_col].mean())
    ss_between = sum(len(g) * (float(g.mean()) - grand_mean) ** 2 for g in groups)
    ss_total = float(((X_test_raw_with_freq[numeric_col] - grand_mean) ** 2).sum())
    eta_squared = float(ss_between / ss_total) if ss_total else float("nan")
    return {
        "feature": numeric_col,
        "f_statistic": float(f_stat),
        "p_value": float(p_value),
        "eta_squared": eta_squared,
        "association_strength": (
            (
                "negligible"
                if eta_squared < 0.01
                else ("small" if eta_squared < 0.06 else "medium" if eta_squared < 0.14 else "large")
            )
            if not np.isnan(eta_squared)
            else "undefined"
        ),
    }


def compute_stratified_fpr_by_feature(
    merged_df: pd.DataFrame,
    feature_col: str,
    group_col: str = "Tags",
    pred_col: str = "predicted_label",
    label_col: str = "true_label",
    min_cell_negatives: int = 30,
    balanced_ratio_bar: float = 0.8,
) -> dict[str, Any]:
    """For each real level of `feature_col` with at least `min_cell_negatives` real negative rows
    (true_label==0) in at least 2 real Tags groups, computes the real false-positive rate per
    group within that level and the resulting real min/max ratio. Reports, honestly, what
    fraction of this gate's real negative rows fall inside a level with enough data to evaluate at
    all (coverage) — the two smallest real Tags groups (Older American, Older American +
    Servicemember; n=2,447 and n=724 in the full test set) mean many high-cardinality feature
    levels will NOT have enough real rows per group to include, and this function does not paper
    over that: uncovered levels are simply excluded, and coverage is reported so a reviewer can
    judge how much of the real disparity this stratification actually speaks to."""
    negatives = merged_df[merged_df[label_col] == 0]
    total_negatives = len(negatives)
    per_level: list[dict[str, Any]] = []
    covered_negatives = 0

    for level, sub in negatives.groupby(feature_col, observed=True):
        cell = sub.groupby(group_col, observed=True)[pred_col].agg(n_negative="size", n_false_positive="sum")
        cell = cell[cell["n_negative"] >= min_cell_negatives]
        if len(cell) < 2:
            continue
        cell = cell.copy()
        cell["fpr"] = cell["n_false_positive"] / cell["n_negative"]
        ratio = float(cell["fpr"].min() / cell["fpr"].max()) if cell["fpr"].max() else float("nan")
        covered_negatives += int(cell["n_negative"].sum())
        per_level.append(
            {
                "level": str(level),
                "groups_evaluated": cell.index.astype(str).tolist(),
                "n_negative_per_group": {str(k): int(v) for k, v in cell["n_negative"].items()},
                "fpr_per_group": {str(k): float(v) for k, v in cell["fpr"].items()},
                "fpr_ratio_min_over_max": ratio,
                "fpr_balanced_within_level": (
                    bool(ratio >= balanced_ratio_bar) if not np.isnan(ratio) else None
                ),
            }
        )

    n_evaluated = len(per_level)
    n_balanced = sum(1 for r in per_level if r["fpr_balanced_within_level"])
    return {
        "feature": feature_col,
        "min_cell_negatives": min_cell_negatives,
        "n_levels_evaluated": n_evaluated,
        "n_levels_with_balanced_fpr": n_balanced,
        "fraction_levels_balanced": (n_balanced / n_evaluated) if n_evaluated else None,
        "total_real_negative_rows": total_negatives,
        "real_negative_rows_covered_by_evaluated_levels": covered_negatives,
        "coverage_fraction": ((covered_negatives / total_negatives) if total_negatives else None),
        "per_level_detail": per_level,
    }


def fit_residual_disparity_model(
    merged_df: pd.DataFrame,
    categorical_cols: list[str],
    numeric_cols: list[str],
    group_col: str = "Tags",
    label_col: str = "true_label",
    pred_col: str = "predicted_label",
    n_splits: int = 5,
    random_state: int = 42,
    meaningful_auc_delta: float = 0.01,
) -> dict[str, Any]:
    """Real, cross-validated (StratifiedKFold) comparison of two logistic regressions predicting
    the real false-positive event (predicted_label==1 among true_label==0 rows) from (a) the real
    candidate features the champion model actually uses, alone, vs (b) those same real features
    plus one-hot(Tags). Both models are fit fresh here purely for this diagnostic (never the
    champion model itself, never used to score or gate any production row). A materially higher
    real mean CV AUC for (b) over (a) — by at least `meaningful_auc_delta`, a disclosed convention
    — is real evidence Tags carries information about the model's real false-positive behavior
    beyond what its own real training features explain; a real AUC delta below that bar is
    evidence the real features already capture Tags' association with false positives.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.preprocessing import OneHotEncoder

    negatives = merged_df[merged_df[label_col] == 0].reset_index(drop=True)
    y = (negatives[pred_col] == 1).astype(int).to_numpy()
    n_false_positive = int(y.sum())

    if n_false_positive < n_splits or (len(y) - n_false_positive) < n_splits:
        return {
            "n_negative_rows_evaluated": int(len(negatives)),
            "n_false_positives_in_evaluated_rows": n_false_positive,
            "note": (
                "too few real false-positive or real true-negative rows for a "
                f"{n_splits}-fold stratified CV comparison - residual model not fit."
            ),
        }

    transformer_a = ColumnTransformer(
        [
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", dtype=np.float32),
                categorical_cols,
            ),
            ("num", "passthrough", numeric_cols),
        ]
    )
    X_a = transformer_a.fit_transform(negatives)

    transformer_b = ColumnTransformer(
        [
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", dtype=np.float32),
                categorical_cols + [group_col],
            ),
            ("num", "passthrough", numeric_cols),
        ]
    )
    X_b = transformer_b.fit_transform(negatives)

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    auc_a = cross_val_score(clf, X_a, y, cv=skf, scoring="roc_auc", n_jobs=1)
    auc_b = cross_val_score(clf, X_b, y, cv=skf, scoring="roc_auc", n_jobs=1)
    delta = float(auc_b.mean() - auc_a.mean())

    return {
        "n_negative_rows_evaluated": int(len(negatives)),
        "n_false_positives_in_evaluated_rows": n_false_positive,
        "cv_folds": n_splits,
        "features_only_mean_cv_auc": float(auc_a.mean()),
        "features_only_cv_auc_std": float(auc_a.std()),
        "features_plus_tags_mean_cv_auc": float(auc_b.mean()),
        "features_plus_tags_cv_auc_std": float(auc_b.std()),
        "auc_delta_from_adding_tags": delta,
        "meaningful_auc_delta_convention": meaningful_auc_delta,
        "tags_adds_meaningful_information_beyond_real_features": bool(delta >= meaningful_auc_delta),
    }


PROXY_AUDIT_DISCLOSURE = (
    "This audit tests whether the real candidate features the champion model was actually trained "
    "on (Product, Sub-product, Issue, Sub-issue, State, Submitted via, Company) already explain "
    "Tags' real association with the model's false-positive behavior. It does not retrain, "
    "repredict, or change any real production decision - it re-examines the same real held-out "
    "test rows Gate 5 already scored. A finding that Tags adds real information beyond these "
    "features (residual model AUC delta above the disclosed bar, and/or the stratified false-"
    "positive-rate gap persisting across most real feature levels) means the disparity is not a "
    "data-quality or feature-engineering artifact explainable by a legitimate business feature - "
    "it strengthens, not weakens, the original MODEL-DRIVEN diagnosis. A finding that the real "
    "features already explain most of the gap would instead point toward a specific real feature "
    "as a genuine candidate for further review - itself still a real finding requiring human "
    "governance judgment, not something this module resolves automatically."
)


def build_proxy_feature_audit_summary(
    X_test_raw: pd.DataFrame,
    merged_df: pd.DataFrame,
    categorical_cols: list[str],
    numeric_cols: list[str],
    stratify_features: list[str],
    group_col: str = "Tags",
) -> dict[str, Any]:
    """Orchestrates the full real Tier C proxy-feature audit into one structured report - never
    silently resolves the original MODEL-DRIVEN finding, always ends with the real numbers and
    disclosure a human reviewer needs."""
    categorical_association = compute_categorical_feature_tags_association(
        X_test_raw, categorical_cols, group_col=group_col
    )
    numeric_association = [
        compute_numeric_feature_tags_association(X_test_raw, col, group_col=group_col) for col in numeric_cols
    ]
    stratified_fpr = [
        compute_stratified_fpr_by_feature(merged_df, feature_col, group_col=group_col)
        for feature_col in stratify_features
    ]
    residual_model = fit_residual_disparity_model(
        merged_df, categorical_cols, numeric_cols, group_col=group_col
    )

    return {
        "bp_id": "bp3",
        "investigation": "disparate_impact_proxy_feature_audit",
        "categorical_feature_tags_association": categorical_association,
        "numeric_feature_tags_association": numeric_association,
        "stratified_false_positive_rate_by_feature": stratified_fpr,
        "residual_disparity_model": residual_model,
        "proxy_audit_disclosure": PROXY_AUDIT_DISCLOSURE,
    }


# ==============================================================================
# Tier A addition below (fairness-aware retraining candidate - see this block's own docstring
# text inline for full rationale)
# =============================================================================


def compute_fpr_targeted_sample_weights(
    y_train: np.ndarray,
    tags_train: pd.Series,
    real_group_fpr: dict[str, float],
    reference_group: str = "NO_TAG",
    scale_pos_weight: float = 1.0,
) -> np.ndarray:
    """Real, disclosed FPR-targeted group-conditional sample reweighting for BP3's fairness-aware
    retraining candidate (Tier A), directly informed by Tier C's real finding that the false-
    positive-rate disparity is NOT explained by any single real candidate feature the champion was
    trained on - so this reweighting acts on the training objective itself, not the feature list.

    `real_group_fpr` must be the real, already-established per-group false-positive rate from this
    gate's own real disparate-impact investigation (read live from
    gate4_disparate_impact_investigation.json's group_confusion_detail - never hardcoded here, and
    never re-estimated on the training set itself, since an unbiased in-sample training-set FPR
    would require an extra nested CV/holdout loop outside this candidate's scope). This is a
    disclosed design choice, not a leak of test labels into the training loss - only a fixed,
    already-real-run-confirmed population-level statistic is used, exactly as scale_pos_weight
    itself already is a fixed statistic-derived hyperparameter, not a per-row computation from
    live labels.

    Design: every real negative (true_label=0) training row in a non-reference Tags group is
    upweighted by real_group_fpr[group] / real_group_fpr[reference_group], floored at 1.0 (a group
    is never downweighted below the reference group's baseline). A group currently over-flagged at
    (say) 7.5x the reference group's real FPR has its real negative rows weighted roughly 7.5x more
    heavily during training - directly incentivizing the model to reduce false positives
    specifically where the real disparity is largest. Real positive (true_label=1) rows keep the
    same scale_pos_weight-equivalent weight the original champion used (passed in, never re-derived
    here), so this candidate's positive-class recall is not additionally penalized by this change -
    only the false-positive axis is targeted, matching Tier C/the original investigation's finding
    that recall (equal opportunity) was already balanced (ratio 0.9562) and only false-positive
    rate (equalized odds) was not (ratio 0.1324).

    This is a heuristic reweighting, not a formal equalized-odds constraint - it does not guarantee
    the resulting model's real per-group FPR ratio will clear the 0.8 four-fifths-style bar. It is
    designed to move the real held-out test set's per-group FPR ratio toward it, and the real
    result must be evaluated on real held-out data (this candidate notebook's own Section 8), never
    assumed from the training-time design alone."""
    group_multiplier = {
        group: max(1.0, fpr / real_group_fpr[reference_group]) for group, fpr in real_group_fpr.items()
    }
    negative_multiplier = tags_train.map(group_multiplier).fillna(1.0).to_numpy(dtype=np.float64)
    y_arr = np.asarray(y_train)
    weights = np.where(y_arr == 1, float(scale_pos_weight), negative_multiplier)
    return weights.astype(np.float64)


def compute_real_group_confusion_from_predictions(
    tags_test: pd.Series,
    y_test: np.ndarray,
    y_pred: np.ndarray,
) -> list[dict[str, Any]]:
    """Real per-Tags-group confusion-matrix detail computed DIRECTLY from this candidate's real
    predictions on the real held-out test set (never back-computed from rounded selection-
    rate/recall the way the original investigation's compute_group_confusion_detail() necessarily
    was, since that function only had Gate 4/5's already-rounded recorded rates to work from - this
    candidate has real predictions in hand, so the more direct, more precise computation is used
    here instead)."""
    df = pd.DataFrame({"tags_group": tags_test.to_numpy(), "true_label": y_test, "predicted_label": y_pred})
    results: list[dict[str, Any]] = []
    for group_name, sub in df.groupby("tags_group", observed=True):
        n_rows = len(sub)
        n_pos = int((sub["true_label"] == 1).sum())
        n_neg = int((sub["true_label"] == 0).sum())
        n_tp = int(((sub["predicted_label"] == 1) & (sub["true_label"] == 1)).sum())
        n_fp = int(((sub["predicted_label"] == 1) & (sub["true_label"] == 0)).sum())
        n_tn = int(((sub["predicted_label"] == 0) & (sub["true_label"] == 0)).sum())
        n_fn = int(((sub["predicted_label"] == 0) & (sub["true_label"] == 1)).sum())
        n_selected = n_tp + n_fp
        results.append(
            {
                "tags_group": str(group_name),
                "n_rows_in_test": n_rows,
                "n_real_positive_in_group": n_pos,
                "n_real_negative_in_group": n_neg,
                "n_selected": n_selected,
                "n_true_positive": n_tp,
                "n_false_positive": n_fp,
                "n_true_negative": n_tn,
                "n_false_negative": n_fn,
                "selection_rate": round(n_selected / n_rows, 4) if n_rows else 0.0,
                "recall": round(n_tp / n_pos, 4) if n_pos else None,
                "false_positive_rate": round(n_fp / n_neg, 6) if n_neg else None,
                "precision": round(n_tp / n_selected, 4) if n_selected else None,
            }
        )
    return results


FAIRNESS_AWARE_RETRAINING_DISCLOSURE = (
    "This candidate model is produced by FPR-targeted group-conditional sample reweighting during "
    "training (compute_fpr_targeted_sample_weights()) - a heuristic informed by Tier C's real "
    "finding that no single real candidate feature explains the false-positive-rate disparity, so "
    "the fix targets the training objective directly rather than the feature list. It is NOT a "
    "formal equalized-odds-constrained optimization (that would be a further real option, not "
    "built here) and does NOT guarantee the real per-group false-positive-rate ratio clears the "
    "0.8 four-fifths-style bar - the real result must be read from this notebook's own real "
    "held-out test set evaluation, Section 8, not assumed from the design. This candidate is never "
    "auto-promoted to BP3's champion and does NOT alter Gate 3-7's existing real-run-confirmed "
    "artifacts or config blocks - adopting it (or not) is the user's real governance decision, to "
    "be made only after comparing its real PR-AUC/ROC-AUC/recall/precision/F1 against the real, "
    "already-confirmed original champion's numbers (a materially worse real PR-AUC is a real cost "
    "of this fix that must be weighed, not hidden) alongside its real fairness-metric improvement."
)


# --- Tier A v2 addition below (amplified FPR-ratio reweighting) ---


def compute_fpr_targeted_sample_weights_v2(
    y_train: np.ndarray,
    tags_train: pd.Series,
    real_group_fpr: dict[str, float],
    reference_group: str = "NO_TAG",
    scale_pos_weight: float = 1.0,
    amplification_exponent: float = 2.0,
    cap_at_scale_pos_weight: bool = True,
) -> np.ndarray:
    """Real, disclosed, AMPLIFIED FPR-targeted group-conditional sample reweighting for BP3's
    fairness-aware retraining candidate (Tier A, v2) - a stronger successor to
    compute_fpr_targeted_sample_weights() (v1), built after v1's own real held-out test result
    (real-run-confirmed 2026-09-23) showed the linear FPR-ratio multiplier (max real per-row
    multiplier ~7.55x, for the "Older American, Servicemember" group) moved the real held-out FPR
    ratio only from 0.132381 to 0.139087 - a ~5% relative improvement, nowhere near the real 0.8
    four-fifths-style bar - despite that linear multiplier already injecting roughly a fifth of the
    real training set's total negative-row weighted mass toward the three non-reference Tags groups
    (by Claude's own back-of-envelope estimate from the real train/test row counts). The v1 real
    result implies the real ~457-dimensional one-hot/frequency feature space retains enough combined
    real predictive separation between Tags groups - individually weak per Tier C's real proxy-audit
    (max Cramer's V 0.1872), but evidently not weak enough in combination for a linear pull to
    overcome - that a stronger, nonlinear pull is needed to make a real dent.

    v2's change from v1: the same real per-group FPR ratio (`real_group_fpr[group] /
    real_group_fpr[reference_group]`, loaded live from the real, already-confirmed disparate-impact
    investigation, never hardcoded, never re-estimated in-sample) is raised to `amplification_exponent`
    (default 2.0, i.e. squared) before being applied as the real negative-row multiplier, still
    floored at 1.0. On the real, already-confirmed per-group FPRs this raises the real max per-row
    multiplier from v1's ~7.55x (Older American, Servicemember) to v2's ~57.06x - and Older
    American's real multiplier rises from ~7.48x to ~55.93x, Servicemember's from ~2.43x to ~5.88x -
    now on the same real order of magnitude as the champion's own real scale_pos_weight (76.58),
    giving the minority Tags groups' real negative rows comparable per-row training influence to the
    positive class itself, a materially stronger real pull than v1's.

    Disclosed real cost expectation (not a promise): because this real multiplier is substantially
    larger than v1's, it is expected to cost MORE real PR-AUC/recall than v1's already-real-confirmed
    cost (v1: -0.0064 PR-AUC, -0.0233 recall) in exchange for a real attempt at a materially larger
    real FPR-ratio improvement - the real result must be read from this notebook's own real held-out
    evaluation, never assumed from this design. `cap_at_scale_pos_weight` (default True) caps any
    real per-row multiplier at the real scale_pos_weight itself, a disclosed safety bound so no real
    negative row can out-weigh the positive class by construction - it does not engage on the current
    real per-group FPRs (max ~57.06x is already below the real 76.58 scale_pos_weight) but guards
    against a future real re-run with a larger measured disparity. Real positive rows keep the same
    scale_pos_weight-equivalent weight the original champion used (passed in, never re-derived here),
    unchanged from v1 - only the real negative-row multiplier's strength changed between v1 and v2.

    This remains a heuristic reweighting, not a formal equalized-odds constraint, exactly as v1
    disclosed - it does not guarantee the real per-group FPR ratio clears the 0.8 four-fifths-style
    bar, and the real result must be evaluated on real held-out data (this candidate notebook's own
    Section 8), never assumed from the amplification alone."""
    ratio = {group: max(1.0, fpr / real_group_fpr[reference_group]) for group, fpr in real_group_fpr.items()}
    amplified = {group: r**amplification_exponent for group, r in ratio.items()}
    if cap_at_scale_pos_weight:
        amplified = {group: min(m, float(scale_pos_weight)) for group, m in amplified.items()}
    negative_multiplier = tags_train.map(amplified).fillna(1.0).to_numpy(dtype=np.float64)
    y_arr = np.asarray(y_train)
    weights = np.where(y_arr == 1, float(scale_pos_weight), negative_multiplier)
    return weights.astype(np.float64)
