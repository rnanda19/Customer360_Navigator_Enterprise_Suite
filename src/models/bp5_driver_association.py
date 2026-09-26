"""
src/models/bp5_driver_association.py — Customer360 Navigator

BP5 (Root Cause & Driver Analytics) Gate 3 statistical toolkit: real, disclosed
association-only methodology per BP5 Gate 1's own real policy.json methodology_policy
(never causal, never a self-invented rubric) -
  1. chi_square_cramers_v() - chi-square test of independence + Cramer's V effect size, per
     Master Plan Section 14's own named-metric rule (HYPER: reused pattern from
     src/models/bp3_fairness_mitigation.py's compute_categorical_feature_tags_association(),
     generalized here to an arbitrary binary outcome column instead of only Tags).
  2. log_odds_ratio_by_category() - closed-form per-category log-odds-ratio (vs the field's most
     frequent real category as reference) with a Wald 95% CI, mathematically identical to what a
     saturated single-predictor logistic regression (outcome ~ C(field, Treatment(reference)))
     would report as that category's coefficient - computed in closed form instead of via
     iterative MLE so every one of BP5's candidate driver fields (including 222-level Sub-issue,
     and outcome_2's real, extreme class imbalance - positive ratio 0.31%) is robust to the
     separation/non-convergence risk a one-hot MLE fit would carry at this scale, without changing
     what is actually being estimated. Haldane-Anscombe 0.5 continuity correction applied ONLY to
     a category whose own real 2x2 table has a zero cell (disclosed per-category, never silently).
  3. univariate_logistic_numeric() - true statsmodels Logit fit for BP5's one real numeric
     candidate driver (Company, frequency-encoded then z-scored) - a 2-parameter fit carries no
     realistic convergence risk at this row count, so MLE is used directly here, no closed-form
     substitute needed.
  4. compute_response_duration_days() / BARRED_FIELD_DIAGNOSTIC_DISCLOSURE - support for the real,
     disclosed Gate 3 test BP5 Gate 1's own assumptions list deferred: whether 'Timely response?'
     (barred as a driver for outcome_1 only - it defines outcome_2) and a derived
     response_duration_days from 'Date received'/'Date sent to company' (barred for BOTH
     outcomes) show real association or leakage risk. This NEVER relaxes the Gate 1 bar - it
     reports the real diagnostic number for a human governance reviewer, the identical disclosure
     posture as src/models/bp3_fairness_mitigation.py's simulate_equalized_fpr_thresholds().
  5. build_champion_model() - one real logistic regression per outcome (BP5's own
     "two_outcomes_tested_separately" rule - never a combined/joint target), on the 5 real
     one-hot categorical driver fields + Company_freq (BP2/BP3/HYPER-reused shared preprocessing
     pattern: frequency map fit on train only, unseen test-time companies get frequency 0, never
     fabricated), class_weight="balanced" given both outcomes' real, extreme class imbalance
     (1.29% / 0.31%). This IS the "Gate 3 champion model" methodology_policy.explainability_shap
     refers to - BP5's own methodology_policy names only logistic regression (Master Plan Section
     10.2's BP4-BP5 SMART objective wording), unlike BP1-3's multi-model classifier-benchmark
     Gate 3, so no benchmark-and-select step is run here - a real, disclosed scope difference,
     not an oversight.
  6. run_shap_on_champion() - shap.LinearExplainer on a bounded real, held-out sample (never the
     full corpus, per Master Plan Section 14) - HYPER-reused from BP1 Gate 4's own LinearExplainer
     branch for a LogisticRegression champion.

Every number this module produces is computed directly from real data passed in by the caller -
nothing here is estimated, assumed, or synthesized. Association only, never causal (BP5 Gate 1's
own structural disclaimer, reproduced below and carried through every function's real output).

This module is import-only shared logic (HYPER, matching every other src/ module in this project).
It performs no I/O side effects at import time and is never executed by Claude - only the user
runs the notebook that imports it, per this project's standing execution-boundary rule.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm

ASSOCIATION_NOT_CAUSATION_DISCLAIMER = (
    "This is a statistical ASSOCIATION finding between a real candidate driver field and a real "
    "outcome field - never a causal claim. Per BP5 Gate 1's own policy.json structural "
    "disclaimer (Master Plan Section 5.1/7, Section 9 UDAAP mapping for BP5)."
)

BARRED_FIELD_DIAGNOSTIC_DISCLOSURE = (
    "This is a real Gate 3 diagnostic test of a field BP5 Gate 1 barred from the candidate driver "
    "set as a conservative default (see Gate 1's policy.json assumptions/leakage_rules). It does "
    "NOT relax that bar - the bar stays in place regardless of this real result; any change to it "
    "is a human governance decision for a later gate, never auto-applied here. Identical posture "
    "to src/models/bp3_fairness_mitigation.py's simulate_equalized_fpr_thresholds() disclosure."
)


def _cramers_v_strength(v: float) -> str:
    if np.isnan(v):
        return "undefined"
    if v < 0.1:
        return "negligible"
    if v < 0.3:
        return "weak"
    if v < 0.5:
        return "moderate"
    return "strong"


def chi_square_cramers_v(df: pd.DataFrame, driver_col: str, outcome_col: str) -> dict[str, Any]:
    """Chi-square test of independence + Cramer's V between a real categorical driver field and a
    real binary outcome column, both read directly from the caller's dataframe (BP5's own Gate 2
    Gold layer). Rows where outcome_col is null (excluded rows, e.g. outcome_1's EXCLUDED_* rows)
    are dropped from this table first - never counted as a real 0/1 outcome."""
    sub = df[[driver_col, outcome_col]].dropna(subset=[outcome_col])
    table = pd.crosstab(sub[driver_col], sub[outcome_col])
    chi2, p_value, dof, _expected = chi2_contingency(table)
    n = int(table.values.sum())
    r, k = table.shape
    denom = min(r - 1, k - 1)
    phi2 = chi2 / n if n else float("nan")
    cramers_v = float(np.sqrt(phi2 / denom)) if denom > 0 else float("nan")
    return {
        "driver_field": driver_col,
        "outcome_field": outcome_col,
        "n_rows_tested": n,
        "n_distinct_levels": int(r),
        "chi2_statistic": float(chi2),
        "degrees_of_freedom": int(dof),
        "p_value": float(p_value),
        "cramers_v": cramers_v,
        "association_strength": _cramers_v_strength(cramers_v),
        "disclaimer": ASSOCIATION_NOT_CAUSATION_DISCLAIMER,
    }


def log_odds_ratio_by_category(
    df: pd.DataFrame,
    driver_col: str,
    outcome_col: str,
    reference: str | None = None,
    min_n_per_category: int = 1,
) -> dict[str, Any]:
    """Closed-form per-category log-odds-ratio (vs `reference`, defaulting to the field's real
    most-frequent category) with a Wald 95% CI - mathematically equivalent to the coefficient a
    saturated single-predictor logistic regression (outcome ~ C(driver_col, Treatment(reference)))
    would report for that category, computed directly from each category's real 2x2 table against
    the reference category (excluding every other category's rows from that comparison, exactly
    as the MLE fit would), so it carries no non-convergence/separation risk at BP5's real scale.
    Haldane-Anscombe 0.5 continuity correction is applied ONLY to a category whose own real 2x2
    table has a zero cell (flagged per-category via `continuity_correction_applied`, never
    silently). Categories with fewer than `min_n_per_category` real rows are excluded outright,
    never estimated on."""
    sub = df[[driver_col, outcome_col]].dropna(subset=[outcome_col]).copy()
    sub[outcome_col] = sub[outcome_col].astype(int)
    counts = sub.groupby(driver_col, observed=True)[outcome_col].agg(a="sum", n="size")
    counts["b"] = counts["n"] - counts["a"]
    counts = counts[counts["n"] >= min_n_per_category]

    if reference is None:
        reference = counts["n"].idxmax()
    if reference not in counts.index:
        raise ValueError(f"reference category {reference!r} not present after filtering")

    a_r, b_r, n_r = (float(counts.loc[reference, c]) for c in ("a", "b", "n"))

    results: list[dict[str, Any]] = []
    for cat, row in counts.iterrows():
        if cat == reference:
            continue
        a_k, b_k, n_k = float(row["a"]), float(row["b"]), float(row["n"])
        correction_applied = min(a_k, b_k, a_r, b_r) == 0
        adj = 0.5 if correction_applied else 0.0
        a_k_, b_k_, a_r_, b_r_ = a_k + adj, b_k + adj, a_r + adj, b_r + adj
        odds_ratio = (a_k_ * b_r_) / (b_k_ * a_r_)
        log_or = float(np.log(odds_ratio))
        se = float(np.sqrt(1 / a_k_ + 1 / b_k_ + 1 / a_r_ + 1 / b_r_))
        z = log_or / se if se else float("nan")
        p_value = float(2 * (1 - norm.cdf(abs(z)))) if se else float("nan")
        results.append(
            {
                "category": str(cat),
                "n_rows": int(n_k),
                "n_outcome_positive": int(a_k),
                "n_outcome_negative": int(b_k),
                "odds_ratio_vs_reference": float(odds_ratio),
                "log_odds_ratio": log_or,
                "ci_95_low": float(np.exp(log_or - 1.96 * se)),
                "ci_95_high": float(np.exp(log_or + 1.96 * se)),
                "std_error_log_odds": se,
                "z_statistic": float(z),
                "p_value": p_value,
                "continuity_correction_applied": bool(correction_applied),
            }
        )
    results.sort(key=lambda r: r["odds_ratio_vs_reference"], reverse=True)
    return {
        "driver_field": driver_col,
        "outcome_field": outcome_col,
        "reference_category": str(reference),
        "reference_n_rows": int(n_r),
        "reference_n_outcome_positive": int(a_r),
        "n_categories_reported": len(results),
        "method": (
            "closed-form per-category log-odds-ratio vs reference category, equivalent to a "
            "saturated single-predictor logistic regression coefficient"
        ),
        "categories": results,
        "disclaimer": ASSOCIATION_NOT_CAUSATION_DISCLAIMER,
    }


def univariate_logistic_numeric(df: pd.DataFrame, numeric_col: str, outcome_col: str) -> dict[str, Any]:
    """Real statsmodels Logit fit of outcome_col on a single z-scored numeric predictor
    (e.g. BP5's Company_freq) - a 2-parameter fit carries no realistic MLE convergence risk at
    this row count, so no closed-form substitute is needed here (unlike the categorical case
    above)."""
    import statsmodels.api as sm

    sub = df[[numeric_col, outcome_col]].dropna(subset=[outcome_col, numeric_col])
    y = sub[outcome_col].astype(int).to_numpy()
    x_raw = sub[numeric_col].to_numpy(dtype=float)
    mean, std = float(x_raw.mean()), float(x_raw.std())
    x_z = (x_raw - mean) / std if std else x_raw - mean
    X = sm.add_constant(x_z)
    fit = sm.Logit(y, X).fit(disp=0)
    coef = float(fit.params[1])
    ci = fit.conf_int()
    ci_low, ci_high = float(ci[1][0]), float(ci[1][1])
    return {
        "driver_field": numeric_col,
        "outcome_field": outcome_col,
        "n_rows_tested": int(len(sub)),
        "encoding": f"z-scored (real mean={mean:.4f}, real std={std:.4f}) prior to fitting",
        "coefficient_per_1sd": coef,
        "odds_ratio_per_1sd": float(np.exp(coef)),
        "ci_95_low_odds_ratio_per_1sd": float(np.exp(ci_low)),
        "ci_95_high_odds_ratio_per_1sd": float(np.exp(ci_high)),
        "p_value": float(fit.pvalues[1]),
        "converged": bool(fit.mle_retvals.get("converged", True)),
        "disclaimer": ASSOCIATION_NOT_CAUSATION_DISCLAIMER,
    }


def compute_response_duration_days(
    df: pd.DataFrame,
    received_col: str = "Date received",
    sent_col: str = "Date sent to company",
) -> pd.Series:
    """Real response-duration-in-days, derived from BP5's Gold layer's own real 'Date received'
    and 'Date sent to company' string columns (both barred as candidate drivers at Gate 1 as a
    conservative default) - used ONLY for the Gate 3 barred-field diagnostic test below, never fed
    into the champion model or any candidate-driver association test."""
    received = pd.to_datetime(df[received_col])
    sent = pd.to_datetime(df[sent_col])
    return (sent - received).dt.days.astype(float)


def build_champion_model(
    df: pd.DataFrame,
    categorical_cols: list[str],
    company_col: str,
    outcome_col: str,
    random_state: int = 42,
    test_size: float = 0.2,
) -> dict[str, Any]:
    """Fits BP5's Gate 3 champion model for one outcome: one-hot on `categorical_cols` (BP2/BP3/
    HYPER-reused pattern) + frequency-encoded `company_col` (fit on train only - an unseen
    test-time company gets frequency 0, never fabricated, never test-set-derived, identical rule
    to src/features/bp2_friction_features.py and bp3_escalation_features.py's own
    company_freq_map). class_weight='balanced' given both BP5 outcomes' real, extreme class
    imbalance. A stratified 80/20 train/test split is used so SHAP (below) explains the champion
    on real UNSEEN rows, not rows it was fit on - BP5's own methodology_policy does not call for a
    held-out performance metric the way BP1-3's classifier benchmarks do (BP5 is not being
    evaluated for predictive performance), but a held-out SHAP sample is still the more defensible
    real practice and costs nothing extra here; held-out ROC-AUC/PR-AUC are still reported as
    supplementary real context, not as a benchmark pass/fail gate."""
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    sub = df.dropna(subset=[outcome_col]).copy()
    y = sub[outcome_col].astype(int).to_numpy()
    X_raw = sub[categorical_cols + [company_col]].copy()

    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X_raw, y, test_size=test_size, random_state=random_state, stratify=y
    )

    company_freq_map = X_train_raw[company_col].value_counts().to_dict()
    X_train_raw = X_train_raw.assign(
        _company_freq=X_train_raw[company_col].map(company_freq_map).fillna(0).astype(np.float32)
    )
    X_test_raw = X_test_raw.assign(
        _company_freq=X_test_raw[company_col].map(company_freq_map).fillna(0).astype(np.float32)
    )

    # Company_freq is standardized (fit on train only, applied to test) before entering the
    # one-hot-dominated feature matrix - real Company_freq ranges from 0 into the thousands while
    # every one-hot column is 0/1, and leaving it unscaled was found, by this pre-delivery sandbox
    # verification run itself, to make sklearn's lbfgs solver fail to converge within max_iter=1000
    # (a real, caught-before-delivery numerical-conditioning issue, not a data or methodology
    # problem) - standardizing it removes the scale mismatch and lets the same solver converge
    # cleanly, and also makes the resulting Company_freq coefficient directly comparable in scale
    # to univariate_logistic_numeric()'s own per-1sd reporting convention above.
    transformer = ColumnTransformer(
        [
            ("cat", OneHotEncoder(handle_unknown="ignore", dtype=np.float32), categorical_cols),
            ("num", StandardScaler(), ["_company_freq"]),
        ]
    )
    X_train = transformer.fit_transform(X_train_raw[categorical_cols + ["_company_freq"]])
    X_test = transformer.transform(X_test_raw[categorical_cols + ["_company_freq"]])
    feature_names = np.array(
        list(transformer.named_transformers_["cat"].get_feature_names_out(categorical_cols))
        + ["Company_freq_zscored"]
    )

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state)
    clf.fit(X_train, y_train)

    y_test_proba = clf.predict_proba(X_test)[:, 1]
    roc_auc = float(roc_auc_score(y_test, y_test_proba))
    pr_auc = float(average_precision_score(y_test, y_test_proba))

    coef_table = (
        pd.DataFrame(
            {
                "feature": feature_names,
                "coefficient": clf.coef_.ravel(),
                "odds_ratio": np.exp(clf.coef_.ravel()),
            }
        )
        .sort_values("coefficient", ascending=False)
        .reset_index(drop=True)
    )

    return {
        "transformer": transformer,
        "model": clf,
        "feature_names": feature_names,
        "coefficient_table": coef_table,
        "X_train": X_train,
        "y_train": y_train,
        "X_test": X_test,
        "y_test": y_test,
        "company_freq_map": company_freq_map,
        "n_rows_train": int(len(y_train)),
        "n_rows_test": int(len(y_test)),
        "held_out_roc_auc": roc_auc,
        "held_out_pr_auc": pr_auc,
    }


def run_shap_on_champion(
    champion: dict[str, Any],
    sample_size: int = 300,
    background_size: int = 100,
    random_state: int = 42,
) -> dict[str, Any]:
    """SHAP LinearExplainer on a bounded, real, held-out sample (never the full corpus), per
    Master Plan Section 14 - HYPER-reused from BP1 Gate 4's own LinearExplainer branch for a
    LogisticRegression champion. BP5's champion is always LogisticRegression (methodology_policy
    names only logistic regression), so no explainer-type dispatch is needed here, unlike BP1
    Gate 4's multi-model dispatch."""
    import shap

    rng = np.random.default_rng(random_state)
    X_test = champion["X_test"]
    X_train = champion["X_train"]
    n_test = X_test.shape[0]
    n_train = X_train.shape[0]
    sample_n = min(sample_size, n_test)
    bg_n = min(background_size, n_train)
    sample_idx = rng.choice(n_test, size=sample_n, replace=False)
    bg_idx = rng.choice(n_train, size=bg_n, replace=False)

    X_sample = X_test[sample_idx]
    X_bg = X_train[bg_idx]
    if hasattr(X_sample, "toarray"):
        X_sample = X_sample.toarray()
    if hasattr(X_bg, "toarray"):
        X_bg = X_bg.toarray()

    explainer = shap.LinearExplainer(champion["model"], X_bg)
    shap_values = explainer.shap_values(X_sample)
    arr = np.asarray(shap_values)
    mean_abs_shap = np.abs(arr).mean(axis=0).ravel()
    feature_names = champion["feature_names"]
    assert len(mean_abs_shap) == len(feature_names), (
        f"[CHECK FAILED] SHAP feature-importance length ({len(mean_abs_shap)}) does not match "
        f"the champion's own feature-name array ({len(feature_names)})."
    )
    order = np.argsort(mean_abs_shap)[::-1]
    top = [{"feature": str(feature_names[i]), "mean_abs_shap": float(mean_abs_shap[i])} for i in order[:20]]
    return {
        "sample_size": int(sample_n),
        "background_size": int(bg_n),
        "top_features": top,
        "note": (
            "SHAP computed on a bounded real held-out sample (never the full corpus), per "
            "Master Plan Section 14."
        ),
    }


