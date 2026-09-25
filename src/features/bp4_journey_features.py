"""
src/features/bp4_journey_features.py — Customer360 Navigator

Shared BP4 (Customer Journey Analytics) feature-engineering module. Built AT Gate 2 (HYPER,
matching BP3's own improved pattern of building its shared module at Gate 2 rather than
retroactively at Gate 6, the way BP2's was). Master Plan Section 5.1/7 (BP4 methodology),
Section 8 Gate 2 (Data Verification & Feature/Taxonomy Engineering), Section 17.5 (BP4's own
designated Polars/DuckDB lazy-aggregation tech stack).

BP4 has no supervised target - "feature engineering" here means building the two real journey
units BP4 Gate 1's policy.json already defines: (1) the complaint-event journey (row-level,
response_lag_days + the real Gold-layer taxonomy overlay) and (2) the issue-cluster journey
(aggregate-level, a real monthly time series plus a real per-cluster summary). Every real null
found in a journey-relevant column is filled with an explicit, named sentinel - never silently
dropped (this project's standing Gate 2 exit criterion) - and every engineered column is
documented in feature_lineage_table() below.

This module is import-only shared logic (HYPER). It performs no I/O side effects at import time
and is never executed by Claude - only the user runs it, in their own environment, per the
project's execution-boundary rule.

Public functions:
  load_cfpb_with_journey_features(cfpb_path, gold_taxonomy_path) -> pl.LazyFrame
  build_issue_cluster_monthly(journey_lazy)   -> pl.LazyFrame
  build_issue_cluster_summary(journey_lazy)   -> pl.LazyFrame
  feature_lineage_table()                     -> pl.DataFrame
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from taxonomy.taxonomy_mapper import CFPB_DTYPES

# BP4's real, disclosed issue-cluster journey key (Gate 1 policy.json journey_definition.unit_2).
CLUSTER_KEY: list[str] = ["Company", "Product", "Sub-product", "Issue", "Sub-issue"]

# Barred from every BP4 journey-grouping key (Gate 1 policy.json scope_boundaries) - kept here so
# a structural check can assert neither ever appears in CLUSTER_KEY, rather than just trusting the
# constant above was typed correctly.
BARRED_JOURNEY_COLUMNS: list[str] = ["Tags", "ZIP code"]

DATE_FMT: str = "%m/%d/%Y"

# Explicit per-column sentinel for real nulls found in journey-relevant columns (BP4 Gate 1
# policy.json live_checks.null_counts_journey_columns, re-verified live in this notebook's own
# Gate 2 run) - HYPER-reuses BP3's own NULL_SENTINEL_MAP naming convention (src/features/
# bp3_escalation_features.py) for cross-BP consistency, not reinvented. Sub-product and Sub-issue
# are part of CLUSTER_KEY (a null there would otherwise silently fragment or drop cluster
# membership under a tool that treats null differently from Polars' own group-by); State is not
# part of CLUSTER_KEY but is filled anyway for the same zero-nulls-silently-dropped discipline,
# since Gate 1's own assumptions name it as BP4's one sanctioned geographic dimension for a later
# gate. Product/Issue/Company have 0 real nulls (Gate 1 live_checks) and need no entry here.
NULL_SENTINEL_MAP: dict[str, str] = {
    "Sub-product": "MISSING_SUB_PRODUCT",
    "Sub-issue": "MISSING_SUB_ISSUE",
    "State": "MISSING_STATE",
}


def live_null_counts(cfpb_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Live null count for every journey-relevant column (NULL_SENTINEL_MAP keys plus the
    CLUSTER_KEY columns with no documented nulls) - the real numbers Gate 2's own 'zero nulls
    silently dropped' exit criterion is checked against, computed fresh rather than trusted from
    Gate 1's policy.json."""
    cols = sorted(set(CLUSTER_KEY) | set(NULL_SENTINEL_MAP.keys()))
    wide = cfpb_lazy.select([pl.col(c).is_null().sum().alias(c) for c in cols]).collect()
    return pl.DataFrame({"column": cols, "null_count": [int(wide[c][0]) for c in cols]})


def journey_derived_columns_expr() -> list[pl.Expr]:
    """Polars expressions for BP4's real complaint-event journey columns: parsed dates,
    response_lag_days (Date sent to company - Date received), and complaint_month (the real
    year-month bucket of Date received, used by the issue-cluster monthly table below)."""
    date_received = pl.col("Date received").str.strptime(pl.Date, DATE_FMT)
    date_sent = pl.col("Date sent to company").str.strptime(pl.Date, DATE_FMT)
    return [
        date_received.alias("date_received_parsed"),
        date_sent.alias("date_sent_parsed"),
        (date_sent - date_received).dt.total_days().alias("response_lag_days"),
        date_received.dt.strftime("%Y-%m").alias("complaint_month"),
    ]


def fill_journey_nulls_expr() -> list[pl.Expr]:
    """Explicit sentinel fill for every journey-relevant column with a documented real null count
    (NULL_SENTINEL_MAP) - satisfies Gate 2's 'zero nulls silently dropped' exit criterion. Also
    emits a companion boolean *_was_null flag per filled column so a filled row stays traceable,
    never silently indistinguishable from a genuine real category. Both the flag and the fill are
    applied in one with_columns() call against the same, still-unfilled frame, so the flag always
    reflects the real, original null status."""
    flag_exprs = [
        pl.col(col).is_null().alias(f"{col.lower().replace('-', '_').replace(' ', '_')}_was_null")
        for col in NULL_SENTINEL_MAP
    ]
    fill_exprs = [
        pl.col(col).cast(pl.Utf8).fill_null(sentinel).cast(pl.Categorical).alias(col)
        for col, sentinel in NULL_SENTINEL_MAP.items()
    ]
    return flag_exprs + fill_exprs


