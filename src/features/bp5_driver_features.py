"""
src/features/bp5_driver_features.py — Customer360 Navigator

BP5 (Root-Cause & Driver Analytics) shared feature-engineering module, built at Gate 2 (Data
Verification & Feature Engineering), mirroring bp3_escalation_features.py's Gate-2-first pattern
(HYPER: shared component library, built once, not triplicated inline across later gates first).

Why BP5's Gate 2 differs from BP1's/BP2's/BP3's: BP5 has no single supervised target and
integrates no BANKING77 taxonomy (Master Plan BP table: Integrates BANKING77? = NO). Per BP5
Gate 1's own real, live-verified policy.json, BP5 tests real candidate driver fields (Product,
Sub-product, Issue, Sub-issue, Submitted via, Company; State as a control field only) for
statistical ASSOCIATION - never causation - against TWO real, distinct CFPB outcome fields:

  outcome_1_intervention_required - reused verbatim from BP3 Gate 1's own real target definition
    on 'Company response to consumer' (identical rule, independently re-verified live here, never
    copied from BP3's own already-real-run artifact).
  outcome_2_timely_response_failure - new to BP5: binary from the real 'Timely response?' field
    (1 if 'No', 0 if 'Yes'), computed over the full real population independent of
    'Company response to consumer'.

So this module's Gate 2 job is: tag every real row with BOTH outcome fields (and each one's own
exclusion reason), apply the explicit null-sentinel fill to the real candidate driver columns that
have real nulls, build a driver-field lineage table (distinguishing PRIMARY drivers, the CONTROL
field, and BARRED columns), and write the Gold layer - mirroring BP3 Gate 2's
"every row tagged, none dropped" pattern, doubled for two outcomes instead of one.

Standing rules this module follows:
  - WARP: Polars lazy scans, category dtype (reused from taxonomy_mapper.CFPB_DTYPES, not
    re-derived), no pandas, no eager full-file loads where a lazy scan + select + collect will do.
  - Zero-fabrication: every null count, distinct-value count, class-balance number, and overlap
    figure this module's report functions produce is computed live against the real CFPB file -
    none are asserted from BP5 Gate 1's policy.json without re-measuring (Gate 2's own notebook
    performs that drift cross-check; this module only computes the live numbers).
  - This module is import-only shared logic (HYPER). It performs no I/O side effects at import
    time and is never executed by Claude - only the user runs it, per the execution-boundary rule.

Public functions:
  outcome_1_target_expr()                               -> list[pl.Expr]
  outcome_2_target_expr()                                -> list[pl.Expr]
  null_screen_report(cfpb_lazy)                          -> pl.DataFrame
  fill_categorical_nulls_expr()                          -> list[pl.Expr]
  load_cfpb_with_outcomes_and_filled_features(cfpb_path) -> pl.LazyFrame
  outcome_overlap_report(cfpb_lazy_tagged)               -> dict
  feature_lineage_table()                                -> pl.DataFrame
  build_bp5_driver_gold_layer(cfpb_lazy, out_dir)        -> dict (paths + row counts)
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from taxonomy.taxonomy_mapper import CFPB_DTYPES  # noqa: F401  (re-exported for callers)

# Barred from the candidate driver set entirely - defines one of the two outcomes, an
# outcome-echo risk against the OTHER outcome, or a leakage/compliance risk. See BP5 Gate 1's own
# real policy.json leakage_rules for the full per-column rationale - not re-derived here.
BARRED_COLUMNS: list[str] = [
    "Company response to consumer",  # defines outcome_1; barred as a driver for outcome_2 too
    "Timely response?",  # defines outcome_2; barred as a driver for outcome_1 too
    "Date received",
    "Date sent to company",
    "Tags",
    "Company public response",
    "Complaint ID",
    "ZIP code",
]

# The 6 real candidate driver fields BP5 Gate 1's policy.json actually names (product/issue +
# process fields) - tested for association against BOTH outcome_1 and outcome_2 at Gate 3/4.
# Company (2,970 distinct, per BP5 Gate 1's own live-verified candidate_driver_field_profile) is
# handled separately below (frequency-encoded later, not one-hot - identical design choice to
# bp2_friction_features.py's / bp3_escalation_features.py's COMPANY_COL).
PRODUCT_ISSUE_FIELDS: list[str] = ["Product", "Sub-product", "Issue", "Sub-issue"]
PROCESS_FIELDS: list[str] = ["Submitted via", "Company"]
FEATURE_COLS_CATEGORICAL: list[str] = [c for c in (PRODUCT_ISSUE_FIELDS + PROCESS_FIELDS) if c != "Company"]
COMPANY_COL: str = "Company"

# Kept only as a secondary geographic CONTROL field (BP5 Gate 1 policy.json) - never presented as
# a primary named driver, per the Master Plan's own BP5 wording.
CONTROL_FIELD: str = "State"

# Explicit per-column sentinel for real nulls found in the candidate driver / control columns
# (BP5 Gate 1's own live-verified candidate_driver_field_profile) - Gate 2's own exit criterion is
# "zero nulls silently dropped," so every null-bearing column gets its own named sentinel category
# rather than a generic "MISSING" or an implicit drop/error from a downstream encoder. Product,
# Issue, Submitted via, and Company have 0 real nulls and need no sentinel - listed here only for
# the columns that actually have one.
NULL_SENTINEL_MAP: dict[str, str] = {
    "Sub-product": "MISSING_SUB_PRODUCT",
    "Sub-issue": "MISSING_SUB_ISSUE",
    "State": "MISSING_STATE",
}


def outcome_1_target_expr() -> list[pl.Expr]:
    """outcome_1_intervention_required, reused VERBATIM from BP3 Gate 1's own real target rule on
    'Company response to consumer' (BP5 Gate 1 policy.json target_definition.
    outcome_1_intervention_required.reused_from) - must match BP3's rule exactly, never
    re-derived differently here. Returns (outcome_1_intervention_required, outcome_1_exclusion_reason)."""
    outcome_1 = (
        pl.when(pl.col("Company response to consumer") == "Closed with monetary relief")
        .then(pl.lit(1, dtype=pl.Int8))
        .when(
            pl.col("Company response to consumer").is_in(
                ["Closed with explanation", "Closed with non-monetary relief"]
            )
        )
        .then(pl.lit(0, dtype=pl.Int8))
        .otherwise(pl.lit(None, dtype=pl.Int8))
        .alias("outcome_1_intervention_required")
    )
    outcome_1_exclusion_reason = (
        pl.when(pl.col("Company response to consumer") == "In progress")
        .then(pl.lit("EXCLUDED_PENDING"))
        .when(pl.col("Company response to consumer") == "Untimely response")
        .then(pl.lit("EXCLUDED_UNTIMELY_RESPONSE_OVERLAPS_BP2"))
        .when(pl.col("Company response to consumer").is_null())
        .then(pl.lit("EXCLUDED_UNKNOWN_NULL_RESPONSE"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("outcome_1_exclusion_reason")
    )
    return [outcome_1, outcome_1_exclusion_reason]


def outcome_2_target_expr() -> list[pl.Expr]:
    """outcome_2_timely_response_failure, new to BP5 (BP5 Gate 1 policy.json target_definition.
    outcome_2_timely_response_failure): binary from the real 'Timely response?' field, 1 if 'No',
    0 if 'Yes', computed over the full real population independent of
    'Company response to consumer'. Returns (outcome_2_timely_response_failure,
    outcome_2_exclusion_reason) - the exclusion reason column exists for schema symmetry with
    outcome_1 even though BP5 Gate 1's own live_checks recorded 0 real null
    'Timely response?' rows on 2026-09-24 (re-verified live by Gate 2's own notebook, never
    assumed to stay 0 forever)."""
    outcome_2 = (
        pl.when(pl.col("Timely response?") == "No")
        .then(pl.lit(1, dtype=pl.Int8))
        .when(pl.col("Timely response?") == "Yes")
        .then(pl.lit(0, dtype=pl.Int8))
        .otherwise(pl.lit(None, dtype=pl.Int8))
        .alias("outcome_2_timely_response_failure")
    )
    outcome_2_exclusion_reason = (
        pl.when(pl.col("Timely response?").is_null())
        .then(pl.lit("EXCLUDED_NULL_TIMELY_RESPONSE"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
        .alias("outcome_2_exclusion_reason")
    )
    return [outcome_2, outcome_2_exclusion_reason]


def null_screen_report(cfpb_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Live null count for every BP5 candidate driver / control column (FEATURE_COLS_CATEGORICAL +
    COMPANY_COL + CONTROL_FIELD) - the real numbers Gate 2's 'zero nulls silently dropped' exit
    criterion is checked against, computed fresh rather than trusted from BP5 Gate 1's policy.json."""
    cols = FEATURE_COLS_CATEGORICAL + [COMPANY_COL, CONTROL_FIELD]
    wide = cfpb_lazy.select([pl.col(c).is_null().sum().alias(c) for c in cols]).collect()
    return pl.DataFrame({"column": cols, "null_count": [int(wide[c][0]) for c in cols]})