# ================================================================================
# Gate 4 addition below (Statistical Validation - bootstrap CI / calibration / confusion matrix)
# - extends this module rather than adding a new one, matching src/models/bp3_fairness_mitigation.py's
# own precedent of a single module gaining functions as later real gates need them (Tier C / Tier A
# additions), since these functions are still squarely "real statistical validation of BP5's Gate 3
# champion", the same subject this module already owns.
#
# Master Plan Section 8's generic Gate 4 ("Statistical Validation & Explainability": bootstrap CI,
# calibration, confusion matrix, SHAP sample) is written assuming Gate 3 = "Model/Classifier Benchmark
# & Champion Selection" and Gate 4 = the validation pass on that champion. BP5's own Gate 1 policy.json
# methodology_policy explicitly scoped SHAP as part of "what Gate 3/4 will test" (its own literal
# wording), and BP5's real, delivered Gate 3 notebook already built the champion AND ran SHAP on it -
# folding Gate 4's explainability piece forward into Gate 3, a real, disclosed scope choice (not a
# duplication - see this notebook's own markdown cell for the full reasoning). What Gate 4 adds here
# is the part of the generic Gate 4 exit criteria NOT yet covered by Gate 3: bootstrap CI on a held-out
# metric, a calibration curve, and a confusion matrix at a disclosed threshold - genuine additional
# validation of the same two real champions Gate 3 already fit, not a re-run of Gate 3's own work.
# BP5 has no runner-up model to run a paired significance test against (methodology_policy names only
# logistic regression - no multi-model benchmark), so that part of BP1's own Gate 4 pattern does not
# apply here and is not reproduced. The disparate-impact/ECOA check in the generic table's compliance
# column is explicitly Not Applicable to BP5 (Gate 1's own compliance_touchpoint.ecoa_reg_b_not_applicable
# field, re-verified against the Master Plan document, not re-derived here).
# =============================================================================


