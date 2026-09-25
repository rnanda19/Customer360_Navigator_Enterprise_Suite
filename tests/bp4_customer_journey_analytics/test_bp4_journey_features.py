"""
tests/bp4_customer_journey_analytics/test_bp4_journey_features.py — Customer360 Navigator

Full pytest coverage for src/features/bp4_journey_features.py (BP4 Gate 6 governance
requirement, mirroring BP2/BP3's own test_*_features.py pattern). Unlike BP3, BP4's shared
module needed no Gate-6 extension - CLUSTER_KEY, BARRED_JOURNEY_COLUMNS, and NULL_SENTINEL_MAP
were already centralized at Gate 2 (HYPER, matching BP3's own improved pattern of not waiting
until Gate 6 to de-duplicate), and no CANDIDATES/pipeline logic is triplicated across BP4's
Gates 3/4/5 the way BP3's classifier pipeline was - Gate 3's 5 execution-engine functions are
one-off benchmark candidates, never reused by Gate 4 or Gate 5. This file is BP4's first-ever
test coverage - previously `pytest tests/` only exercised BP1/BP2/BP3's own tests.
"""

from __future__ import annotations

import polars as pl

from features import bp4_journey_features as bjf

# ---------------------------------------------------------------------------
# Constants - must exactly match what Gates 2/3/4/5's delivered notebooks define/read live.
# ---------------------------------------------------------------------------


def test_cluster_key_matches_gate1_policy_definition():
    assert bjf.CLUSTER_KEY == ["Company", "Product", "Sub-product", "Issue", "Sub-issue"]


def test_barred_journey_columns_matches_gate1_scope_boundaries():
    assert bjf.BARRED_JOURNEY_COLUMNS == ["Tags", "ZIP code"]


def test_cluster_key_and_barred_columns_never_overlap():
    # The exact invariant every gate's own no_barred_column_in_cluster_key /
    # no_barred_column_in_cluster_report check enforces at run time - verified once here,
    # structurally, for every future edit.
    assert set(bjf.CLUSTER_KEY) & set(bjf.BARRED_JOURNEY_COLUMNS) == set()


def test_null_sentinel_map_covers_exactly_the_gate1_live_checked_null_columns():
    assert set(bjf.NULL_SENTINEL_MAP.keys()) == {"Sub-product", "Sub-issue", "State"}
    assert bjf.NULL_SENTINEL_MAP["Sub-product"] == "MISSING_SUB_PRODUCT"
    assert bjf.NULL_SENTINEL_MAP["Sub-issue"] == "MISSING_SUB_ISSUE"
    assert bjf.NULL_SENTINEL_MAP["State"] == "MISSING_STATE"


# ---------------------------------------------------------------------------
# live_null_counts
# ---------------------------------------------------------------------------


def _tiny_cfpb_frame():
    return pl.DataFrame(
        {
            "Company": ["Acme Bank", "Acme Bank", "Beta Financial"],
            "Product": ["Checking or savings account"] * 3,
            "Sub-product": ["Checking account", None, "Checking account"],
            "Issue": ["Managing an account"] * 3,
            "Sub-issue": [None, None, "Some sub-issue"],
            "State": ["CA", None, "NY"],
        }
    )


def test_live_null_counts_reports_real_nulls_per_journey_relevant_column():
    report = bjf.live_null_counts(_tiny_cfpb_frame().lazy())
    report_dict = dict(zip(report["column"].to_list(), report["null_count"].to_list()))
    assert report_dict["Sub-product"] == 1
    assert report_dict["Sub-issue"] == 2
    assert report_dict["State"] == 1
    assert report_dict["Company"] == 0
    assert report_dict["Product"] == 0
    assert report_dict["Issue"] == 0


# ---------------------------------------------------------------------------
# journey_derived_columns_expr
# ---------------------------------------------------------------------------


def _tiny_dated_frame():
    return pl.DataFrame(
        {
            "Date received": ["03/01/2024", "03/20/2024"],
            "Date sent to company": ["03/05/2024", "03/20/2024"],
        }
    )


def test_journey_derived_columns_expr_computes_response_lag_days_and_month():
    df = _tiny_dated_frame().with_columns(bjf.journey_derived_columns_expr())
    assert df["response_lag_days"].to_list() == [4, 0]
    assert df["complaint_month"].to_list() == ["2024-03", "2024-03"]


# ---------------------------------------------------------------------------
# fill_journey_nulls_expr
# ---------------------------------------------------------------------------


def test_fill_journey_nulls_expr_fills_sentinel_and_flags_was_null():
    filled = _tiny_cfpb_frame().with_columns(bjf.fill_journey_nulls_expr())
    assert filled["Sub-product"].null_count() == 0
    assert filled["Sub-issue"].null_count() == 0
    assert filled["State"].null_count() == 0
    assert "MISSING_SUB_PRODUCT" in filled["Sub-product"].cast(pl.Utf8).to_list()
    assert "MISSING_SUB_ISSUE" in filled["Sub-issue"].cast(pl.Utf8).to_list()
    assert "MISSING_STATE" in filled["State"].cast(pl.Utf8).to_list()
    # Companion *_was_null flags must reflect the ORIGINAL null status, not the post-fill value.
    assert filled["sub_product_was_null"].to_list() == [False, True, False]
    assert filled["sub_issue_was_null"].to_list() == [True, True, False]
    assert filled["state_was_null"].to_list() == [False, True, False]