def fill_categorical_nulls_expr() -> list[pl.Expr]:
    """Explicit sentinel fill for every candidate driver / control column with a documented real
    null count (NULL_SENTINEL_MAP) - satisfies Gate 2's 'zero nulls silently dropped' exit
    criterion. A column with a real null count of 0 does not need (and is not given) a no-op fill
    here."""
    return [
        pl.col(col).cast(pl.Utf8).fill_null(sentinel).cast(pl.Categorical).alias(col)
        for col, sentinel in NULL_SENTINEL_MAP.items()
    ]


def load_cfpb_with_outcomes_and_filled_features(cfpb_path: str | Path) -> pl.LazyFrame:
    """Lazy-scan the CFPB complaints file (WARP: no eager full-file load), attach BOTH outcome
    fields + their exclusion reasons (this module's own rules, matching BP5 Gate 1's policy.json
    exactly), and apply the explicit null-sentinel fill to every candidate driver / control column
    that has one - never a silent drop."""
    lazy = pl.scan_csv(cfpb_path, schema_overrides=CFPB_DTYPES)
    lazy = lazy.with_columns(outcome_1_target_expr() + outcome_2_target_expr())
    lazy = lazy.with_columns(fill_categorical_nulls_expr())
    return lazy


def outcome_overlap_report(cfpb_lazy_tagged: pl.LazyFrame) -> dict:
    """Live re-verification of BP5 Gate 1's own outcome_field_overlap_live_check - how much
    'Company response to consumer' == 'Untimely response' coincides with
    'Timely response?' == 'No', and how much outcome_1's positive class coincides with
    outcome_2's positive class. Computed fresh against the real, currently-tagged data (never
    trusted from Gate 1's policy.json without re-measuring) so Gate 2's own drift check has a real
    number to compare against."""
    counts = (
        cfpb_lazy_tagged.select(
            [
                (pl.col("Company response to consumer") == "Untimely response").alias("is_untimely_response"),
                (pl.col("Timely response?") == "No").alias("is_timely_no"),
                (pl.col("outcome_1_intervention_required") == 1).alias("is_outcome_1_positive"),
            ]
        )
        .collect()
    )
    n_untimely_response_rows = int(counts["is_untimely_response"].sum())
    n_untimely_response_and_timely_no = int(
        (counts["is_untimely_response"] & counts["is_timely_no"]).sum()
    )
    n_untimely_response_and_timely_yes = n_untimely_response_rows - n_untimely_response_and_timely_no
    n_timely_no_rows = int(counts["is_timely_no"].sum())
    n_outcome_1_positive_rows = int(counts["is_outcome_1_positive"].fill_null(False).sum())
    n_intervention_required_and_timely_no = int(
        (counts["is_outcome_1_positive"].fill_null(False) & counts["is_timely_no"]).sum()
    )
    return {
        "n_untimely_response_rows": n_untimely_response_rows,
        "n_untimely_response_and_timely_no": n_untimely_response_and_timely_no,
        "n_untimely_response_and_timely_yes": n_untimely_response_and_timely_yes,
        "pct_untimely_response_rows_also_timely_no": (
            round(n_untimely_response_and_timely_no / n_untimely_response_rows, 4)
            if n_untimely_response_rows
            else None
        ),
        "n_timely_no_rows": n_timely_no_rows,
        "pct_timely_no_rows_also_untimely_response": (
            round(n_untimely_response_and_timely_no / n_timely_no_rows, 4) if n_timely_no_rows else None
        ),
        "n_intervention_required_and_timely_no": n_intervention_required_and_timely_no,
        # Denominator is the outcome_1-positive count (n_intervention_required), NOT
        # n_timely_no_rows - "pct of intervention_required rows that are ALSO timely_no", matching
        # BP5 Gate 1's own field naming and its real recorded value (84/10511 = 0.008), not
        # 84/3227 = 0.026 (a different, differently-named quantity this module got wrong on its
        # first pass - caught by sandbox cross-check against Gate 1's real policy.json before
        # delivery, never delivered with the bug).
        "pct_intervention_required_rows_also_timely_no": (
            round(n_intervention_required_and_timely_no / n_outcome_1_positive_rows, 4)
            if n_outcome_1_positive_rows
            else None
        ),
    }