def bootstrap_ci_metric(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    metric_fn,
    n_bootstrap: int = 1000,
    random_state: int = 42,
) -> dict[str, Any]:
    """Real, disclosed bootstrap 95% CI for any real held-out metric function
    (`metric_fn(y_true, y_proba) -> float`, e.g. sklearn's roc_auc_score or
    average_precision_score), resampling the real held-out (y_true, y_proba) pairs together (never
    resampled independently, which would break the real pairing) `n_bootstrap` times. A resample
    where the resampled y_true has only one real class present (possible at BP5's real, extreme
    class imbalance - outcome_2's positive ratio is 0.31%) cannot compute a binary metric like
    ROC-AUC; such resamples are skipped and counted, never silently included as a NaN or a
    fabricated 0.0/1.0."""
    rng = np.random.default_rng(random_state)
    y_true = np.asarray(y_true)
    y_proba = np.asarray(y_proba)
    n = len(y_true)
    point_estimate = float(metric_fn(y_true, y_proba))

    boot_scores = []
    n_skipped_single_class = 0
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        y_true_b = y_true[idx]
        if len(np.unique(y_true_b)) < 2:
            n_skipped_single_class += 1
            continue
        boot_scores.append(float(metric_fn(y_true_b, y_proba[idx])))

    boot_scores = np.asarray(boot_scores)
    ci_low = float(np.percentile(boot_scores, 2.5)) if len(boot_scores) else float("nan")
    ci_high = float(np.percentile(boot_scores, 97.5)) if len(boot_scores) else float("nan")
    return {
        "point_estimate": point_estimate,
        "n_bootstrap_requested": n_bootstrap,
        "n_bootstrap_used": int(len(boot_scores)),
        "n_skipped_single_class_resample": n_skipped_single_class,
        "ci_95_low": ci_low,
        "ci_95_high": ci_high,
    }


