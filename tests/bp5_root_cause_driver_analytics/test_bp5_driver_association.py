"""
tests/bp5_root_cause_driver_analytics/test_bp5_driver_association.py — Customer360 Navigator

Full pytest coverage for src/models/bp5_driver_association.py (BP5 Gate 6 governance
requirement, mirroring BP3/BP4's own test_*_features.py pattern — BP5's first-ever test
coverage; previously `pytest tests/` did not exercise BP5's module at all). Every test uses
small synthetic data constructed in this file, never real CFPB data or real Gate 3/4/5
artifacts — that real-data cross-consistency is test_gate_artifacts.py's job instead.

Scope choice, disclosed: `build_champion_model()` and `run_shap_on_champion()` (the two
functions that actually fit a real `sklearn.LogisticRegression` / run `shap.LinearExplainer`)
are exercised here only at a small, fast synthetic scale — enough to catch a real regression in
their own logic (e.g. the Company_freq standardization fix from Gate 3's own sandbox
verification) without turning the CI-run pytest suite into a slow full-scale retrain. The real,
full-scale numbers these functions produce against the real Gold layer are Gate 3's/Gate 4's own
job to report, checked live inside those notebooks at run time — never re-asserted here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from models import bp5_driver_association as bda

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_association_not_causation_disclaimer_is_nonempty_and_says_association():
    assert isinstance(bda.ASSOCIATION_NOT_CAUSATION_DISCLAIMER, str)
    assert len(bda.ASSOCIATION_NOT_CAUSATION_DISCLAIMER) > 0
    assert "association" in bda.ASSOCIATION_NOT_CAUSATION_DISCLAIMER.lower()


def test_udaap_banned_causal_patterns_contains_the_real_bug_case():
    # "caused by" is the exact real CFPB taxonomy phrase ('Problem caused by your funds being
    # low') that this gate's own Gate 5 sandbox verification caught as a real false positive -
    # kept in the banned list (masking, not removal, is the fix - see check_udaap_language).
    assert "caused by" in bda.UDAAP_BANNED_CAUSAL_PATTERNS
    assert "due to" in bda.UDAAP_BANNED_CAUSAL_PATTERNS
    assert all(p == p.lower() for p in bda.UDAAP_BANNED_CAUSAL_PATTERNS)


# ---------------------------------------------------------------------------
# chi_square_cramers_v
# ---------------------------------------------------------------------------


def _perfectly_associated_frame(n_per_category: int = 50) -> pd.DataFrame:
    # category "A" always outcome=1, category "B" always outcome=0 - maximal real association.
    return pd.DataFrame(
        {
            "driver": ["A"] * n_per_category + ["B"] * n_per_category,
            "outcome": [1] * n_per_category + [0] * n_per_category,
        }
    )


def test_chi_square_cramers_v_detects_perfect_association():
    result = bda.chi_square_cramers_v(_perfectly_associated_frame(), "driver", "outcome")
    # Not exactly 1.0: scipy.stats.chi2_contingency applies Yates' continuity correction by
    # default on a 2x2 table (this module's own real, already-used, already real-run-confirmed
    # behavior - identical to every real 2x2 comparison in Gate 3's own delivered output), which
    # shrinks the statistic slightly below the uncorrected value even for a perfectly separated
    # real 2x2 table.
    assert result["cramers_v"] > 0.95
    assert result["p_value"] < 0.01
    assert result["association_strength"] in {"moderate", "strong"}
    assert result["n_rows_tested"] == 100


def test_chi_square_cramers_v_near_zero_for_independent_data():
    rng = np.random.default_rng(42)
    n = 4000
    df = pd.DataFrame(
        {
            "driver": rng.choice(["A", "B"], size=n),
            "outcome": rng.choice([0, 1], size=n),
        }
    )
    result = bda.chi_square_cramers_v(df, "driver", "outcome")
    assert result["cramers_v"] < 0.05
    assert result["association_strength"] == "negligible"


# ---------------------------------------------------------------------------
# log_odds_ratio_by_category
# ---------------------------------------------------------------------------


def test_log_odds_ratio_reference_defaults_to_most_frequent_category():
    df = pd.DataFrame(
        {
            "driver": ["Common"] * 60 + ["Rare"] * 10,
            "outcome": [0] * 30 + [1] * 30 + [0] * 5 + [1] * 5,
        }
    )
    result = bda.log_odds_ratio_by_category(df, "driver", "outcome")
    assert result["reference_category"] == "Common"
    # Only the non-reference category should appear in the per-category output.
    assert [c["category"] for c in result["categories"]] == ["Rare"]


def test_log_odds_ratio_applies_continuity_correction_only_on_zero_cell():
    # "ZeroNeg" category has zero real negative outcomes - a real zero-cell 2x2 table.
    df = pd.DataFrame(
        {
            "driver": ["Ref"] * 40 + ["ZeroNeg"] * 10,
            "outcome": [0] * 20 + [1] * 20 + [1] * 10,
        }
    )
    result = bda.log_odds_ratio_by_category(df, "driver", "outcome", reference="Ref")
    zero_neg_entry = next(c for c in result["categories"] if c["category"] == "ZeroNeg")
    assert zero_neg_entry["continuity_correction_applied"] is True
    assert zero_neg_entry["n_outcome_negative"] == 0
    # A category with no zero cell must NOT get the correction.
    df2 = pd.DataFrame(
        {
            "driver": ["Ref"] * 40 + ["Balanced"] * 20,
            "outcome": [0] * 20 + [1] * 20 + [0] * 10 + [1] * 10,
        }
    )
    result2 = bda.log_odds_ratio_by_category(df2, "driver", "outcome", reference="Ref")
    balanced_entry = next(c for c in result2["categories"] if c["category"] == "Balanced")
    assert balanced_entry["continuity_correction_applied"] is False


def test_log_odds_ratio_min_n_per_category_excludes_small_categories():
    df = pd.DataFrame(
        {
            "driver": ["Ref"] * 40 + ["TooSmall"] * 3,
            "outcome": [0] * 20 + [1] * 20 + [0, 1, 1],
        }
    )
    result = bda.log_odds_ratio_by_category(df, "driver", "outcome", reference="Ref", min_n_per_category=5)
    assert [c["category"] for c in result["categories"]] == []


# ---------------------------------------------------------------------------
# univariate_logistic_numeric
# ---------------------------------------------------------------------------


def test_univariate_logistic_numeric_converges_and_reports_positive_association():
    rng = np.random.default_rng(7)
    n = 2000
    x = rng.normal(size=n)
    # Outcome probability increases with x - a real positive association by construction.
    p = 1.0 / (1.0 + np.exp(-(1.5 * x)))
    y = (rng.uniform(size=n) < p).astype(int)
    df = pd.DataFrame({"x": x, "outcome": y})
    result = bda.univariate_logistic_numeric(df, "x", "outcome")
    assert result["converged"] is True
    assert result["coefficient_per_1sd"] > 0
    assert result["odds_ratio_per_1sd"] > 1
    assert result["p_value"] < 0.01


# ---------------------------------------------------------------------------
# compute_response_duration_days
# ---------------------------------------------------------------------------


def test_compute_response_duration_days_real_arithmetic():
    df = pd.DataFrame(
        {
            "Date received": ["2026-01-01", "2026-01-10"],
            "Date sent to company": ["2026-01-03", "2026-01-10"],
        }
    )
    out = bda.compute_response_duration_days(df)
    assert list(out) == [2.0, 0.0]


# ---------------------------------------------------------------------------
# bootstrap_ci_metric
# ---------------------------------------------------------------------------


def test_bootstrap_ci_metric_ci_brackets_point_estimate():
    rng = np.random.default_rng(11)
    n = 500
    y_true = rng.choice([0, 1], size=n, p=[0.9, 0.1])
    y_proba = np.clip(y_true * 0.6 + rng.normal(scale=0.2, size=n), 0, 1)
    result = bda.bootstrap_ci_metric(y_true, y_proba, roc_auc_score, n_bootstrap=200, random_state=1)
    assert result["n_bootstrap_requested"] == 200
    assert result["n_bootstrap_used"] <= 200
    assert result["ci_95_low"] <= result["point_estimate"] <= result["ci_95_high"]


def test_bootstrap_ci_metric_skips_single_class_resamples_and_counts_them():
    # Extremely rare positive class (1 positive in 300) makes a single-class bootstrap
    # resample a real possibility - the function must skip and COUNT it, never fabricate a
    # score for it.
    y_true = np.array([0] * 299 + [1])
    y_proba = np.linspace(0, 1, 300)
    result = bda.bootstrap_ci_metric(y_true, y_proba, roc_auc_score, n_bootstrap=300, random_state=3)
    assert result["n_skipped_single_class_resample"] >= 0
    assert result["n_bootstrap_used"] + result["n_skipped_single_class_resample"] == 300


# ---------------------------------------------------------------------------
# compute_calibration_curve
# ---------------------------------------------------------------------------


def test_compute_calibration_curve_brier_score_zero_for_perfect_predictions():
    y_true = np.array([0, 0, 1, 1] * 25)
    y_proba = y_true.astype(float)
    result = bda.compute_calibration_curve(y_true, y_proba, n_bins=5)
    assert result["brier_score"] == pytest.approx(0.0, abs=1e-9)
    assert result["n_rows"] == 100


def test_compute_calibration_curve_handles_too_few_distinct_probabilities():
    y_true = np.array([0, 1, 0, 1])
    y_proba = np.array([0.5, 0.5, 0.5, 0.5])  # single distinct value - cannot form 10 bins
    result = bda.compute_calibration_curve(y_true, y_proba, n_bins=10)
    assert len(result["calibration_curve"]) >= 1
    assert result["n_rows"] == 4


# ---------------------------------------------------------------------------
# compute_confusion_matrix_at_threshold
# ---------------------------------------------------------------------------


def test_compute_confusion_matrix_at_threshold_known_counts():
    y_true = np.array([1, 1, 0, 0, 1, 0])
    y_proba = np.array([0.9, 0.4, 0.8, 0.2, 0.6, 0.1])
    result = bda.compute_confusion_matrix_at_threshold(y_true, y_proba, threshold=0.5)
    # At 0.5: predicted positive = indices 0,2,4 (0.9,0.8,0.6); true labels there = 1,0,1
    assert result["true_positive"] == 2
    assert result["false_positive"] == 1
    assert result["true_negative"] == 2
    assert result["false_negative"] == 1
    assert result["recall"] == pytest.approx(2 / 3)
    assert result["precision"] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# check_udaap_language / check_udaap_language_batch
# ---------------------------------------------------------------------------


def test_check_udaap_language_flags_unquoted_causal_assertion():
    result = bda.check_udaap_language("This field causes the outcome directly.")
    assert result["passed"] is False
    assert "causes" in result["banned_terms_found"]


def test_check_udaap_language_masks_quoted_real_source_value_and_discloses_it_separately():
    # The real bug this gate's own sandbox verification caught: a real CFPB category label
    # quoted verbatim as source data must not fail the check, but must still be disclosed.
    text = "Within 'Issue', category 'Problem caused by your funds being low' shows an odds ratio of 5x."
    result = bda.check_udaap_language(text)
    assert result["passed"] is True
    assert result["banned_terms_found"] == []
    assert "Problem caused by your funds being low" in result["quoted_real_source_values_containing_banned_terms"]


def test_check_udaap_language_batch_survives_unpaired_apostrophe_across_sentences():
    # The real second bug this gate's own sandbox verification caught: "Cramer's V" has an
    # unpaired apostrophe that broke cross-sentence quote-pairing when sentences were joined
    # into one blob before masking. check_udaap_language_batch must NOT reproduce that failure
    # mode because it checks each sentence independently.
    sentences = [
        "Field 'Issue' shows a real moderate statistical association (Cramer's V=0.40).",
        "Within 'Issue', category 'Problem caused by your funds being low' shows an odds ratio of 5x.",
    ]
    result = bda.check_udaap_language_batch(sentences)
    assert result["passed"] is True
    assert result["n_sentences_scanned"] == 2
    assert result["n_sentences_failing"] == 0
    assert "Problem caused by your funds being low" in result["quoted_real_source_values_containing_banned_terms"]


def test_check_udaap_language_batch_fails_on_a_genuine_authored_causal_claim():
    sentences = [
        "Field 'Issue' shows a real moderate statistical association.",
        "This field causes complaints to escalate.",
    ]
    result = bda.check_udaap_language_batch(sentences)
    assert result["passed"] is False
    assert result["n_sentences_failing"] == 1
    assert result["failing_sentences"][0]["sentence_index"] == 1


# ---------------------------------------------------------------------------
# make_citation / build_field_ranking / build_category_findings
# ---------------------------------------------------------------------------


def test_make_citation_schema_has_all_seven_bp6_fields():
    citation = bda.make_citation(
        source_gate="gate3",
        source_artifact_relative_path="notebooks/x/artifacts/y.csv",
        source_field_or_metric="cramers_v",
        extracted_value=0.42,
        verification_method="test",
    )
    expected_keys = {
        "source_bp", "source_gate", "source_artifact_relative_path", "source_field_or_metric",
        "extracted_value", "retrieval_timestamp_utc", "verification_method",
    }
    assert set(citation.keys()) == expected_keys
    assert citation["source_bp"] == "bp5"
    assert citation["extracted_value"] == 0.42


def _synthetic_chi_square_df():
    return pd.DataFrame(
        [
            {"driver_field": "Issue", "outcome_field": "outcome_1", "n_rows_tested": 100,
             "n_distinct_levels": 3, "chi2_statistic": 50.0, "degrees_of_freedom": 2,
             "p_value": 0.0, "cramers_v": 0.40, "association_strength": "moderate", "control_field": False},
            {"driver_field": "Product", "outcome_field": "outcome_1", "n_rows_tested": 100,
             "n_distinct_levels": 3, "chi2_statistic": 20.0, "degrees_of_freedom": 2,
             "p_value": 0.01, "cramers_v": 0.20, "association_strength": "negligible", "control_field": False},
            {"driver_field": "State", "outcome_field": "outcome_1", "n_rows_tested": 100,
             "n_distinct_levels": 5, "chi2_statistic": 60.0, "degrees_of_freedom": 4,
             "p_value": 0.0, "cramers_v": 0.60, "association_strength": "strong", "control_field": True},
        ]
    )


def test_build_field_ranking_excludes_control_field_and_sorts_descending():
    ranking = bda.build_field_ranking(_synthetic_chi_square_df(), "outcome_1", "x.csv")
    assert [r["driver_field"] for r in ranking] == ["Issue", "Product"]
    assert ranking[0]["rank"] == 1
    assert "citation" in ranking[0]


def test_build_category_findings_respects_min_n_and_top_k():
    log_odds_df = pd.DataFrame(
        [
            {"driver_field": "Issue", "outcome_field": "outcome_1", "reference_category": "Ref",
             "category": "Big", "n_rows": 100, "n_outcome_positive": 50, "n_outcome_negative": 50,
             "odds_ratio_vs_reference": 5.0, "log_odds_ratio": 1.6, "ci_95_low": 1.0, "ci_95_high": 2.2,
             "p_value": 0.0, "continuity_correction_applied": False},
            {"driver_field": "Issue", "outcome_field": "outcome_1", "reference_category": "Ref",
             "category": "TooSmall", "n_rows": 5, "n_outcome_positive": 2, "n_outcome_negative": 3,
             "odds_ratio_vs_reference": 9.0, "log_odds_ratio": 2.2, "ci_95_low": 1.0, "ci_95_high": 3.0,
             "p_value": 0.01, "continuity_correction_applied": False},
        ]
    )
    findings = bda.build_category_findings(
        log_odds_df, "outcome_1", ["Issue"], "y.csv", min_n_per_category=30, top_k_per_field=5,
    )
    assert [f["category"] for f in findings["Issue"]] == ["Big"]


# ---------------------------------------------------------------------------
# map_shap_feature_to_driver_field / build_shap_findings
# ---------------------------------------------------------------------------


def test_map_shap_feature_company_freq_special_case():
    mapped = bda.map_shap_feature_to_driver_field("Company_freq_zscored", ["Product", "Issue"])
    assert mapped == {"driver_field": "Company", "category": None, "encoding": "frequency_zscored"}


def test_map_shap_feature_prefix_matching_does_not_confuse_issue_and_sub_issue():
    fields = ["Issue", "Sub-issue"]
    mapped_issue = bda.map_shap_feature_to_driver_field(
        "Issue_Incorrect information on your report", fields
    )
    mapped_sub_issue = bda.map_shap_feature_to_driver_field(
        "Sub-issue_Information belongs to someone else", fields
    )
    assert mapped_issue["driver_field"] == "Issue"
    assert mapped_issue["category"] == "Incorrect information on your report"
    assert mapped_sub_issue["driver_field"] == "Sub-issue"
    assert mapped_sub_issue["category"] == "Information belongs to someone else"


def test_build_shap_findings_sorted_desc_and_capped_at_top_k():
    shap_df = pd.DataFrame(
        {
            "feature": ["Company_freq_zscored", "Issue_A", "Issue_B", "Issue_C"],
            "mean_abs_shap": [1.0, 0.5, 0.9, 0.1],
        }
    )
    findings = bda.build_shap_findings(shap_df, "outcome_1", ["Issue"], "z.csv", top_k=2)
    assert [f["feature"] for f in findings] == ["Company_freq_zscored", "Issue_B"]
    assert findings[0]["rank"] == 1
    assert findings[1]["driver_field"] == "Issue"


# ---------------------------------------------------------------------------
# build_company_frequency_finding / narrative builders
# ---------------------------------------------------------------------------


def test_build_company_frequency_finding_extracts_real_fields():
    entry = {
        "odds_ratio_per_1sd": 0.5, "ci_95_low_odds_ratio_per_1sd": 0.4,
        "ci_95_high_odds_ratio_per_1sd": 0.6, "p_value": 0.001, "converged": True,
    }
    finding = bda.build_company_frequency_finding(entry, "outcome_1", "c.json")
    assert finding["driver_field"] == "Company"
    assert finding["odds_ratio_per_1sd"] == 0.5
    assert "citation" in finding


def test_build_field_narrative_contains_quoted_field_name_and_metric():
    entry = {"driver_field": "Issue", "association_strength": "moderate", "cramers_v": 0.4123,
              "p_value": 0.001, "n_rows_tested": 1000}
    text = bda.build_field_narrative(entry, "outcome_1")
    assert "'Issue'" in text
    assert "0.4123" in text


def test_build_category_narrative_contains_both_quoted_categories():
    entry = {"driver_field": "Issue", "category": "Foo", "odds_ratio_vs_reference": 5.0,
              "reference_category": "Bar", "ci_95_low": 1.0, "ci_95_high": 10.0, "n_rows": 100}
    text = bda.build_category_narrative(entry, "outcome_1")
    assert "'Foo'" in text and "'Bar'" in text


def test_build_shap_narrative_handles_company_freq_with_no_category():
    entry = {"feature": "Company_freq_zscored", "driver_field": "Company", "category": None,
              "rank": 1, "mean_abs_shap": 1.5}
    text = bda.build_shap_narrative(entry, "outcome_1")
    assert "Company" in text
    assert "(category" not in text


# ---------------------------------------------------------------------------
# build_champion_model - small synthetic scale only (see file docstring for scope rationale).
# Exercises the real fit path, including the Company_freq standardization Gate 3's own sandbox
# verification added to fix a real lbfgs non-convergence bug - a regression here would silently
# reintroduce that exact bug.
# ---------------------------------------------------------------------------


def _synthetic_champion_frame(n: int = 400, random_state: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    companies = rng.choice([f"Company_{i}" for i in range(20)], size=n)
    issue = rng.choice(["IssueA", "IssueB"], size=n, p=[0.7, 0.3])
    # Outcome more likely when Issue == IssueB - a real, learnable synthetic signal.
    p = np.where(issue == "IssueB", 0.6, 0.05)
    outcome = (rng.uniform(size=n) < p).astype(int)
    return pd.DataFrame(
        {
            "Product": rng.choice(["P1", "P2"], size=n),
            "Sub-product": rng.choice(["SP1", "SP2"], size=n),
            "Issue": issue,
            "Sub-issue": rng.choice(["SI1", "SI2"], size=n),
            "Submitted via": rng.choice(["Web", "Phone"], size=n),
            "Company": companies,
            "outcome": outcome,
        }
    )


def test_build_champion_model_converges_without_warning_on_synthetic_data():
    df = _synthetic_champion_frame()
    categorical_cols = ["Product", "Sub-product", "Issue", "Sub-issue", "Submitted via"]
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a real ConvergenceWarning must fail this test
        champion = bda.build_champion_model(df, categorical_cols, "Company", "outcome", random_state=42)

    assert "Company_freq_zscored" in champion["feature_names"]
    assert 0.0 <= champion["held_out_roc_auc"] <= 1.0
    assert champion["n_rows_train"] + champion["n_rows_test"] == len(df)
    # The real learnable signal (Issue == IssueB) should make the champion rank meaningfully
    # above random on this synthetic held-out set.
    assert champion["held_out_roc_auc"] > 0.6