def feature_lineage_table() -> pl.DataFrame:
    """The driver-field lineage table Gate 2's own exit criterion requires - one row per candidate
    driver field, its real column, its planned Gate 3/4 transform, and its null handling; plus the
    CONTROL field, both outcome fields (TARGET rows, never input features), and every BARRED
    column. Built from this module's own constants (never hand-duplicated elsewhere) so it can
    never drift from what the pipeline actually does."""
    rows: list[dict] = []
    for col in FEATURE_COLS_CATEGORICAL:
        sentinel = NULL_SENTINEL_MAP.get(col)
        rows.append(
            {
                "driver_field": f"{col} (one-hot + chi-square/logistic-regression driver, Gate 3/4)",
                "source_column": col,
                "transform": "one-hot encoding (Gate 3/4); tested against BOTH outcome_1 and outcome_2",
                "null_handling": (
                    f"real nulls filled with sentinel category '{sentinel}'"
                    if sentinel
                    else "no real nulls in this column (BP5 Gate 1 policy.json, re-verified live)"
                ),
            }
        )
    rows.append(
        {
            "driver_field": "Company_freq",
            "source_column": COMPANY_COL,
            "transform": (
                "frequency encoding (fit on train only, Gate 3/4); tested against BOTH outcomes; "
                "unseen test-time companies get frequency 0 - never fabricated"
            ),
            "null_handling": "no real nulls in this column (BP5 Gate 1 policy.json, re-verified live)",
        }
    )
    rows.append(
        {
            "driver_field": f"{CONTROL_FIELD} (CONTROL ONLY - never a named primary driver)",
            "source_column": CONTROL_FIELD,
            "transform": (
                "one-hot encoding as a control dimension only (Gate 3/4) - per BP5 Gate 1's own "
                "explicit scoping choice, never reported as a named 'product/issue/process' driver"
            ),
            "null_handling": f"real nulls filled with sentinel category '{NULL_SENTINEL_MAP[CONTROL_FIELD]}'",
        }
    )
    rows.append(
        {
            "driver_field": "outcome_1_intervention_required (TARGET 1 of 2, not a driver)",
            "source_column": "Company response to consumer",
            "transform": "binary outcome rule, reused verbatim from BP3 Gate 1 - never used as an input driver",
            "null_handling": "n/a - this is outcome 1, not an input driver field",
        }
    )
    rows.append(
        {
            "driver_field": "outcome_2_timely_response_failure (TARGET 2 of 2, not a driver)",
            "source_column": "Timely response?",
            "transform": "binary outcome rule, new to BP5 - never used as an input driver",
            "null_handling": "n/a - this is outcome 2, not an input driver field",
        }
    )
    for barred_col in BARRED_COLUMNS:
        rows.append(
            {
                "driver_field": "(none - barred)",
                "source_column": barred_col,
                "transform": "EXCLUDED from the candidate driver set entirely - see BP5 Gate 1 policy.json leakage_rules",
                "null_handling": "n/a - column is never read into any candidate driver field",
            }
        )
    return pl.DataFrame(rows)


def build_bp5_driver_gold_layer(cfpb_lazy: pl.LazyFrame, out_dir: str | Path) -> dict:
    """Write the BP5 CFPB-with-both-outcomes Gold layer to Parquet (WARP) - every real row tagged
    with outcome_1_intervention_required/outcome_1_exclusion_reason and
    outcome_2_timely_response_failure/outcome_2_exclusion_reason, none dropped here (mirrors BP3
    Gate 2's build_bp3_escalation_gold_layer pattern; filtering to either outcome's own trainable
    subset is a Gate 3 decision per outcome, not made here)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gold_path = out_dir / "cfpb_root_cause_driver_gold.parquet"
    cfpb_lazy.sink_parquet(gold_path)
    rows_written = pl.scan_parquet(gold_path).select(pl.len()).collect().item()

    return {
        "cfpb_driver_gold_path": str(gold_path),
        "cfpb_driver_gold_rows_written": rows_written,
    }