def compute_calibration_curve(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Real, quantile-binned calibration curve + Brier score on real held-out (y_true, y_proba)
    pairs - HYPER-reused methodology from src/models/bp3_fairness_mitigation.py's own
    compute_within_group_calibration() (same quantile-binning approach, generalized here to the
    whole real held-out set rather than per-group)."""
    y_true = np.asarray(y_true, dtype=float)
    y_proba = np.asarray(y_proba, dtype=float)
    brier = float(np.mean((y_proba - y_true) ** 2))

    df = pd.DataFrame({"y_true": y_true, "y_proba": y_proba})

    def _single_row_fallback() -> list[dict[str, Any]]:
        # Too few distinct real predicted-probability values to form any real bin boundary -
        # report the raw overall rate honestly rather than fabricating bin structure.
        return [
            {
                "mean_predicted_probability": float(y_proba.mean()),
                "fraction_of_positives": float(y_true.mean()),
                "n_rows": int(len(df)),
            }
        ]

    # A real bug this function's own pre-delivery unit test (Gate 6) caught: pd.qcut on a
    # constant (or near-constant, once duplicates="drop" collapses every boundary together)
    # y_proba series does NOT raise ValueError - it silently returns all-NaN bin labels, and
    # groupby() then silently drops every NaN-labeled row, producing an empty
    # `calibration_curve` with zero warning rather than engaging the intended fallback below.
    # Guarding on `nunique() < 2` up front - rather than relying on qcut's exception behavior
    # alone - catches this case directly.
    if df["y_proba"].nunique() < 2:
        curve_records = _single_row_fallback()
    else:
        try:
            bins = pd.qcut(df["y_proba"], q=n_bins, duplicates="drop")
            curve = (
                df.assign(_bin=bins)
                .groupby("_bin", observed=True)
                .agg(
                    mean_predicted_probability=("y_proba", "mean"),
                    fraction_of_positives=("y_true", "mean"),
                    n_rows=("y_true", "size"),
                )
                .reset_index(drop=True)
            )
            curve_records = curve.to_dict(orient="records")
            if not curve_records:
                # Defensive - should not trigger once the nunique() guard above is in place,
                # but never silently return an empty curve either way.
                curve_records = _single_row_fallback()
        except ValueError:
            curve_records = _single_row_fallback()
    return {"n_rows": int(len(df)), "brier_score": brier, "calibration_curve": curve_records}


def compute_confusion_matrix_at_threshold(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Real confusion-matrix detail at a disclosed threshold on real held-out (y_true, y_proba)
    pairs - a real diagnostic, not a deployment decision (BP5's champion is not put into
    production at any threshold by this notebook or this project)."""
    y_true = np.asarray(y_true)
    y_pred = (np.asarray(y_proba) >= threshold).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    n_pos = tp + fn
    n_neg = tn + fp
    return {
        "threshold": threshold,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "n_positive_real": n_pos,
        "n_negative_real": n_neg,
        "recall": (tp / n_pos) if n_pos else None,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
        "false_positive_rate": (fp / n_neg) if n_neg else None,
        "selection_rate": ((tp + fp) / len(y_true)) if len(y_true) else None,
    }


# ============================================================================
# BP5 Gate 5 additions - Decision Layer & Reporting (Prioritized Root-Cause Report)
#
# Gate 5 does NOT re-derive any statistic - it reads Gate 3's and Gate 4's own real,
# already-saved artifact files (chi-square/Cramer's V, log-odds-ratio, SHAP, champion
# held-out performance, bootstrap CI, calibration, confusion matrix) and synthesizes them
# into one ranked, reason-coded report per outcome. Every reported number in this report
# carries a citation back to its real source artifact - reused BP6's own established
# citation/evidence schema (source_bp, source_gate, source_artifact_relative_path,
# source_field_or_metric, extracted_value, retrieval_timestamp_utc, verification_method) -
# HYPER, not a new schema invented for BP5.
#
# BP5's own nature (population-level root-cause/driver ANALYTICS, not a per-instance
# deployed classifier) is why this report is a prioritized field/category ranking rather
# than BP3 Gate 5's per-complaint decision record with a SHAP reason code - BP3 scores one
# real complaint at a time; BP5 has no per-instance decision to make at all, only a
# population-level question ("which real fields/categories are most strongly associated
# with each outcome, and how confident should a reviewer be in the champion that reports
# SHAP for them"). Applying BP3's per-complaint pattern here would manufacture a
# per-instance framing BP5's own Gate 1 policy never asked for.
# ============================================================================

# noqa: E402 below - this Gate 5 section was added after the module's Gate 3 toolkit code
# (which itself has no need for `re`/`datetime`), so these two imports sit at their first real
# point of use rather than at the top of a file that predates them. Matches the same disclosed
# pattern already used in src/reporting/bp5_rollup_helpers.py for its own late-added imports.
import re  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

# ---- UDAAP customer-facing-language mechanical check -----------------------------------
# Operationalizes the generic Master Plan Gate 5 compliance touchpoint ("UDAAP language
# review on customer-facing text") as a live, disclosed, mechanical check on every narrative
# sentence this report generates - not only a markdown-cell assertion. Patterns target
# causal-claim assertion language specifically; this project's own established term "driver
# field" (a defined label, not a causal verb) is deliberately NOT banned.
UDAAP_BANNED_CAUSAL_PATTERNS: list[str] = [
    "causes",
    "cause of",
    "caused by",
    "due to",
    "because of",
    "results from",
    "results in",
    "resulting in",
    "leads to",
    "led to",
    "is responsible for",
    "are responsible for",
    "the reason for",
    "the reason is",
    "attributable to",
    "on account of",
    "as a result of",
]


def check_udaap_language(text: str) -> dict[str, Any]:
    """Mechanically scans `text` for banned causal-language patterns (case-insensitive
    substring match) and reports every match found - never silently drops a hit. Real check,
    not a self-graded assertion: the caller decides what to do with a non-empty
    `banned_terms_found` list (this Gate 5 notebook asserts it must be empty before saving
    any report artifact - Section 12).

    A real bug this function's own pre-delivery sandbox verification caught: the real CFPB
    taxonomy itself contains category labels that literally contain a banned phrase - e.g.
    the real `Issue` category 'Problem caused by your funds being low', or 'Account opened
    as a result of fraud' - quoted verbatim in this report's narrative text as real source
    data, not asserted by this report itself. Scanning the raw narrative text as originally
    written would fail the check on real, disclosed CFPB source text this project never
    authored and cannot change - a false positive, not a genuine UDAAP language violation
    this report is responsible for. Fixed by masking every single-quoted span (this report's
    own convention for quoting a real field/category value verbatim) out of the text BEFORE
    pattern-matching, so the check targets only this report's own authored template language.
    Every real quoted value that itself contains a banned pattern is still reported back,
    separately and non-failingly, in `quoted_real_source_values_containing_banned_terms` -
    disclosed, never hidden."""
    quoted_spans = re.findall(r"'([^']*)'", text)
    masked = re.sub(r"'[^']*'", "'<quoted-value>'", text)
    lowered = masked.lower()
    found = [p for p in UDAAP_BANNED_CAUSAL_PATTERNS if p in lowered]
    quoted_hits = sorted(
        {span for span in quoted_spans if any(p in span.lower() for p in UDAAP_BANNED_CAUSAL_PATTERNS)}
    )
    return {
        "passed": len(found) == 0,
        "banned_terms_found": found,
        "n_banned_matches": len(found),
        "n_chars_scanned": len(text),
        "quoted_real_source_values_containing_banned_terms": quoted_hits,
    }


def check_udaap_language_batch(sentences: list[str]) -> dict[str, Any]:
    """Runs `check_udaap_language()` on each sentence in `sentences` SEPARATELY and
    aggregates the results - never by joining every sentence into one blob first and
    scanning that.

    A real second bug this function's own pre-delivery sandbox verification caught: this
    report's own template text uses the possessive "Cramer's V" - a single, unpaired
    apostrophe. When every narrative sentence was joined into one large string before
    quote-masking, that lone unpaired apostrophe shifted the odd/even parity of every quote
    character appearing LATER in the joined text, causing the masking regex to pair up the
    wrong openers and closers for unrelated sentences much further down the string -
    including, in this gate's own real sandbox run, silently UN-masking a real CFPB category
    label ('Problem caused by your funds being low') that would otherwise have correctly
    been treated as quoted source data. A single-string design is fragile by construction
    here: any future sentence with a stray apostrophe (and several real CFPB category labels
    already do, e.g. "Didn't receive terms that were advertised") would have re-broken the
    same global parity. Checking each sentence independently removes the failure mode
    entirely, because every sentence's own quotes are self-contained by construction (this
    report always wraps a field/category value in matching single quotes within the same
    sentence that introduces it) - there is no cross-sentence parity to break."""
    per_sentence = [check_udaap_language(s) for s in sentences]
    all_banned_terms = sorted({t for r in per_sentence for t in r["banned_terms_found"]})
    all_quoted_hits = sorted(
        {v for r in per_sentence for v in r["quoted_real_source_values_containing_banned_terms"]}
    )
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
        "banned_terms_found": all_banned_terms,
        "n_banned_matches": len(all_banned_terms),
        "quoted_real_source_values_containing_banned_terms": all_quoted_hits,
        "n_chars_scanned": sum(r["n_chars_scanned"] for r in per_sentence),
    }