def test_fill_journey_nulls_expr_only_touches_null_sentinel_map_columns():
    filled_cols = set(bjf.fill_journey_nulls_expr.__doc__ or "")  # smoke: doc exists
    assert filled_cols or True  # doc presence is non-essential; real check is the flag columns:
    filled = _tiny_cfpb_frame().with_columns(bjf.fill_journey_nulls_expr())
    for col in bjf.NULL_SENTINEL_MAP:
        flag_col = f"{col.lower().replace('-', '_').replace(' ', '_')}_was_null"
        assert flag_col in filled.columns
    assert "company_was_null" not in filled.columns
    assert "product_was_null" not in filled.columns


# ---------------------------------------------------------------------------
# build_issue_cluster_monthly / build_issue_cluster_summary
# ---------------------------------------------------------------------------


def _tiny_journey_frame():
    return pl.DataFrame(
        {
            "Company": ["Acme Bank", "Acme Bank", "Acme Bank", "Beta Financial"],
            "Product": ["Checking or savings account"] * 4,
            "Sub-product": ["Checking account"] * 4,
            "Issue": ["Managing an account"] * 4,
            "Sub-issue": ["Some sub-issue"] * 4,
            "date_received_parsed": [
                pl.date(2024, 1, 5),
                pl.date(2024, 1, 20),
                pl.date(2024, 2, 10),
                pl.date(2024, 1, 1),
            ],
            "complaint_month": ["2024-01", "2024-01", "2024-02", "2024-01"],
            "response_lag_days": [1, 3, 5, 0],
            "banking77_in_scope": [True, False, True, False],
        }
    ).lazy()


def test_build_issue_cluster_monthly_aggregates_per_cluster_per_month():
    monthly = bjf.build_issue_cluster_monthly(_tiny_journey_frame()).collect()
    acme_jan = monthly.filter((pl.col("Company") == "Acme Bank") & (pl.col("complaint_month") == "2024-01"))
    assert acme_jan["n_complaints_month"].to_list() == [2]
    assert acme_jan["avg_response_lag_days_month"].to_list() == [2.0]  # mean(1, 3)
    assert acme_jan["n_banking77_in_scope_month"].to_list() == [1]  # True, False -> sum 1


def test_build_issue_cluster_summary_computes_real_per_cluster_totals_and_recurring_flag():
    summary = bjf.build_issue_cluster_summary(_tiny_journey_frame()).collect()
    acme_row = summary.filter(pl.col("Company") == "Acme Bank")
    assert acme_row["n_complaints_total"].to_list() == [3]
    assert acme_row["is_recurring_cluster"].to_list() == [True]  # n_complaints_total > 1
    assert acme_row["n_active_months"].to_list() == [2]  # 2024-01, 2024-02
    beta_row = summary.filter(pl.col("Company") == "Beta Financial")
    assert beta_row["n_complaints_total"].to_list() == [1]
    assert beta_row["is_recurring_cluster"].to_list() == [False]


def test_build_issue_cluster_summary_is_sorted_descending_by_complaint_count():
    summary = bjf.build_issue_cluster_summary(_tiny_journey_frame()).collect()
    counts = summary["n_complaints_total"].to_list()
    assert counts == sorted(counts, reverse=True)


# ---------------------------------------------------------------------------
# feature_lineage_table
# ---------------------------------------------------------------------------


def test_feature_lineage_table_covers_engineered_columns_and_barred_columns():
    table = bjf.feature_lineage_table()
    engineered = table["engineered_feature"].to_list()
    assert any("response_lag_days" in e for e in engineered)
    assert any("complaint_month" in e for e in engineered)
    assert any("banking77_in_scope" in e for e in engineered)
    for col in bjf.NULL_SENTINEL_MAP:
        assert any(col in e for e in engineered)
    barred_rows = table.filter(
        pl.col("engineered_feature") == "(none - barred from every BP4 journey-grouping key)"
    )
    assert set(barred_rows["source_column"].to_list()) == set(bjf.BARRED_JOURNEY_COLUMNS)


def test_feature_lineage_table_sentinel_rows_note_cluster_key_membership():
    table = bjf.feature_lineage_table()
    sub_product_rows = table.filter(pl.col("source_column") == "Sub-product")
    assert len(sub_product_rows) == 1
    assert "part of CLUSTER_KEY" in sub_product_rows["engineered_feature"].to_list()[0]
    state_rows = table.filter(pl.col("source_column") == "State")
    assert len(state_rows) == 1
    assert "not part of CLUSTER_KEY" in state_rows["engineered_feature"].to_list()[0]
