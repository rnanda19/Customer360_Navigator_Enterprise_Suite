"""
tests/bp3_complaint_escalation_prediction/test_bp3_escalation_features.py — Customer360 Navigator

Full pytest coverage for src/features/bp3_escalation_features.py (BP3 Gate 6 governance
requirement, mirroring BP2's test_bp2_friction_features.py pattern). Covers both the Gate-2-era
functions (target rule, null screening, feature lineage) and the Gate-6-added CANDIDATES/pipeline
functions, including consistency checks against the literal values BP3 Gates 3/4/5's own
delivered, already real-run-confirmed notebook source uses inline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from features import bp3_escalation_features as bef

# ---------------------------------------------------------------------------
# Constants - must exactly match what Gates 3/4/5's delivered notebooks define inline.
# ---------------------------------------------------------------------------


def test_feature_cols_categorical_matches_gate3_4_5_definitions():
    assert bef.FEATURE_COLS_CATEGORICAL == [
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "State",
        "Submitted via",
    ]


def test_company_col_matches_gate3_4_5_definitions():
    assert bef.COMPANY_COL == "Company"


def test_barred_columns_matches_gate1_policy_json():
    assert bef.BARRED_COLUMNS == [
        "Company response to consumer",
        "Timely response?",
        "Date received",
        "Date sent to company",
        "Tags",
        "Complaint ID",
        "ZIP code",
    ]


def test_needs_dense_matches_gate3_4_5_definitions():
    assert bef.NEEDS_DENSE == frozenset({"hist_gradient_boosting"})


def test_feature_cols_and_barred_cols_never_overlap():
    # The exact invariant Gate 1's leakage_rules and Gate 3/4/5's own no_barred_column_in_feature_
    # frame checks enforce at run time - verified once here, structurally, for every future edit.
    overlap = set(bef.FEATURE_COLS_CATEGORICAL + [bef.COMPANY_COL]) & set(bef.BARRED_COLUMNS)
    assert overlap == set()


# ---------------------------------------------------------------------------
# intervention_target_expr / Gate-2-era target rule
# ---------------------------------------------------------------------------


def _tiny_cfpb_frame():
    return pl.DataFrame(
        {
            "Company response to consumer": [
                "Closed with monetary relief",
                "Closed with explanation",
                "Closed with non-monetary relief",
                "In progress",
                "Untimely response",
                None,
            ],
            "Product": ["Credit card"] * 6,
        }
    )


def test_intervention_target_expr_assigns_target_and_exclusion_reason_correctly():
    df = _tiny_cfpb_frame().with_columns(bef.intervention_target_expr())
    assert df["intervention_required"].to_list() == [1, 0, 0, None, None, None]
    assert df["exclusion_reason"].to_list() == [
        None,
        None,
        None,
        "EXCLUDED_PENDING",
        "EXCLUDED_UNTIMELY_RESPONSE_OVERLAPS_BP2",
        "EXCLUDED_UNKNOWN_NULL_RESPONSE",
    ]


def test_intervention_target_expr_trainable_rows_never_carry_an_exclusion_reason():
    df = _tiny_cfpb_frame().with_columns(bef.intervention_target_expr())
    trainable = df.filter(pl.col("intervention_required").is_not_null())
    assert trainable["exclusion_reason"].null_count() == len(trainable)


# ---------------------------------------------------------------------------
# null_screen_report / fill_categorical_nulls_expr
# ---------------------------------------------------------------------------


def _tiny_feature_frame_with_nulls():
    return pl.DataFrame(
        {
            "Product": ["Credit card", "Mortgage", "Credit card"],
            "Sub-product": ["General-purpose credit card", None, "Conventional home mortgage"],
            "Issue": ["Billing dispute"] * 3,
            "Sub-issue": [None, None, "Problem with a credit reporting company"],
            "State": ["CA", None, "NY"],
            "Submitted via": ["Web"] * 3,
            "Company": ["Bank A", "Bank B", "Bank A"],
        }
    )


def test_null_screen_report_counts_real_nulls_per_column():
    report = bef.null_screen_report(_tiny_feature_frame_with_nulls().lazy())
    report_dict = dict(zip(report["column"].to_list(), report["null_count"].to_list()))
    assert report_dict["Sub-product"] == 1
    assert report_dict["Sub-issue"] == 2
    assert report_dict["State"] == 1
    assert report_dict["Product"] == 0
    assert report_dict["Company"] == 0


def test_fill_categorical_nulls_expr_fills_only_columns_with_a_sentinel():
    filled = _tiny_feature_frame_with_nulls().with_columns(bef.fill_categorical_nulls_expr())
    assert filled["Sub-product"].null_count() == 0
    assert filled["Sub-issue"].null_count() == 0
    assert filled["State"].null_count() == 0
    assert "MISSING_SUB_PRODUCT" in filled["Sub-product"].cast(pl.Utf8).to_list()
    assert "MISSING_STATE" in filled["State"].cast(pl.Utf8).to_list()


def test_fill_categorical_nulls_expr_only_touches_columns_in_null_sentinel_map():
    assert set(bef.NULL_SENTINEL_MAP.keys()) == {"Sub-product", "Sub-issue", "State"}
    assert "Product" not in bef.NULL_SENTINEL_MAP
    assert "Company" not in bef.NULL_SENTINEL_MAP


# ---------------------------------------------------------------------------
# feature_lineage_table
# ---------------------------------------------------------------------------


def test_feature_lineage_table_covers_every_feature_and_every_barred_column():
    table = bef.feature_lineage_table()
    source_cols = table["source_column"].to_list()
    for col in bef.FEATURE_COLS_CATEGORICAL + [bef.COMPANY_COL]:
        assert col in source_cols
    for barred in bef.BARRED_COLUMNS:
        assert barred in source_cols
    # Every row explicitly labeled "(none - barred)" must have its source_column in BARRED_COLUMNS
    # (never a real feature column mislabeled as barred).
    barred_label_rows = table.filter(pl.col("engineered_feature") == "(none - barred)")
    assert set(barred_label_rows["source_column"].to_list()).issubset(set(bef.BARRED_COLUMNS))
    # Every barred column has at least one "(none - barred)" row - the target column
    # ("Company response to consumer") is the one exception that ALSO carries a separate TARGET
    # row (see test_feature_lineage_table_target_row_is_never_a_feature below), so it correctly
    # appears twice in the full table but must still have its own barred-labeled row here.
    barred_labeled_source_cols = set(barred_label_rows["source_column"].to_list())
    for barred in bef.BARRED_COLUMNS:
        assert barred in barred_labeled_source_cols, f"{barred!r} has no '(none - barred)' row"


def test_feature_lineage_table_target_row_is_never_a_feature():
    table = bef.feature_lineage_table()
    target_rows = table.filter(pl.col("source_column") == "Company response to consumer")
    # The target's source column appears twice: once as the TARGET row (documenting the binary
    # rule), and once as a "(none - barred)" row (documenting it is also barred from the feature
    # set entirely) - both real, both correct, neither is a feature.
    assert len(target_rows) == 2
    engineered = set(target_rows["engineered_feature"].to_list())
    assert sum("TARGET" in e for e in engineered) == 1
    assert "(none - barred)" in engineered


# ---------------------------------------------------------------------------
# make_candidates (Gate 6 addition)
# ---------------------------------------------------------------------------


def test_make_candidates_returns_all_five_models():
    candidates = bef.make_candidates(random_state=42, scale_pos_weight=76.58)
    assert set(candidates.keys()) == {
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
        "xgboost",
        "lightgbm",
    }


def test_make_candidates_uses_given_random_state_and_class_weight_balanced():
    candidates = bef.make_candidates(random_state=123, scale_pos_weight=10.0)
    assert isinstance(candidates["logistic_regression"], LogisticRegression)
    assert candidates["logistic_regression"].random_state == 123
    assert candidates["logistic_regression"].class_weight == "balanced"
    assert isinstance(candidates["random_forest"], RandomForestClassifier)
    assert candidates["random_forest"].random_state == 123
    assert candidates["random_forest"].class_weight == "balanced"
    assert candidates["random_forest"].n_jobs == 1  # no nested parallelism (WARP)


def test_make_candidates_only_xgboost_receives_live_scale_pos_weight():
    # The real, live-computed imbalance-compensation parameter Gates 3/4/5 each derive from their
    # own train split (n_train_negative / n_train_positive) - unique to BP3's binary target, unlike
    # BP2's multiclass class_weight='balanced'-everywhere pattern.
    candidates = bef.make_candidates(random_state=42, scale_pos_weight=76.58)
    assert candidates["xgboost"].get_params(deep=False).get("scale_pos_weight") == 76.58
    from lightgbm import LGBMClassifier

    assert isinstance(candidates["lightgbm"], LGBMClassifier)
    assert "scale_pos_weight" not in {"class_weight"}  # sanity: distinct knobs, not interchangeable
    assert candidates["lightgbm"].class_weight == "balanced"


def test_make_candidates_hist_gradient_boosting_never_passed_class_weight():
    # Documented library-capability asymmetry (Gates 3/4/5's own comment, mirrored from
    # bp2_friction_features.py) - HistGradientBoostingClassifier's sklearn API does not support
    # class_weight for this environment's installed version.
    candidates = bef.make_candidates(random_state=42, scale_pos_weight=50.0)
    assert isinstance(candidates["hist_gradient_boosting"], HistGradientBoostingClassifier)
    params = candidates["hist_gradient_boosting"].get_params(deep=False)
    assert "class_weight" not in params or params.get("class_weight") is None


# ---------------------------------------------------------------------------
# build_shared_preprocessing (Gate 6 addition)
# ---------------------------------------------------------------------------


def _tiny_raw_frame(n=6):
    products = ["Checking or savings account", "Credit card"] * (n // 2)
    return pd.DataFrame(
        {
            "Product": products,
            "Sub-product": ["Checking account"] * n,
            "Issue": ["Some issue"] * n,
            "Sub-issue": ["Some sub-issue"] * n,
            "State": ["CA", "NY"] * (n // 2),
            "Submitted via": ["Web"] * n,
            "Company": [f"Company_{i % 3}" for i in range(n)],
        }
    )


def test_build_shared_preprocessing_shapes_and_feature_names():
    X_train_raw = _tiny_raw_frame(6)
    X_test_raw = _tiny_raw_frame(4)
    ohe, X_train_shared, X_test_shared, company_freq_map, feature_names = bef.build_shared_preprocessing(
        X_train_raw, X_test_raw
    )
    assert X_train_shared.shape[0] == 6
    assert X_test_shared.shape[0] == 4
    assert X_train_shared.shape[1] == len(feature_names)
    assert feature_names[-1] == "Company_freq"
    assert set(company_freq_map.keys()) == {"Company_0", "Company_1", "Company_2"}


def test_build_shared_preprocessing_unseen_test_company_gets_zero_frequency():
    X_train_raw = _tiny_raw_frame(6)
    X_test_raw = _tiny_raw_frame(2)
    X_test_raw.loc[0, "Company"] = "Never_Seen_In_Train"
    _, _, X_test_shared, company_freq_map, _ = bef.build_shared_preprocessing(X_train_raw, X_test_raw)
    assert "Never_Seen_In_Train" not in company_freq_map
    assert X_test_shared.toarray()[0, -1] == 0.0


# ---------------------------------------------------------------------------
# to_dense
# ---------------------------------------------------------------------------


def test_to_dense_converts_sparse():
    from scipy import sparse as sp

    sparse_matrix = sp.csr_matrix(np.array([[1.0, 0.0], [0.0, 2.0]]))
    dense = bef.to_dense(sparse_matrix)
    assert isinstance(dense, np.ndarray)
    np.testing.assert_array_equal(dense, [[1.0, 0.0], [0.0, 2.0]])


def test_to_dense_passthrough_for_already_dense():
    arr = np.array([[1.0, 2.0]])
    assert bef.to_dense(arr) is arr


# ---------------------------------------------------------------------------
# is_linear_champion (the real bug Gate 4 fixed before delivery, same rule as BP1/BP2)
# ---------------------------------------------------------------------------


def test_is_linear_champion_true_for_logistic_regression():
    assert bef.is_linear_champion(LogisticRegression()) is True


def test_is_linear_champion_false_for_tree_based_models_not_in_needs_dense():
    # xgboost is NOT in NEEDS_DENSE (that set only has hist_gradient_boosting) but must still be
    # treated as non-linear for SHAP densification - the exact gap the Gate 4 fix closed.
    from xgboost import XGBClassifier

    assert bef.is_linear_champion(XGBClassifier()) is False
    assert bef.is_linear_champion(HistGradientBoostingClassifier()) is False
    assert "xgboost" not in bef.NEEDS_DENSE


# ---------------------------------------------------------------------------
# reason_codes_for_row_shared (reused verbatim from bp1_intent_classifier - HYPER)
# ---------------------------------------------------------------------------


def test_reason_codes_for_row_shared_only_returns_nonzero_valued_features():
    feature_names = np.array(["Product_CreditCard", "State_CA", "Company_freq", "State_NY"])
    shap_values = np.array([0.9, 0.5, 0.1, 5.0])  # State_NY has the HIGHEST |shap| ...
    row_values = np.array([0.3, 0.2, 12.0, 0.0])  # ... but is absent (0.0) in this row - excluded
    codes = bef.reason_codes_for_row_shared(shap_values, row_values, feature_names, n_reason_codes=5)
    assert "State_NY" not in codes
    assert set(codes) == {"Product_CreditCard", "State_CA", "Company_freq"}


def test_reason_codes_for_row_shared_is_the_bp1_module_function():
    # Explicit HYPER reuse assertion - this is not a re-implementation, it is the same object.
    from models.bp1_intent_classifier import reason_codes_for_row

    assert bef.reason_codes_for_row_shared is reason_codes_for_row


def test_reason_codes_for_row_shared_shape_mismatch_raises():
    with pytest.raises(ValueError, match="Shape mismatch"):
        bef.reason_codes_for_row_shared(
            np.array([0.1, 0.2]), np.array([1.0, 2.0, 3.0]), np.array(["a", "b", "c"])
        )