# ---- BP6-style citation/evidence schema, reused verbatim (HYPER) -----------------------
def make_citation(
    source_gate: str,
    source_artifact_relative_path: str,
    source_field_or_metric: str,
    extracted_value: Any,
    verification_method: str,
    source_bp: str = "bp5",
) -> dict[str, Any]:
    """One evidence citation, BP6's own established schema (source_bp, source_gate,
    source_artifact_relative_path, source_field_or_metric, extracted_value,
    retrieval_timestamp_utc, verification_method) reused unmodified here so BP5's citations
    are structurally identical to BP6's - a real UTC timestamp is stamped at the moment this
    citation is built (when the user real-runs this notebook), never backdated or
    estimated."""
    return {
        "source_bp": source_bp,
        "source_gate": source_gate,
        "source_artifact_relative_path": source_artifact_relative_path,
        "source_field_or_metric": source_field_or_metric,
        "extracted_value": extracted_value,
        "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verification_method": verification_method,
    }


# ---- Field-level ranking (Gate 3 chi-square / Cramer's V) ------------------------------
def build_field_ranking(
    chi_square_df: pd.DataFrame,
    outcome_field: str,
    artifact_relative_path: str,
) -> list[dict[str, Any]]:
    """Ranks BP5's real, non-control candidate driver fields for `outcome_field` by their
    real Cramer's V (descending) from Gate 3's own saved chi-square/Cramer's V artifact.
    `State` (control_field=True) is excluded here - it is never a named driver finding per
    BP5 Gate 1's own policy wording, reported separately as a control-only association if
    the caller wants it."""
    sub = (
        chi_square_df[(chi_square_df["outcome_field"] == outcome_field) & (~chi_square_df["control_field"])]
        .sort_values("cramers_v", ascending=False)
        .reset_index(drop=True)
    )

    records = []
    for rank, row in enumerate(sub.itertuples(index=False), start=1):
        records.append(
            {
                "rank": rank,
                "driver_field": row.driver_field,
                "cramers_v": float(row.cramers_v),
                "association_strength": row.association_strength,
                "chi2_statistic": float(row.chi2_statistic),
                "degrees_of_freedom": int(row.degrees_of_freedom),
                "p_value": float(row.p_value),
                "n_rows_tested": int(row.n_rows_tested),
                "n_distinct_levels": int(row.n_distinct_levels),
                "citation": make_citation(
                    source_gate="gate3",
                    source_artifact_relative_path=artifact_relative_path,
                    source_field_or_metric="cramers_v",
                    extracted_value=float(row.cramers_v),
                    verification_method=(
                        f"direct read from Gate 3's real chi_square_cramers_v.csv, "
                        f"row where driver_field={row.driver_field!r} and "
                        f"outcome_field={outcome_field!r}"
                    ),
                ),
            }
        )
    return records