def load_cfpb_with_journey_features(cfpb_path: str | Path, gold_taxonomy_path: str | Path) -> pl.LazyFrame:
    """Lazy-scan the real CFPB complaints file (WARP: no eager full-file load), attach the real
    complaint-event journey columns (response_lag_days, complaint_month), the explicit null-
    sentinel fill for every journey-relevant column with a real null count (never a silent drop),
    and the real Gold-layer common_taxonomy_bucket overlay (BP1/BP2's own Gate 2 work, reused
    unmodified, HYPER) joined in on the real, unique Complaint ID."""
    lazy = pl.scan_csv(cfpb_path, schema_overrides=CFPB_DTYPES)
    lazy = lazy.with_columns(fill_journey_nulls_expr())
    lazy = lazy.with_columns(journey_derived_columns_expr())

    taxonomy_lazy = pl.scan_parquet(gold_taxonomy_path).select(
        pl.col("Complaint ID"), pl.col("common_taxonomy_bucket")
    )
    lazy = lazy.join(taxonomy_lazy, on="Complaint ID", how="left")
    lazy = lazy.with_columns(
        (pl.col("common_taxonomy_bucket") != "OUT_OF_SCOPE_NO_BANKING77_OVERLAP").alias("banking77_in_scope")
    )
    return lazy


def build_issue_cluster_monthly(journey_lazy: pl.LazyFrame) -> pl.LazyFrame:
    """Real monthly complaint-volume time series per issue-cluster (Master Plan's 'repeat-contact/
    bottleneck' signal, Gate 1 policy.json journey_definition.unit_2) - WARP: lazy group-by
    push-down, no eager materialization, no per-row Python loop."""
    return (
        journey_lazy.group_by(CLUSTER_KEY + ["complaint_month"])
        .agg(
            pl.len().alias("n_complaints_month"),
            pl.col("response_lag_days").mean().alias("avg_response_lag_days_month"),
            pl.col("banking77_in_scope").sum().alias("n_banking77_in_scope_month"),
        )
        .sort(CLUSTER_KEY + ["complaint_month"])
    )


def build_issue_cluster_summary(journey_lazy: pl.LazyFrame) -> pl.LazyFrame:
    """One real row per issue-cluster: total complaint count, real first/last active date, real
    count of distinct active months, mean response lag, and real BANKING77-overlay coverage
    fraction - the cluster-level summary a later gate reads rather than re-aggregating from
    scratch."""
    return (
        journey_lazy.group_by(CLUSTER_KEY)
        .agg(
            pl.len().alias("n_complaints_total"),
            pl.col("date_received_parsed").min().alias("first_complaint_date"),
            pl.col("date_received_parsed").max().alias("last_complaint_date"),
            pl.col("complaint_month").n_unique().alias("n_active_months"),
            pl.col("response_lag_days").mean().alias("avg_response_lag_days"),
            pl.col("banking77_in_scope").mean().alias("banking77_coverage_fraction"),
        )
        .with_columns((pl.col("n_complaints_total") > 1).alias("is_recurring_cluster"))
        .sort("n_complaints_total", descending=True)
    )


def feature_lineage_table() -> pl.DataFrame:
    """The feature-lineage table Gate 2's own exit criterion requires ('feature-lineage table
    complete') - one row per engineered column, its real source column(s), and its transform.
    Built from this module's own constants (never hand-duplicated elsewhere) so it can never drift
    from what the pipeline actually does."""
    rows: list[dict] = [
        {
            "engineered_feature": "response_lag_days",
            "source_column": "Date received, Date sent to company",
            "transform": "date_sent_parsed - date_received_parsed, in real days",
            "null_handling": "n/a - Gate 1 live-verified 0 nulls in either source date column",
        },
        {
            "engineered_feature": "complaint_month",
            "source_column": "Date received",
            "transform": "real year-month bucket (date_received_parsed.strftime('%Y-%m'))",
            "null_handling": "n/a - Gate 1 live-verified 0 nulls in Date received",
        },
        {
            "engineered_feature": "common_taxonomy_bucket, banking77_in_scope",
            "source_column": "Complaint ID (join key) -> " "data/processed/cfpb_common_taxonomy_gold.parquet",
            "transform": "left join on the real, unique Complaint ID to BP1/BP2's own Gate 2 "
            "Gold-layer taxonomy overlay (HYPER, reused unmodified, never recomputed)",
            "null_handling": "n/a - Gate 1 live-verified the Gold taxonomy parquet's row count "
            "equals the raw CFPB row count (every row has a bucket)",
        },
    ]
    for col, sentinel in NULL_SENTINEL_MAP.items():
        scope_note = "part of CLUSTER_KEY" if col in CLUSTER_KEY else "not part of CLUSTER_KEY"
        rows.append(
            {
                "engineered_feature": f"{col} (sentinel-filled, {scope_note})",
                "source_column": col,
                "transform": f"real nulls cast Utf8 -> filled '{sentinel}' -> cast back to "
                "Categorical; a companion boolean *_was_null flag column records which rows "
                "were filled",
                "null_handling": f"real nulls filled with sentinel category '{sentinel}' - "
                "never silently dropped",
            }
        )
    for col in BARRED_JOURNEY_COLUMNS:
        rows.append(
            {
                "engineered_feature": "(none - barred from every BP4 journey-grouping key)",
                "source_column": col,
                "transform": "n/a",
                "null_handling": "n/a",
            }
        )
    return pl.DataFrame(rows)