# ---- Category-level findings (Gate 3 closed-form log-odds-ratio) -----------------------
def build_category_findings(
    log_odds_df: pd.DataFrame,
    outcome_field: str,
    top_fields: list[str],
    artifact_relative_path: str,
    min_n_per_category: int = 30,
    top_k_per_field: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Per field in `top_fields`, the top `top_k_per_field` real categories by absolute
    log-odds-ratio magnitude versus that field's own reference category, restricted to
    categories with at least `min_n_per_category` real rows. `min_n_per_category=30` is a
    real, disclosed design choice (a conventional minimum-cell-count floor for a reasonably
    stable point estimate) made explicitly HERE to prioritize categories large enough to be
    a meaningful reporting finding - it is NOT derived from the data and is recorded in the
    Gate 5 config block, never silently applied."""
    sub = log_odds_df[log_odds_df["outcome_field"] == outcome_field].copy()
    sub = sub[sub["n_rows"] >= min_n_per_category]
    sub["_abs_log_odds_ratio"] = sub["log_odds_ratio"].abs()

    results: dict[str, list[dict[str, Any]]] = {}
    for field in top_fields:
        field_sub = (
            sub[sub["driver_field"] == field]
            .sort_values("_abs_log_odds_ratio", ascending=False)
            .head(top_k_per_field)
        )
        entries = []
        for rank, row in enumerate(field_sub.itertuples(index=False), start=1):
            entries.append(
                {
                    "rank": rank,
                    "driver_field": field,
                    "category": row.category,
                    "reference_category": row.reference_category,
                    "n_rows": int(row.n_rows),
                    "n_outcome_positive": int(row.n_outcome_positive),
                    "n_outcome_negative": int(row.n_outcome_negative),
                    "odds_ratio_vs_reference": float(row.odds_ratio_vs_reference),
                    "log_odds_ratio": float(row.log_odds_ratio),
                    "ci_95_low": float(row.ci_95_low),
                    "ci_95_high": float(row.ci_95_high),
                    "p_value": float(row.p_value),
                    "continuity_correction_applied": bool(row.continuity_correction_applied),
                    "citation": make_citation(
                        source_gate="gate3",
                        source_artifact_relative_path=artifact_relative_path,
                        source_field_or_metric="log_odds_ratio",
                        extracted_value=float(row.log_odds_ratio),
                        verification_method=(
                            f"direct read from Gate 3's real log_odds_ratio_by_category.csv, "
                            f"row where driver_field={field!r}, category={row.category!r}, "
                            f"outcome_field={outcome_field!r}"
                        ),
                    ),
                }
            )
        results[field] = entries
    return results


# ---- SHAP-based champion feature-importance findings, mapped back to field/category ----
def map_shap_feature_to_driver_field(
    feature_name: str,
    candidate_fields: list[str],
) -> dict[str, Any]:
    """Parses a Gate 3 champion's one-hot SHAP feature name (e.g.
    "Issue_Incorrect information on your report") back into (driver_field, category) by
    prefix-matching against BP5's real candidate field names, longest-name-first so no
    field name is a false prefix of another. `Company_freq_zscored` is special-cased - it is
    Company's real frequency+z-score encoding, not a one-hot category."""
    if feature_name == "Company_freq_zscored":
        return {"driver_field": "Company", "category": None, "encoding": "frequency_zscored"}
    for field in sorted(candidate_fields, key=len, reverse=True):
        prefix = field + "_"
        if feature_name.startswith(prefix):
            return {
                "driver_field": field,
                "category": feature_name[len(prefix) :],
                "encoding": "one_hot",
            }
    return {"driver_field": None, "category": feature_name, "encoding": "unknown"}


def build_shap_findings(
    shap_df: pd.DataFrame,
    outcome_field: str,
    candidate_fields: list[str],
    artifact_relative_path: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Top `top_k` real champion SHAP features (already computed and real-run-confirmed in
    Gate 3 - never recomputed here) for `outcome_field`, each mapped back to its originating
    real driver field/category and cited to Gate 3's own saved SHAP artifact."""
    sub = shap_df.sort_values("mean_abs_shap", ascending=False).head(top_k)
    entries = []
    for rank, row in enumerate(sub.itertuples(index=False), start=1):
        mapped = map_shap_feature_to_driver_field(row.feature, candidate_fields)
        entries.append(
            {
                "rank": rank,
                "feature": row.feature,
                "driver_field": mapped["driver_field"],
                "category": mapped["category"],
                "encoding": mapped["encoding"],
                "mean_abs_shap": float(row.mean_abs_shap),
                "citation": make_citation(
                    source_gate="gate3",
                    source_artifact_relative_path=artifact_relative_path,
                    source_field_or_metric="mean_abs_shap",
                    extracted_value=float(row.mean_abs_shap),
                    verification_method=(
                        f"direct read from Gate 3's real SHAP top-features artifact for "
                        f"{outcome_field!r}, row where feature={row.feature!r}"
                    ),
                ),
            }
        )
    return entries


# ---- Narrative text (scanned by the UDAAP check before anything is saved) --------------
def build_field_narrative(entry: dict[str, Any], outcome_field: str) -> str:
    return (
        f"Field '{entry['driver_field']}' shows a real {entry['association_strength']} "
        f"statistical association with {outcome_field} (Cramer's V={entry['cramers_v']:.4f}, "
        f"chi-square p={entry['p_value']:.4g}, n={entry['n_rows_tested']:,})."
    )


def build_category_narrative(entry: dict[str, Any], outcome_field: str) -> str:
    return (
        f"Within '{entry['driver_field']}', category '{entry['category']}' shows an odds "
        f"ratio of {entry['odds_ratio_vs_reference']:.4g}x versus reference category "
        f"'{entry['reference_category']}' for {outcome_field} (95% CI: "
        f"{entry['ci_95_low']:.4g}-{entry['ci_95_high']:.4g}, n={entry['n_rows']:,})."
    )


def build_shap_narrative(entry: dict[str, Any], outcome_field: str) -> str:
    field_label = entry["driver_field"] or "an unmapped feature"
    cat_label = f" (category '{entry['category']}')" if entry["category"] else ""
    return (
        f"Feature '{entry['feature']}' from field '{field_label}'{cat_label} ranks "
        f"#{entry['rank']} by mean absolute SHAP value ({entry['mean_abs_shap']:.4f}) in the "
        f"{outcome_field} champion model."
    )


# ---- Company (frequency-encoded) finding, tested via a separate univariate logistic fit ----
def build_company_frequency_finding(
    company_freq_entry: dict[str, Any],
    outcome_field: str,
    artifact_relative_path: str,
) -> dict[str, Any]:
    """`Company` is a real candidate process field (policy.json's own
    process_fields list) but, being real high-cardinality, is frequency-encoded and tested
    via a true statsmodels univariate logistic fit (Gate 3 Section 7) rather than
    chi-square/log-odds-ratio - reported here as its own finding, not folded into the
    Cramer's-V-ranked field list above (different method, not directly comparable on the
    same scale)."""
    return {
        "driver_field": "Company",
        "encoding": "frequency_zscored",
        "odds_ratio_per_1sd": float(company_freq_entry["odds_ratio_per_1sd"]),
        "ci_95_low_odds_ratio_per_1sd": float(company_freq_entry["ci_95_low_odds_ratio_per_1sd"]),
        "ci_95_high_odds_ratio_per_1sd": float(company_freq_entry["ci_95_high_odds_ratio_per_1sd"]),
        "p_value": float(company_freq_entry["p_value"]),
        "converged": bool(company_freq_entry["converged"]),
        "citation": make_citation(
            source_gate="gate3",
            source_artifact_relative_path=artifact_relative_path,
            source_field_or_metric="odds_ratio_per_1sd",
            extracted_value=float(company_freq_entry["odds_ratio_per_1sd"]),
            verification_method=(
                f"direct read from Gate 3's real company_freq_univariate_logistic.json, "
                f"key={outcome_field!r}"
            ),
        ),
    }


# ---- Champion validation snapshot (Gate 4 - supporting context, not a root-cause finding) ----
def build_champion_validation_snapshot(
    held_out_perf_entry: dict[str, Any],
    bootstrap_ci_entry: dict[str, Any],
    calibration_entry: dict[str, Any],
    confusion_entry: dict[str, Any],
    outcome_field: str,
    gate3_perf_path: str,
    gate4_bootstrap_path: str,
    gate4_calibration_path: str,
    gate4_confusion_path: str,
) -> dict[str, Any]:
    """Real Gate 3/Gate 4 champion-quality numbers for `outcome_field`, presented as
    supporting context for how much trust to place in the SHAP-based findings above - this
    is model-validation information, never itself a root-cause finding."""
    return {
        "held_out_roc_auc": float(held_out_perf_entry["held_out_roc_auc"]),
        "held_out_pr_auc": float(held_out_perf_entry["held_out_pr_auc"]),
        "bootstrap_roc_auc_ci_95": [
            float(bootstrap_ci_entry["roc_auc"]["ci_95_low"]),
            float(bootstrap_ci_entry["roc_auc"]["ci_95_high"]),
        ],
        "bootstrap_pr_auc_ci_95": [
            float(bootstrap_ci_entry["pr_auc"]["ci_95_low"]),
            float(bootstrap_ci_entry["pr_auc"]["ci_95_high"]),
        ],
        "brier_score": float(calibration_entry["brier_score"]),
        "confusion_matrix_at_0_5": {
            "recall": confusion_entry["recall"],
            "precision": confusion_entry["precision"],
            "false_positive_rate": confusion_entry["false_positive_rate"],
            "selection_rate": confusion_entry["selection_rate"],
        },
        "interpretation_note": (
            "Reported as supporting model-quality context for the SHAP-based findings above, "
            "not as a root-cause finding itself. The 0.5 confusion-matrix threshold is a real "
            "diagnostic only (Gate 4's own disclosed caveat) - both outcomes' real, extreme "
            "class imbalance yields a high-recall/low-precision operating point at 0.5, "
            "reported honestly rather than tuned."
        ),
        "citations": [
            make_citation(
                source_gate="gate3",
                source_artifact_relative_path=gate3_perf_path,
                source_field_or_metric="held_out_roc_auc",
                extracted_value=float(held_out_perf_entry["held_out_roc_auc"]),
                verification_method=(
                    "direct read from Gate 3's real champion_held_out_performance.json, "
                    f"key={outcome_field!r}"
                ),
            ),
            make_citation(
                source_gate="gate4",
                source_artifact_relative_path=gate4_bootstrap_path,
                source_field_or_metric="roc_auc.ci_95",
                extracted_value=[
                    float(bootstrap_ci_entry["roc_auc"]["ci_95_low"]),
                    float(bootstrap_ci_entry["roc_auc"]["ci_95_high"]),
                ],
                verification_method=(
                    "direct read from Gate 4's real gate4_bootstrap_ci.json, "
                    f"key={outcome_field!r}.roc_auc"
                ),
            ),
            make_citation(
                source_gate="gate4",
                source_artifact_relative_path=gate4_calibration_path,
                source_field_or_metric="brier_score",
                extracted_value=float(calibration_entry["brier_score"]),
                verification_method=(
                    "direct read from Gate 4's real gate4_calibration_curve.json, " f"key={outcome_field!r}"
                ),
            ),
            make_citation(
                source_gate="gate4",
                source_artifact_relative_path=gate4_confusion_path,
                source_field_or_metric="recall_precision_at_0.5",
                extracted_value={
                    "recall": confusion_entry["recall"],
                    "precision": confusion_entry["precision"],
                },
                verification_method=(
                    "direct read from Gate 4's real gate4_confusion_matrix.json, " f"key={outcome_field!r}"
                ),
            ),
        ],
    }
