"""
src/features/bp7_decision_engine_features.py — Customer360 Navigator

BP7 (Customer360 Navigator Decision Engine) shared re-scoring / join module, built AT Gate 2
(HYPER, matching BP3's and BP4's own precedent of building the shared module at Gate 2 rather than
retroactively at Gate 6 - see those modules' own docstrings for the identical rationale). Master
Plan Section 5.1/7 (BP7 methodology), Section 8 Gate 2 (Data Verification & Feature/Taxonomy
Engineering).

Why this module exists (the real Gate 1 -> Gate 2 design gap it resolves): BP7 Gate 1's own real,
live-run policy.json (`target_definition.known_dependency_gaps`) found that BP1/BP2/BP3's real
`gate5_decision_records.csv` artifacts are each that BP's own independent held-out TEST-SPLIT
predictions, keyed only by a `row_index` local to that BP's own split - live-verified to carry no
`Complaint ID` column. Three independently-split BPs cannot be joined row-for-row from those
artifacts alone. This module implements Gate 1's own named resolution: a "BP7-owned common
re-scoring pass" - never retraining, never touching any upstream BP's own already-real-run-
confirmed Gate 3/4/5 notebook, champion, hyperparameters, or threshold, purely re-applying each
BP's already-validated, already-persisted inference pipeline (src/models/model_persistence.py) to
the FULL real CFPB population, keyed by the real, always-present `Complaint ID` column - never a
join across three disjoint test splits.

A real, load-bearing finding this module's design had to resolve honestly (BP1 is NOT re-scored
here, unlike BP2/BP3): BP1's own real, live-run Gate 1 policy.json states plainly that "no CFPB
row-level data is ever joined into BANKING77 training or evaluation data" and that "BP1's
trainable text classifier is built and evaluated on BANKING77 alone, because the CFPB extract used
in this project has no narrative/complaint-text column" (docs/data_dictionary/RAW_DATA_MANIFEST.md
Finding 2, re-confirmed live: the real 15-column CFPB extract has no free-text field).
`model_persistence.predict_bp1()` takes raw `texts` - and CFPB has no real text to hand it.
Synthesizing pseudo-text from structured fields (e.g. "Product. Sub-product. Issue. Sub-issue.")
would be feeding the model an input distribution it was never fit or evaluated on and presenting
whatever it returns as a real prediction - exactly the fabricated-result-for-a-missing-input
pattern this project's zero-fabrication rule (and BP1 Gate 1's own leakage_rules) forbid. BP1's
real, already-computed, CFPB-row-level contribution is instead the taxonomy CROSSWALK (not a model
prediction) BP1 Gate 2 already built and persisted at
`data/processed/cfpb_common_taxonomy_gold.parquet` (`common_taxonomy_bucket`, real ~6.55% in-scope
coverage, BP4 Gate 1's own live-verified figure) - carried forward here as optional, structurally-
grounded context, exactly as BP7 Gate 1's policy.json scopes it (`OPTIONAL_CONTEXT_ONLY`). See
`attach_bp1_taxonomy_context()` below.

BP2/BP3 ARE re-scored via `model_persistence.predict_bp2()`/`predict_bp3()`, because both operate
on real structured CFPB columns present on every real row (Product, Sub-product, Issue, Sub-issue,
State, Submitted via, Company, [+ common_taxonomy_bucket for BP2]) - a valid, real input for every
row, not a fabricated one. This module reuses each BP's own already-delivered, already real-run-
confirmed null-handling convention EXACTLY as that BP's own Gate 3 notebook defines it (verified
live against that notebook's own delivered source, not assumed to be identical across BPs):
  - BP2 (`build_bp2_raw_feature_frame`): every FEATURE_COLS_CATEGORICAL + Company value cast to
    string and null-filled with the single literal "MISSING" - byte-for-byte the same rule
    `bp2_customer_friction_classification_g3_model_benchmark.ipynb`'s own delivered Section 5 uses
    inline (`.fill_null("MISSING")`), replicated here (not imported - BP2's Gate-2/3-era code
    predates the "build the shared module at Gate 2" convention BP3/BP4 established later, so no
    shared function exists yet to import for this specific step; every other BP2 step this module
    needs (the classifier/preprocessor/company-freq walk itself) reuses `model_persistence.py`
    unmodified, never reimplemented).
  - BP3 (`build_bp3_raw_feature_frame`): reuses `features.bp3_escalation_features.
    fill_categorical_nulls_expr()` and `NULL_SENTINEL_MAP` UNMODIFIED (true HYPER reuse, since
    BP3's own Gate 2 already centralized this) - per-column sentinels (MISSING_SUB_PRODUCT /
    MISSING_SUB_ISSUE / MISSING_STATE), not BP2's generic "MISSING".

Bundle-availability handling (zero-fabrication, matching `src/services/bp4_decision_service.py`'s
own established 503-not-a-fake-result idiom, itself built on `services.service_common.
ModelBundleHandle` - reused UNMODIFIED here via `load_bp2_bp3_bundles()` rather than
reimplemented): if a BP's real persisted joblib bundle is not present on disk (or fails to load),
that BP's contribution is reported as `NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED` for every row -
never a mock/fabricated prediction, and this module (and the Gate 2 notebook that calls it) still
completes successfully on whatever real inputs ARE available.

BP4 join (`join_bp4_cluster_tier`): BP4 fits no model - its real Gate 5 output
(`gate5_cluster_decision_report.csv`) is already at the issue-cluster grain BP7 Gate 1's policy.json
names, joined onto complaint-level rows via the real, always-present CLUSTER_KEY (reused UNMODIFIED
from `features.bp4_journey_features.CLUSTER_KEY`, never retyped). An unmatched row's BP4 fields
(only those fields) are reported `UNSCORED_MISSING_UPSTREAM_INPUT`, never the whole row dropped.

BP5 context (`build_bp5_context_lookup` / `attach_bp5_context`): BP5 Gate 5's own real output
(`gate5_prioritized_root_cause_report_outcome_{1,2}_*.json`) is an OUTCOME-level "prioritized
root-cause report" (its own real top-K field/category association rankings), not a per-complaint
prediction - no row-level join is structurally possible (confirmed live: neither file carries a
`Complaint ID` or any per-row key). This module instead builds a small, real, structurally-grounded
lookup from each file's own real `category_level_findings_by_field` (field, category) pairs and
flags, for every complaint row, whether that row's own real Product/Sub-product/Issue/Sub-issue/
Submitted via value is one of BP5's own real reported top-K association categories for each of the
two real outcome fields - qualitative context, never a numeric weight, never a causal claim (BP5's
own `association_not_causation_disclaimer`, carried forward verbatim into every value this module
emits).

This module is import-only shared logic (HYPER). It performs no I/O side effects at import time
and is never executed by Claude - only the user runs it, in their own environment, per the
project's execution-boundary rule.

Public functions/constants:
  CLUSTER_KEY                                    -> re-exported from features.bp4_journey_features
  BARRED_COLUMNS                                  list[str]
  BP1_OUT_OF_SCOPE_BUCKET_LITERAL                 str
  UNSCORED_MISSING_UPSTREAM_INPUT                 str  (sentinel)
  NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED          str  (sentinel)
  load_bp2_bp3_bundles(project_root)              -> dict[str, ModelBundleHandle]
  attach_bp1_taxonomy_context(cfpb_lazy, gold_taxonomy_path) -> pl.LazyFrame
  build_bp2_raw_feature_frame(pl_df)              -> pd.DataFrame
  build_bp3_raw_feature_frame(pl_df)              -> pd.DataFrame
  score_bp2_population(handle, pl_df, batch_size) -> pd.DataFrame
  score_bp3_population(handle, pl_df, batch_size) -> pd.DataFrame
  join_bp4_cluster_tier(complaint_lazy, bp4_csv_path) -> pl.LazyFrame
  build_bp5_context_lookup(outcome1_json_path, outcome2_json_path) -> pl.DataFrame
  attach_bp5_context(complaint_lazy, bp5_lookup_pl)   -> pl.LazyFrame
  feature_lineage_table()                         -> pl.DataFrame
  coverage_report(gold_pl)                        -> dict

  --- Gate 3 additions (decision-rule-scheme benchmark - built AT Gate 3, extending this module
  rather than creating a second one, matching this project's own "one shared module per BP"
  convention) ---
  DEFAULT_INTERVENTION_THRESHOLD                  float
  BP4_JOINED_STATUS                               str
  CANDIDATE_NAMES                                 list[str]
  load_bp2_friction_ordinal_ranks(project_root)   -> dict[str, int]
  load_upstream_validated_metrics(project_root)   -> dict
  compute_bp4_join_coverage(gold_pl)              -> float
  compute_bp2_bp3_correlation(gold_pl)            -> dict
  attach_normalized_signal_columns(gold_lazy, friction_ordinal_ranks) -> pl.LazyFrame
  compute_candidate_raw_weights(upstream_metrics, bp4_coverage, bp2_bp3_cramers_v) -> dict
  normalize_candidate_weights(raw_weights)        -> dict[str, float]
  score_priority_rule(gold_lazy, weights, threshold) -> pl.LazyFrame
  benchmark_candidate(scored_pl, candidate_name, weights_normalized, weights_raw) -> dict
  fit_lr_diagnostic(gold_pl, sample_size, random_state) -> dict
  check_disparate_impact_carry_forward(gold_pl_columns) -> dict
  select_champion(benchmark_rows, bp2_bp3_cramers_v)    -> str

  --- Gate 4 additions (statistical validation & explainability - built AT Gate 4, extending this
  module rather than creating a second one) ---
  N_DEFAULT_BOOTSTRAP                             int
  bootstrap_ci_for_rate(values, n_bootstrap, random_state) -> dict
  build_bp3_agreement_crosstab(scored_pl)         -> dict
  compute_priority_score_contribution_decomposition(scored_pl, weights_normalized) -> pl.DataFrame
  summarize_contribution_decomposition(decomp_pl) -> dict
  reconfirm_no_barred_columns_in_gold_layer(gold_pl_columns) -> dict
  KNOWN_TAGS_GROUPS                               list[str]
  load_bp3_gold_tags_group(bp3_gold_path)         -> pl.DataFrame
  attach_tags_group_for_audit(scored_pl, tags_group_pl) -> pl.DataFrame
  compute_disparate_impact_audit(audited_pl, group_col) -> dict

  --- Gate 5 additions (decision layer & full-population reporting - built AT Gate 5, extending
  this module rather than creating a second one) ---
  FINAL_OUTPUT_COLUMNS                            list[str]
  build_full_population_decision_records(scored_pl, decomp_pl, tags_group_pl) -> pl.DataFrame
  summarize_recommended_action_breakdown(records_pl) -> pl.DataFrame
  summarize_bp4_tier_intervention_crosstab(records_pl) -> pl.DataFrame
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import polars as pl

from features.bp3_escalation_features import (
    NULL_SENTINEL_MAP as BP3_NULL_SENTINEL_MAP,
    FEATURE_COLS_CATEGORICAL as BP3_FEATURE_COLS_CATEGORICAL,
    COMPANY_COL as BP3_COMPANY_COL,
    fill_categorical_nulls_expr as bp3_fill_categorical_nulls_expr,
)
from features.bp4_journey_features import CLUSTER_KEY
from models.model_persistence import predict_bp2, predict_bp3
from services.service_common import ModelBundleHandle

# ---------------------------------------------------------------------------
# BP7's own barred-input list - the exact 5 columns BP7 Gate 1's real, live-run policy.json
# leakage_rules bars from every BP7 input, re-verified live (never trusted from Gate 1 alone) by
# the notebook's own Section 4 barred-column re-check. `Complaint ID` is NOT barred - it is BP7's
# own real, required join key, present and unique on every real CFPB row (re-verified live, never
# assumed). `Tags` and `ZIP code` are read only for the live demographic-adjacent re-check itself
# (never as a model input), matching BP1-4's own precedent.
# ---------------------------------------------------------------------------
BARRED_COLUMNS: list[str] = [
    "Company response to consumer",
    "Timely response?",
    "Date received",
    "Date sent to company",
    "Tags",
]

# The real sentinel literal BP1 Gate 2's crosswalk (`taxonomy.taxonomy_mapper.cfpb_bucket_expr`)
# writes for a CFPB row with no plausible BANKING77 overlap - live-verified against the real
# cfpb_common_taxonomy_gold.parquet (Section 5 of the Gate 2 notebook re-checks this literal
# against the real file rather than trusting it hardcoded here).
BP1_OUT_OF_SCOPE_BUCKET_LITERAL: str = "OUT_OF_SCOPE_NO_BANKING77_OVERLAP"

# Zero-fabrication sentinels (BP7 Gate 1 policy.json leakage_rules: "No BP7 output row may be
# produced for a complaint outside the real join coverage... reported as
# UNSCORED_MISSING_UPSTREAM_INPUT, never silently defaulted").
UNSCORED_MISSING_UPSTREAM_INPUT: str = "UNSCORED_MISSING_UPSTREAM_INPUT"
NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED: str = "NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED"

DEFAULT_BATCH_SIZE: int = 200_000


# ---------------------------------------------------------------------------
# Bundle loading - reuses services.service_common.ModelBundleHandle UNMODIFIED (HYPER); never
# raises past this call, never fabricates a bundle, honestly reports which of BP2/BP3 are
# available for this real run.
# ---------------------------------------------------------------------------
def load_bp2_bp3_bundles(project_root: str | Path) -> dict[str, ModelBundleHandle]:
    """Return {'bp2': ModelBundleHandle, 'bp3': ModelBundleHandle} for the real persisted champion
    bundles at their real, documented paths under `models/`. Each handle's `.is_loaded` reports
    real, live-checked availability - never assumed. BP1 is deliberately not included here: see
    this module's own docstring for why BP1 has no valid `predict_bp1()` input on CFPB data."""
    project_root = Path(project_root)
    specs = {
        "bp2": (
            project_root / "models" / "bp2_customer_friction_classification" / "bp2_champion_bundle.joblib",
            project_root / "models" / "bp2_customer_friction_classification" / "bp2_model_metadata.json",
        ),
        "bp3": (
            project_root / "models" / "bp3_complaint_escalation_prediction" / "bp3_champion_bundle.joblib",
            project_root / "models" / "bp3_complaint_escalation_prediction" / "bp3_model_metadata.json",
        ),
    }
    return {
        bp_id: ModelBundleHandle(bp_id, joblib_path, metadata_path)
        for bp_id, (joblib_path, metadata_path) in specs.items()
    }


# ---------------------------------------------------------------------------
# BP1 - taxonomy-crosswalk context only (never model inference - see module docstring).
# ---------------------------------------------------------------------------
def attach_bp1_taxonomy_context(cfpb_lazy: pl.LazyFrame, gold_taxonomy_path: str | Path) -> pl.LazyFrame:
    """Left-join the real, already-computed `common_taxonomy_bucket` (Complaint ID keyed) from
    BP1 Gate 2's own real Gold layer onto `cfpb_lazy`, and derive `bp1_context_status` - never a
    `predicted_label`/`confidence_top1` field (those never exist for a CFPB row - see module
    docstring). If the Gold parquet is not present on disk, every row gets
    NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for bp1_context_status (BP1 Gate 2 not yet real-run) -
    the notebook still completes on the rest of the real, available upstream contributions."""
    gold_taxonomy_path = Path(gold_taxonomy_path)
    if not gold_taxonomy_path.exists():
        return cfpb_lazy.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("common_taxonomy_bucket"),
            pl.lit(NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED).alias("bp1_context_status"),
        )
    taxonomy_lazy = pl.scan_parquet(gold_taxonomy_path).select(["Complaint ID", "common_taxonomy_bucket"])
    joined = cfpb_lazy.join(taxonomy_lazy, on="Complaint ID", how="left")
    joined = joined.with_columns(
        pl.when(pl.col("common_taxonomy_bucket").is_null())
        .then(pl.lit(UNSCORED_MISSING_UPSTREAM_INPUT))
        .when(pl.col("common_taxonomy_bucket") == BP1_OUT_OF_SCOPE_BUCKET_LITERAL)
        .then(pl.lit("BP1_NO_TAXONOMY_MAPPING"))
        .otherwise(pl.lit("BP1_TAXONOMY_CONTEXT_AVAILABLE"))
        .alias("bp1_context_status")
    )
    return joined


# ---------------------------------------------------------------------------
# BP2 - re-scoring the full population via model_persistence.predict_bp2(), BP2's OWN real
# null-handling convention (generic "MISSING" literal - see module docstring for the exact
# citation of where BP2's real delivered notebook does this).
# ---------------------------------------------------------------------------
def build_bp2_raw_feature_frame(pl_df: pl.DataFrame) -> pd.DataFrame:
    feature_cols_categorical = [
        "Product",
        "Sub-product",
        "Issue",
        "Sub-issue",
        "State",
        "Submitted via",
        "common_taxonomy_bucket",
    ]
    company_col = "Company"
    cols = feature_cols_categorical + [company_col]
    pdf = pl_df.select(cols).to_pandas()
    for c in cols:
        pdf[c] = pdf[c].astype("string").fillna("MISSING")
    return pdf


def score_bp2_population(
    handle: ModelBundleHandle, pl_df: pl.DataFrame, batch_size: int = DEFAULT_BATCH_SIZE
) -> pd.DataFrame:
    """Re-score every row of `pl_df` with BP2's real persisted champion bundle, batched (WARP -
    never one giant dense array at once), returning a DataFrame of
    [Complaint ID, bp2_predicted_label, bp2_confidence]. Caller must have already confirmed
    `handle.is_loaded`."""
    complaint_ids = pl_df["Complaint ID"].to_list()
    X_raw = build_bp2_raw_feature_frame(pl_df)
    n = len(X_raw)
    labels: list[Any] = []
    confidences: list[float] = []
    for start in range(0, n, batch_size):
        chunk = X_raw.iloc[start : start + batch_size]
        result = predict_bp2(handle.bundle, chunk)
        labels.extend(result["predicted_label"])
        confidences.extend(result["confidence"])
    return pd.DataFrame(
        {"Complaint ID": complaint_ids, "bp2_predicted_label": labels, "bp2_confidence": confidences}
    )


# ---------------------------------------------------------------------------
# BP3 - re-scoring the full population via model_persistence.predict_bp3(), reusing BP3's OWN
# Gate-2-built null-handling helpers UNMODIFIED (true HYPER reuse).
# ---------------------------------------------------------------------------
def build_bp3_raw_feature_frame(pl_df: pl.DataFrame) -> pd.DataFrame:
    cols = BP3_FEATURE_COLS_CATEGORICAL + [BP3_COMPANY_COL]
    filled = pl_df.lazy().with_columns(bp3_fill_categorical_nulls_expr()).select(cols).collect()
    pdf = filled.to_pandas()
    for c in cols:
        pdf[c] = pdf[c].astype("string")
        sentinel = BP3_NULL_SENTINEL_MAP.get(c)
        if sentinel is not None:
            pdf[c] = pdf[c].fillna(sentinel)
    return pdf


def score_bp3_population(
    handle: ModelBundleHandle, pl_df: pl.DataFrame, batch_size: int = DEFAULT_BATCH_SIZE
) -> pd.DataFrame:
    """Re-score every row of `pl_df` with BP3's real persisted champion bundle, batched. Returns
    [Complaint ID, bp3_predicted_label, bp3_probability_positive_class]. Caller must have already
    confirmed `handle.is_loaded`."""
    complaint_ids = pl_df["Complaint ID"].to_list()
    X_raw = build_bp3_raw_feature_frame(pl_df)
    n = len(X_raw)
    labels: list[Any] = []
    probs: list[float] = []
    for start in range(0, n, batch_size):
        chunk = X_raw.iloc[start : start + batch_size]
        result = predict_bp3(handle.bundle, chunk)
        labels.extend(result["predicted_label"])
        probs.extend(result["probability_positive_class"])
    return pd.DataFrame(
        {
            "Complaint ID": complaint_ids,
            "bp3_predicted_label": labels,
            "bp3_probability_positive_class": probs,
        }
    )


# ---------------------------------------------------------------------------
# BP4 - real cluster-level Gate 5 output, joined onto complaint rows via the real CLUSTER_KEY
# (reused unmodified from features.bp4_journey_features - never retyped).
# ---------------------------------------------------------------------------
BP4_FIELDS: list[str] = [
    "recurring_flag",
    "high_volume_flag",
    "review_priority_tier",
    "review_priority_score",
    "reason_codes",
]


def join_bp4_cluster_tier(complaint_lazy: pl.LazyFrame, bp4_csv_path: str | Path) -> pl.LazyFrame:
    """Left-join BP4's real gate5_cluster_decision_report.csv onto `complaint_lazy` via the real
    (Company, Product, Sub-product, Issue, Sub-issue) CLUSTER_KEY. If the real BP4 artifact is not
    present, every row gets NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for bp4_join_status (matching
    BP2/BP3's own naming even though BP4 has no joblib bundle - the sentinel's meaning here is
    'upstream artifact not yet real-run', the same real-world condition). An unmatched cluster key
    (rare/none expected - verified live by the notebook) gets UNSCORED_MISSING_UPSTREAM_INPUT for
    the BP4 fields specifically, never the whole row dropped."""
    bp4_csv_path = Path(bp4_csv_path)
    if not bp4_csv_path.exists():
        out = complaint_lazy
        for f in BP4_FIELDS:
            out = out.with_columns(pl.lit(None, dtype=pl.Utf8).alias(f"bp4_{f}"))
        return out.with_columns(pl.lit(NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED).alias("bp4_join_status"))

    # BP4's real CSV has no dtype schema of its own (unlike the CFPB extract's CFPB_DTYPES), so its
    # CLUSTER_KEY columns come back as plain Utf8 - cast both sides to Utf8 for the join rather
    # than assume `complaint_lazy`'s own dtype (Categorical, inherited from CFPB_DTYPES upstream)
    # already matches. A real bug this module's own sandbox verification caught before delivery.
    bp4_lazy = pl.scan_csv(bp4_csv_path).select(CLUSTER_KEY + BP4_FIELDS)
    bp4_lazy = bp4_lazy.rename({f: f"bp4_{f}" for f in BP4_FIELDS})
    complaint_lazy = complaint_lazy.with_columns([pl.col(k).cast(pl.Utf8) for k in CLUSTER_KEY])
    bp4_lazy = bp4_lazy.with_columns([pl.col(k).cast(pl.Utf8) for k in CLUSTER_KEY])
    joined = complaint_lazy.join(bp4_lazy, on=CLUSTER_KEY, how="left")
    joined = joined.with_columns(
        pl.when(pl.col("bp4_review_priority_tier").is_null())
        .then(pl.lit(UNSCORED_MISSING_UPSTREAM_INPUT))
        .otherwise(pl.lit("BP4_JOINED"))
        .alias("bp4_join_status")
    )
    return joined


# ---------------------------------------------------------------------------
# BP5 - real, outcome-level qualitative association context (never a row-level join - see module
# docstring for why one is structurally impossible).
# ---------------------------------------------------------------------------
BP5_CANDIDATE_FIELDS: list[str] = ["Product", "Sub-product", "Issue", "Sub-issue", "Submitted via"]


def build_bp5_context_lookup(
    outcome1_json_path: str | Path, outcome2_json_path: str | Path
) -> Optional[pl.DataFrame]:
    """Parse the real `category_level_findings_by_field` block out of BOTH of BP5's real Gate 5
    outcome-level artifacts into one small lookup table:
    [outcome_field, driver_field, category, rank, odds_ratio_vs_reference, log_odds_ratio]. Returns
    None if either real artifact is not present (BP5 Gate 5 not yet real-run) - callers must
    handle that by reporting BP5 context as NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED, never inventing
    a finding."""
    outcome1_json_path = Path(outcome1_json_path)
    outcome2_json_path = Path(outcome2_json_path)
    if not outcome1_json_path.exists() or not outcome2_json_path.exists():
        return None

    rows: list[dict[str, Any]] = []
    for path in (outcome1_json_path, outcome2_json_path):
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        outcome_field = doc["outcome_field"]
        for driver_field, findings in doc["category_level_findings_by_field"].items():
            if driver_field not in BP5_CANDIDATE_FIELDS:
                continue
            for finding in findings:
                rows.append(
                    {
                        "outcome_field": outcome_field,
                        "driver_field": driver_field,
                        "category": finding["category"],
                        "rank": finding["rank"],
                        "odds_ratio_vs_reference": finding["odds_ratio_vs_reference"],
                        "log_odds_ratio": finding["log_odds_ratio"],
                    }
                )
    if not rows:
        return pl.DataFrame(
            schema={
                "outcome_field": pl.Utf8,
                "driver_field": pl.Utf8,
                "category": pl.Utf8,
                "rank": pl.Int64,
                "odds_ratio_vs_reference": pl.Float64,
                "log_odds_ratio": pl.Float64,
            }
        )
    return pl.DataFrame(rows)


def attach_bp5_context(complaint_lazy: pl.LazyFrame, bp5_lookup_pl: Optional[pl.DataFrame]) -> pl.LazyFrame:
    """Attach `bp5_outcome_1_context` / `bp5_outcome_2_context` (each one of
    'ASSOCIATED_DRIVER_CATEGORY' | 'NOT_IN_TOP_K_ASSOCIATION_LIST' |
    NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED) plus a matching `bp5_outcome_{n}_evidence` string
    (empty when not associated) - built ONLY from BP5's own real, already-computed top-K
    association lookup (`build_bp5_context_lookup`), never invented. A row is
    ASSOCIATED_DRIVER_CATEGORY for an outcome if ANY of its own real
    Product/Sub-product/Issue/Sub-issue/Submitted via values matches one of BP5's own real
    reported top-K categories for that field, for that outcome."""
    if bp5_lookup_pl is None:
        return complaint_lazy.with_columns(
            pl.lit(NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED).alias("bp5_outcome_1_context"),
            pl.lit("").alias("bp5_outcome_1_evidence"),
            pl.lit(NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED).alias("bp5_outcome_2_context"),
            pl.lit("").alias("bp5_outcome_2_evidence"),
        )

    out = complaint_lazy
    for outcome_idx, outcome_field in (
        (1, "outcome_1_intervention_required"),
        (2, "outcome_2_timely_response_failure"),
    ):
        outcome_lookup = bp5_lookup_pl.filter(pl.col("outcome_field") == outcome_field)
        match_exprs: list[pl.Expr] = []
        evidence_exprs: list[pl.Expr] = []
        for field in BP5_CANDIDATE_FIELDS:
            field_lookup = outcome_lookup.filter(pl.col("driver_field") == field)
            categories = field_lookup["category"].to_list()
            if not categories:
                continue
            is_match = pl.col(field).is_in(categories)
            match_exprs.append(is_match)
            evidence_exprs.append(
                pl.when(is_match)
                .then(pl.lit(f"{field}=") + pl.col(field).cast(pl.Utf8))
                .otherwise(pl.lit(""))
            )
        if not match_exprs:
            out = out.with_columns(
                pl.lit("NOT_IN_TOP_K_ASSOCIATION_LIST").alias(f"bp5_outcome_{outcome_idx}_context"),
                pl.lit("").alias(f"bp5_outcome_{outcome_idx}_evidence"),
            )
            continue
        any_match = match_exprs[0]
        for m in match_exprs[1:]:
            any_match = any_match | m
        evidence_concat = evidence_exprs[0]
        for e in evidence_exprs[1:]:
            evidence_concat = evidence_concat + pl.lit("|") + e
        out = out.with_columns(
            pl.when(any_match)
            .then(pl.lit("ASSOCIATED_DRIVER_CATEGORY"))
            .otherwise(pl.lit("NOT_IN_TOP_K_ASSOCIATION_LIST"))
            .alias(f"bp5_outcome_{outcome_idx}_context"),
            evidence_concat.str.replace_all(r"^\|+|\|+$", "").alias(f"bp5_outcome_{outcome_idx}_evidence"),
        )
    return out


# ---------------------------------------------------------------------------
# Feature lineage + coverage reporting (Gate 2's own named exit-criterion artifacts).
# ---------------------------------------------------------------------------
def feature_lineage_table() -> pl.DataFrame:
    """BP7 Gate 2's own feature-lineage table (mirrors BP3/BP4/BP5's own
    engineered_feature/source_column/transform/null_handling shape exactly)."""
    rows = [
        {
            "engineered_feature": "bp1_context_status / common_taxonomy_bucket",
            "source_column": "(Complaint-ID-keyed join onto "
            "data/processed/cfpb_common_taxonomy_gold.parquet)",
            "transform": "BP1 Gate 2's own real taxonomy crosswalk, carried forward as context only - "
            "never a model prediction (see module docstring: BP1 has no valid predict_bp1() input on "
            "CFPB, which has no narrative-text column).",
            "null_handling": "Gold parquet absent -> NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for every row.",
        },
        {
            "engineered_feature": "bp2_predicted_label / bp2_confidence",
            "source_column": "Product, Sub-product, Issue, Sub-issue, State, Submitted via, "
            "common_taxonomy_bucket, Company",
            "transform": "BP2's real persisted champion bundle (model_persistence.predict_bp2()), "
            "re-applied to the full real CFPB population, keyed by Complaint ID.",
            "null_handling": "categorical nulls filled with literal 'MISSING' (BP2 Gate 3's own real "
            "convention); bundle absent -> NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for every row.",
        },
        {
            "engineered_feature": "bp3_predicted_label / bp3_probability_positive_class",
            "source_column": "Product, Sub-product, Issue, Sub-issue, State, Submitted via, Company",
            "transform": "BP3's real persisted champion bundle (model_persistence.predict_bp3()), "
            "re-applied to the full real CFPB population, keyed by Complaint ID.",
            "null_handling": "BP3's own NULL_SENTINEL_MAP (MISSING_SUB_PRODUCT / MISSING_SUB_ISSUE / "
            "MISSING_STATE, reused unmodified); bundle absent -> "
            "NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for every row.",
        },
        {
            "engineered_feature": "bp4_review_priority_tier / bp4_review_priority_score / "
            "bp4_recurring_flag / bp4_high_volume_flag / bp4_reason_codes",
            "source_column": "Company, Product, Sub-product, Issue, Sub-issue (CLUSTER_KEY)",
            "transform": "Left-join of BP4's real gate5_cluster_decision_report.csv onto complaint rows "
            "via CLUSTER_KEY (reused unmodified from features.bp4_journey_features).",
            "null_handling": "unmatched cluster key -> UNSCORED_MISSING_UPSTREAM_INPUT for BP4 fields "
            "only; artifact absent -> NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for every row.",
        },
        {
            "engineered_feature": "bp5_outcome_1_context / bp5_outcome_2_context (+ evidence)",
            "source_column": "Product, Sub-product, Issue, Sub-issue, Submitted via",
            "transform": "Membership check against BP5's real, outcome-level top-K "
            "category_level_findings_by_field lookup (Gate 5 artifacts) - qualitative association "
            "context only, never a numeric weight, never a row-level join (structurally impossible: "
            "BP5's real artifacts carry no per-complaint key).",
            "null_handling": "either real BP5 Gate 5 artifact absent -> "
            "NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for every row.",
        },
    ]
    return pl.DataFrame(rows)


def coverage_report(gold_pl: pl.DataFrame) -> dict:
    """Real per-field coverage statistics over the real full population (Gate 2's own
    'zero nulls silently dropped' disclosure convention - every field's real status distribution,
    never a single aggregate hiding a silently-dropped subset)."""
    n = gold_pl.height
    report: dict[str, Any] = {"n_rows": n}
    for col, label in (
        ("bp1_context_status", "bp1"),
        ("bp2_predicted_label", "bp2"),
        ("bp3_predicted_label", "bp3"),
        ("bp4_join_status", "bp4"),
        ("bp5_outcome_1_context", "bp5_outcome_1"),
        ("bp5_outcome_2_context", "bp5_outcome_2"),
    ):
        if col not in gold_pl.columns:
            continue
        if label in ("bp2", "bp3"):
            status_col = gold_pl[col]
            available = int((~status_col.is_null()).sum())
            unavailable = n - available
            report[label] = {
                "n_available": available,
                "n_unavailable": unavailable,
                "pct_available": (round(100.0 * available / n, 4) if n else 0.0),
            }
        else:
            vc = gold_pl[col].value_counts().sort(col)
            report[label] = {row[col]: row["count"] for row in vc.to_dicts()}
    return report


# =============================================================================================
# GATE 3 ADDITIONS - decision-rule-scheme benchmark (built AT Gate 3, extending this module
# rather than creating a second one - HYPER, matching every other BP's own "one shared module,
# extended gate over gate" precedent). Master Plan Section 5.1/7 (BP7 methodology): BP7 Gate 1's
# own real, live-run policy.json is explicit that priority_score/intervention_flag/
# recommended_action are a documented, DETERMINISTIC weighted rule - "never a retrained
# black-box classifier producing the final score directly" - and that "a Gate 3/4 scope decision
# MAY evaluate an interpretable model (logistic regression specifically) as one additional
# reason-coded input field into the rule framework - the framework, its weights, its thresholds,
# and the final decision stay the deterministic, auditable layer regardless."
#
# Gate 1's own policy.json also left one open empirical question for Gate 3/4 to check, verbatim
# (assumptions[0]): "BP2's LOW_FRICTION class and BP3's positive class (intervention_required=1)
# are both defined on the identical real CFPB value 'Closed with monetary relief' - not leakage
# between BP2/BP3 (each already disclosed this at its own Gate 1), but BP7 must not assume their
# predicted outputs are independent, additively-combinable signals; Gate 3/4 must empirically
# check this correlation before finalizing weights." `compute_bp2_bp3_correlation()` below is
# that real, live check, and its real, live-measured Cramer's V feeds the `correlation_aware` /
# `correlation_aware_plus_lr_diagnostic` candidates' weight-redundancy discount - never a
# hardcoded correlation figure.
#
# BP1 (taxonomy context) and BP5 (outcome-level qualitative association) NEVER enter
# priority_score as a numeric weight, per Gate 1's own upstream_input_contract ("OPTIONAL_CONTEXT
# ONLY" for BP1; BP5's own module docstring above: "never a numeric weight, never a causal
# claim"). Only BP2 (friction tier), BP3 (intervention probability), and BP4 (cluster review-
# priority tier/score) are weighted signals - BP1/BP5 are recorded into `reason_codes` as context
# only, exactly as Gate 1 scoped them.
# =============================================================================================

DEFAULT_INTERVENTION_THRESHOLD: float = 0.5
BP4_JOINED_STATUS: str = "BP4_JOINED"
CANDIDATE_NAMES: list[str] = [
    "equal_weight_baseline",
    "domain_informed_weighted",
    "correlation_aware",
    "correlation_aware_plus_lr_diagnostic",
]


# ---------------------------------------------------------------------------
# BP2's own real, already-governance-reviewed severity taxonomy - read LIVE from
# configs/bp2_friction_severity_taxonomy.yaml every call, never hardcoded/cached here, so a
# future amendment to BP2's own taxonomy (a Gate 2 human-review artifact, per that file's own
# header) is picked up automatically rather than silently going stale.
# ---------------------------------------------------------------------------
def load_bp2_friction_ordinal_ranks(project_root: str | Path) -> dict[str, int]:
    """Return {friction_label: ordinal_rank} read live from BP2's own real
    configs/bp2_friction_severity_taxonomy.yaml (`severity_classes.*.ordinal_rank`) - the single
    source of truth for BP2's LOW < MEDIUM < MEDIUM_HIGH < HIGH friction ordering. Raises if the
    file is missing rather than assuming an order BP2 itself might have since amended."""
    import yaml

    path = Path(project_root) / "configs" / "bp2_friction_severity_taxonomy.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found - BP2's own real friction-severity taxonomy config is required to "
            "derive bp2_predicted_label's ordinal ranking; it must not be guessed here."
        )
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    severity_classes = doc["severity_classes"]
    return {label: int(info["ordinal_rank"]) for label, info in severity_classes.items()}


# ---------------------------------------------------------------------------
# Each upstream BP's own real, already-computed, already real-run-confirmed validated-performance
# metric - read LIVE from that BP's own delivered artifact every call, never hardcoded as a
# literal number in this module (a real number copied into source and never re-checked is exactly
# the kind of drift LESSONS_LEARNED_APPLIED.md's config-marker rework was built to prevent).
# ---------------------------------------------------------------------------
def load_upstream_validated_metrics(project_root: str | Path) -> dict[str, Any]:
    """Return {"bp2_f1_macro": float, "bp2_f1_macro_source": str, "bp3_pr_auc": float,
    "bp3_pr_auc_source": str} - BP2's real Gate 3 champion held-out test macro-avg F1 (from its
    own already-delivered `gate3_champion_test_classification_report.json`) and BP3's real Gate 4
    held-out test PR-AUC point estimate (from its own already-delivered
    `gate4_statistical_validation.json`), both read live. Raises FileNotFoundError naming the
    missing artifact if either upstream BP has not real-run that gate - never substitutes an
    invented placeholder metric."""
    project_root = Path(project_root)
    bp2_path = (
        project_root
        / "notebooks"
        / "bp2_customer_friction_classification"
        / "artifacts"
        / "gate3_champion_test_classification_report.json"
    )
    bp3_path = (
        project_root
        / "notebooks"
        / "bp3_complaint_escalation_prediction"
        / "artifacts"
        / "gate4_statistical_validation.json"
    )
    for p in (bp2_path, bp3_path):
        if not p.exists():
            raise FileNotFoundError(
                f"{p} not found - the upstream BP this domain-informed weight depends on has not "
                "real-run the gate that produces this real metric. Run that BP's gate for real "
                "before BP7 Gate 3, rather than inventing a placeholder metric here."
            )
    with open(bp2_path, "r", encoding="utf-8") as f:
        bp2_report = json.load(f)
    with open(bp3_path, "r", encoding="utf-8") as f:
        bp3_report = json.load(f)
    return {
        "bp2_f1_macro": float(bp2_report["macro avg"]["f1-score"]),
        "bp2_f1_macro_source": str(bp2_path.relative_to(project_root).as_posix()),
        "bp3_pr_auc": float(bp3_report["held_out_test_pr_auc_point_estimate"]),
        "bp3_pr_auc_source": str(bp3_path.relative_to(project_root).as_posix()),
    }


def compute_bp4_join_coverage(gold_pl: pl.DataFrame) -> float:
    """Real, live-computed fraction of BP7's own Gate 2 Gold-layer rows with
    `bp4_join_status == BP4_JOINED_STATUS`. BP4 fits no classifier and has no held-out predictive
    metric comparable to BP2's F1/BP3's PR-AUC - this real coverage fraction is the disclosed
    heuristic this module uses as BP4's own domain-informed weight basis instead (never an
    invented accuracy number for a BP that produces no such metric)."""
    n = gold_pl.height
    if n == 0:
        return 0.0
    n_joined = int((gold_pl["bp4_join_status"] == BP4_JOINED_STATUS).sum())
    return round(n_joined / n, 6)


def compute_bp2_bp3_correlation(gold_pl: pl.DataFrame) -> dict[str, Any]:
    """The real, live empirical check BP7 Gate 1's own policy.json (assumptions) named
    explicitly: does BP2's friction-tier prediction carry redundant signal with BP3's
    intervention-probability prediction, given both are partly defined on the identical real CFPB
    resolution value? Reuses `models.bp5_driver_association.chi_square_cramers_v` UNMODIFIED
    (HYPER, true cross-BP reuse of BP5's own real chi-square/Cramer's V toolkit) on
    `bp2_predicted_label` (categorical) vs `bp3_predicted_label` (0/1) - a real chi-square test of
    independence plus Cramer's V effect size. Also reports the literal, specific real number
    Gate 1's own assumptions text named: P(bp3_predicted_label==1 | bp2_predicted_label==
    'LOW_FRICTION') against the real overall base rate, since LOW_FRICTION and BP3's positive
    class are the two classes defined on the identical real CFPB value."""
    from models.bp5_driver_association import chi_square_cramers_v

    df = gold_pl.select(["bp2_predicted_label", "bp3_predicted_label"]).to_pandas()
    chi2_result = chi_square_cramers_v(df, "bp2_predicted_label", "bp3_predicted_label")

    low_friction_mask = df["bp2_predicted_label"] == "LOW_FRICTION"
    n_low_friction = int(low_friction_mask.sum())
    overall_positive_rate = float(df["bp3_predicted_label"].mean())
    low_friction_positive_rate = (
        float(df.loc[low_friction_mask, "bp3_predicted_label"].mean()) if n_low_friction else None
    )

    return {
        "chi_square_cramers_v": chi2_result,
        "n_low_friction_rows": n_low_friction,
        "overall_bp3_positive_rate": round(overall_positive_rate, 6),
        "low_friction_bp3_positive_rate": (
            round(low_friction_positive_rate, 6) if low_friction_positive_rate is not None else None
        ),
        "interpretation": (
            "BP7 Gate 1's own policy.json (assumptions) named this exact open question - whether "
            "BP2's LOW_FRICTION class and BP3's positive class, both defined on the identical "
            "real CFPB value 'Closed with monetary relief', are independent, additively-"
            "combinable signals. cramers_v above real-quantifies the overall association between "
            "the two full prediction fields; low_friction_bp3_positive_rate real-quantifies the "
            "specific redundancy Gate 1 flagged, against overall_bp3_positive_rate as the real "
            "base-rate reference. Neither number is a causal claim - both are real, live-computed "
            "associations on BP7's own Gate 2 Gold layer. cramers_v feeds the correlation_aware / "
            "correlation_aware_plus_lr_diagnostic candidates' weight-redundancy discount below - "
            "this function does not itself decide independence or dependence a priori."
        ),
    }


# ---------------------------------------------------------------------------
# Per-row normalized [0,1] signal columns the weighted rule combines. BP1/BP5 deliberately absent
# here - Gate 1's policy.json scopes them to context/reason_codes only, never a numeric weight.
# ---------------------------------------------------------------------------
def _ordinal_map_expr(col: str, mapping: dict[str, int]) -> pl.Expr:
    """A pl.when/then/otherwise chain over a small, real, live-loaded category->rank mapping -
    avoids any polars-version-dependent `.replace()` API and avoids a per-row Python
    `map_elements` call (WARP: no per-row Python loops over a real 1M-row column)."""
    expr = pl.lit(None, dtype=pl.Int64)
    for label, rank in mapping.items():
        expr = pl.when(pl.col(col) == label).then(pl.lit(rank, dtype=pl.Int64)).otherwise(expr)
    return expr


def attach_normalized_signal_columns(
    gold_lazy: pl.LazyFrame, friction_ordinal_ranks: dict[str, int]
) -> pl.LazyFrame:
    """Attach `_bp2_norm` (BP2's own real ordinal friction rank / max real rank, taxonomy read
    live - see `load_bp2_friction_ordinal_ranks`), `_bp3_norm` (BP3's own real
    `bp3_probability_positive_class` - already a real [0,1] probability, no transform needed), and
    `_bp4_norm` (BP4's own real `bp4_review_priority_score` / 3, only when
    `bp4_join_status == BP4_JOINED_STATUS` - null, never 0, for an unjoined row, so
    `score_priority_rule` below renormalizes over whichever signals are actually available for
    that row rather than silently understating an unscored row's priority)."""
    max_rank = max(friction_ordinal_ranks.values())
    if max_rank <= 0:
        raise ValueError(f"friction_ordinal_ranks has a non-positive max rank: {friction_ordinal_ranks}")
    return gold_lazy.with_columns(
        (_ordinal_map_expr("bp2_predicted_label", friction_ordinal_ranks) / max_rank).alias("_bp2_norm"),
        pl.col("bp3_probability_positive_class").alias("_bp3_norm"),
        pl.when(pl.col("bp4_join_status") == BP4_JOINED_STATUS)
        .then(pl.col("bp4_review_priority_score") / 3.0)
        .otherwise(None)
        .alias("_bp4_norm"),
    )


# ---------------------------------------------------------------------------
# Candidate rule schemes - raw (pre-normalization) weights. Every number traces to a real,
# already-computed upstream artifact (`upstream_metrics`, `bp4_coverage`) or a real, live-computed
# association statistic (`bp2_bp3_cramers_v`) - never invented. `equal_weight_baseline` is an
# honestly-labeled naive baseline (plays the same role BP1-3's Gate 3 "basic/baseline" candidate
# plays in those benchmarks), not itself claimed to be principled.
# ---------------------------------------------------------------------------
def compute_candidate_raw_weights(
    upstream_metrics: dict[str, Any], bp4_coverage: float, bp2_bp3_cramers_v: float
) -> dict[str, dict[str, float]]:
    """Return {candidate_name: {"bp2": raw_w, "bp3": raw_w, "bp4": raw_w}} for every candidate in
    CANDIDATE_NAMES, NOT yet normalized to sum to 1 (`normalize_candidate_weights` does that per
    candidate). `correlation_aware` and `correlation_aware_plus_lr_diagnostic` apply the identical
    `(1 - bp2_bp3_cramers_v)` multiplicative redundancy discount to BP2's and BP3's own raw
    weights only (BP4 is not part of the correlated pair Gate 1 flagged) - the real,
    live-measured Cramer's V from `compute_bp2_bp3_correlation`, never a hardcoded discount."""
    f1_bp2 = upstream_metrics["bp2_f1_macro"]
    pr_auc_bp3 = upstream_metrics["bp3_pr_auc"]
    redundancy_discount = 1.0 - bp2_bp3_cramers_v
    correlation_aware_weights = {
        "bp2": f1_bp2 * redundancy_discount,
        "bp3": pr_auc_bp3 * redundancy_discount,
        "bp4": bp4_coverage,
    }
    return {
        "equal_weight_baseline": {"bp2": 1.0, "bp3": 1.0, "bp4": 1.0},
        "domain_informed_weighted": {"bp2": f1_bp2, "bp3": pr_auc_bp3, "bp4": bp4_coverage},
        "correlation_aware": dict(correlation_aware_weights),
        "correlation_aware_plus_lr_diagnostic": dict(correlation_aware_weights),
    }


def normalize_candidate_weights(raw_weights: dict[str, float]) -> dict[str, float]:
    """Normalize one candidate's {"bp2":.., "bp3":.., "bp4":..} raw weights to sum to 1."""
    total = sum(raw_weights.values())
    if total <= 0:
        raise ValueError(f"raw weights sum to {total} (must be positive) - cannot normalize: {raw_weights}")
    return {k: v / total for k, v in raw_weights.items()}


# ---------------------------------------------------------------------------
# The deterministic weighted rule itself - priority_score / intervention_flag / reason_codes /
# recommended_action. Identical formula shape for every candidate; only `weights` differs.
# ---------------------------------------------------------------------------
def _build_reason_codes_expr() -> pl.Expr:
    """Pipe-separated, per-row, every real field that fed (or was context for) this row's score -
    BP7 Gate 1's own explicit Section 5.1/7 requirement ("every output row records which upstream
    BP fields and thresholds drove its priority_score/intervention_flag"). Mirrors BP4's own
    `gate5_cluster_decision_report.csv` reason_codes pipe-separated convention and this module's
    own `attach_bp5_context()` empty-segment-collapse idiom."""
    parts = [
        pl.lit("BP2_TIER=") + pl.col("bp2_predicted_label"),
        pl.lit("BP3_PROB=") + pl.col("bp3_probability_positive_class").round(4).cast(pl.Utf8),
        pl.when(pl.col("bp4_join_status") == BP4_JOINED_STATUS)
        .then(pl.lit("BP4_TIER=") + pl.col("bp4_review_priority_tier"))
        .otherwise(pl.lit("BP4_TIER=UNSCORED")),
        pl.when(pl.col("bp4_recurring_flag").fill_null(False))
        .then(pl.lit("BP4_RECURRING"))
        .otherwise(pl.lit("")),
        pl.when(pl.col("bp4_high_volume_flag").fill_null(False))
        .then(pl.lit("BP4_HIGH_VOLUME"))
        .otherwise(pl.lit("")),
        pl.lit("BP1_CONTEXT=") + pl.col("bp1_context_status"),
        pl.lit("BP5_OUTCOME1=") + pl.col("bp5_outcome_1_context"),
        pl.lit("BP5_OUTCOME2=") + pl.col("bp5_outcome_2_context"),
    ]
    expr = parts[0]
    for p in parts[1:]:
        expr = expr + pl.lit("|") + p
    return expr.str.replace_all(r"\|+", "|").str.strip_chars("|")


def _recommended_action_expr() -> pl.Expr:
    """Deterministic, reason-code-keyed lookup - never GenAI (Gate 1 policy.json
    target_definition.output_fields.recommended_action: 'never GenAI ... UDAAP Section 9 does not
    map BP7'). Evaluated in this fixed precedence order, first match wins."""
    return (
        pl.when(pl.col("priority_score").is_null())
        .then(pl.lit(UNSCORED_MISSING_UPSTREAM_INPUT))
        .when(pl.col("intervention_flag") & pl.col("bp4_recurring_flag").fill_null(False))
        .then(pl.lit("ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER"))
        .when(pl.col("intervention_flag") & (pl.col("bp4_review_priority_tier") == "HIGH"))
        .then(pl.lit("ESCALATE_SENIOR_REVIEWER"))
        .when(pl.col("intervention_flag"))
        .then(pl.lit("PRIORITY_QUEUE_REVIEW"))
        .otherwise(pl.lit("STANDARD_QUEUE"))
    )


def score_priority_rule(
    gold_lazy: pl.LazyFrame,
    weights: dict[str, float],
    threshold: float = DEFAULT_INTERVENTION_THRESHOLD,
) -> pl.LazyFrame:
    """Attach `priority_score` (weighted average of whichever of `_bp2_norm`/`_bp3_norm`/
    `_bp4_norm` are actually available for that row, renormalized over the available subset only
    - never a fabricated value for a missing signal, never silently defaulted to 0; null,
    reported as UNSCORED_MISSING_UPSTREAM_INPUT downstream, only in the structurally-impossible
    case that none of the three are available for a row), `intervention_flag` (real threshold on
    `priority_score`), `reason_codes`, and `recommended_action` - all four are Gate 1's own named
    BP7 output_fields. Caller must have already run `attach_normalized_signal_columns`."""
    w_bp2, w_bp3, w_bp4 = weights["bp2"], weights["bp3"], weights["bp4"]
    numerator = (
        pl.col("_bp2_norm").fill_null(0.0) * pl.lit(w_bp2)
        + pl.col("_bp3_norm").fill_null(0.0) * pl.lit(w_bp3)
        + pl.col("_bp4_norm").fill_null(0.0) * pl.lit(w_bp4)
    )
    denominator = (
        pl.when(pl.col("_bp2_norm").is_not_null()).then(pl.lit(w_bp2)).otherwise(pl.lit(0.0))
        + pl.when(pl.col("_bp3_norm").is_not_null()).then(pl.lit(w_bp3)).otherwise(pl.lit(0.0))
        + pl.when(pl.col("_bp4_norm").is_not_null()).then(pl.lit(w_bp4)).otherwise(pl.lit(0.0))
    )
    out = gold_lazy.with_columns(
        pl.when(denominator > 0.0).then(numerator / denominator).otherwise(None).alias("priority_score")
    )
    out = out.with_columns(
        (pl.col("priority_score") >= threshold).fill_null(False).alias("intervention_flag")
    )
    out = out.with_columns(_build_reason_codes_expr().alias("reason_codes"))
    out = out.with_columns(_recommended_action_expr().alias("recommended_action"))
    return out


# ---------------------------------------------------------------------------
# Per-candidate benchmark metrics - real, structural, auditability-relevant properties (no
# fabricated "ground truth" accuracy: `customer360_priority_decision` has no labeled CFPB column).
# ---------------------------------------------------------------------------
def benchmark_candidate(
    scored_pl: pl.DataFrame,
    candidate_name: str,
    weights_normalized: dict[str, float],
    weights_raw: dict[str, float],
) -> dict[str, Any]:
    """Real coverage, score-distribution sanity, BP3-coherence, and reason-code-completeness
    metrics for one already-scored candidate DataFrame (must already carry `priority_score`,
    `intervention_flag`, `reason_codes`, `bp3_predicted_label`). Never a precision/recall/F1
    "accuracy" claim - `customer360_priority_decision` has no labeled CFPB column to score
    against; `bp3_agreement_rate` is disclosed as a coherence sanity check against BP3's own
    already-validated prediction, not an accuracy metric, and is expected to run higher for a
    candidate that weights BP3 more heavily by construction - one complementary signal among
    several here, never the sole criterion."""
    n = scored_pl.height
    score_col = scored_pl["priority_score"]
    n_scored = int(score_col.is_not_null().sum())
    coverage_pct = round(100.0 * n_scored / n, 6) if n else 0.0
    scored_only = score_col.drop_nulls()
    n_nan_or_inf = int(scored_only.is_nan().sum() + scored_only.is_infinite().sum()) if n_scored else 0
    score_min = float(scored_only.min()) if n_scored else None
    score_max = float(scored_only.max()) if n_scored else None
    score_std = float(scored_only.std()) if n_scored and n_scored > 1 else None
    score_bounded_0_1 = bool(
        n_scored > 0
        and score_min is not None
        and score_max is not None
        and score_min >= -1e-9
        and score_max <= 1.0 + 1e-9
    )
    score_non_degenerate = bool(score_std is not None and score_std > 1e-9)

    reason_codes_col = scored_pl["reason_codes"]
    n_reason_codes_nonempty = int(
        ((reason_codes_col.is_not_null()) & (reason_codes_col.str.len_chars() > 0)).sum()
    )
    reason_codes_all_nonempty = bool(n == n_reason_codes_nonempty)
    avg_reason_codes_per_row = (
        float(reason_codes_col.drop_nulls().str.split("|").list.len().mean())
        if n_reason_codes_nonempty
        else 0.0
    )

    intervention_col = scored_pl["intervention_flag"]
    bp3_col = scored_pl["bp3_predicted_label"]
    both_present = intervention_col.is_not_null() & bp3_col.is_not_null()
    n_compared = int(both_present.sum())
    bp3_positive = bp3_col == 1
    n_agree = int(((intervention_col == bp3_positive) & both_present).sum())
    bp3_agreement_rate = round(n_agree / n_compared, 6) if n_compared else None

    structurally_passes = bool(
        coverage_pct == 100.0
        and n_nan_or_inf == 0
        and score_bounded_0_1
        and score_non_degenerate
        and reason_codes_all_nonempty
    )

    return {
        "candidate": candidate_name,
        "n_rows": n,
        "n_scored": n_scored,
        "coverage_pct": coverage_pct,
        "n_nan_or_inf": n_nan_or_inf,
        "score_min": score_min,
        "score_max": score_max,
        "score_std": score_std,
        "score_bounded_0_1": score_bounded_0_1,
        "score_non_degenerate": score_non_degenerate,
        "reason_codes_all_nonempty": reason_codes_all_nonempty,
        "avg_reason_codes_per_row": round(avg_reason_codes_per_row, 4),
        "n_intervention_flagged": int(intervention_col.sum()) if n_scored else 0,
        "intervention_flag_rate": (round(float(intervention_col.mean()), 6) if n_scored else None),
        "bp3_agreement_n_compared": n_compared,
        "bp3_agreement_rate": bp3_agreement_rate,
        "weight_bp2_normalized": round(weights_normalized["bp2"], 6),
        "weight_bp3_normalized": round(weights_normalized["bp3"], 6),
        "weight_bp4_normalized": round(weights_normalized["bp4"], 6),
        "raw_weight_bp2": round(weights_raw["bp2"], 6),
        "raw_weight_bp3": round(weights_raw["bp3"], 6),
        "raw_weight_bp4": round(weights_raw["bp4"], 6),
        "lr_diagnostic_held_out_roc_auc": None,
        "lr_diagnostic_n_rows_fit_sample": None,
        "structurally_passes": structurally_passes,
    }


# ---------------------------------------------------------------------------
# Optional interpretable-model reason-coded input - Gate 1's policy.json explicitly permits this
# ("A Gate 3/4 scope decision MAY evaluate an interpretable model (logistic regression
# specifically) as one additional reason-coded input field into the rule framework"). Fit ONLY on
# already-available real upstream PREDICTED fields (never a raw CFPB column Gate 1/2 barred), and
# diagnostic only - never substituted for priority_score/intervention_flag/recommended_action.
# ---------------------------------------------------------------------------
def fit_lr_diagnostic(
    gold_pl: pl.DataFrame, sample_size: int = 200_000, random_state: int = 42
) -> dict[str, Any]:
    """Fit a bounded, real `sklearn.linear_model.LogisticRegression` predicting BP3's own real,
    already-computed `bp3_predicted_label` from BP2's/BP4's/BP1's OTHER already-computed fields
    (`bp2_confidence`, `bp4_review_priority_score`, and a `bp1_context_available` flag derived
    from `bp1_context_status`) - never a raw CFPB column, never any field Gate 1's leakage_rules
    bar. Purely diagnostic: surfaces which of BP2/BP4/BP1's OWN fields correlate with BP3's own
    assessment; its real, held-out ROC-AUC/accuracy and coefficients are reported as one
    additional disclosed reason-coded input per Gate 1's policy.json, NEVER substituted for
    priority_score/intervention_flag/recommended_action, which stay this gate's deterministic
    weighted rule regardless (Gate 1's explicit, non-negotiable constraint)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    df = gold_pl.select(
        ["bp2_confidence", "bp4_review_priority_score", "bp1_context_status", "bp3_predicted_label"]
    ).to_pandas()
    df = df.dropna(subset=["bp3_predicted_label"])
    if len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=random_state)

    # bp4_review_priority_score is null for an unjoined row - an explicit, disclosed sentinel
    # (-1.0, outside BP4's own real [0,3] range) rather than a fabricated 0, so this diagnostic
    # model can itself distinguish "unjoined" from "joined with the lowest real BP4 score".
    df["bp4_review_priority_score"] = df["bp4_review_priority_score"].fillna(-1.0)
    df["bp1_context_available"] = (df["bp1_context_status"] == "BP1_TAXONOMY_CONTEXT_AVAILABLE").astype(int)

    feature_cols = ["bp2_confidence", "bp4_review_priority_score", "bp1_context_available"]
    X = df[feature_cols]
    y = df["bp3_predicted_label"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=random_state, stratify=y
    )
    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state)
    model.fit(X_train, y_train)
    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)

    return {
        "n_rows_fit_sample": int(len(df)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "features": feature_cols,
        "coefficients": {c: round(float(v), 6) for c, v in zip(feature_cols, model.coef_[0].tolist())},
        "intercept": round(float(model.intercept_[0]), 6),
        "held_out_roc_auc": round(float(roc_auc_score(y_test, y_proba)), 6),
        "held_out_accuracy": round(float(accuracy_score(y_test, y_pred)), 6),
        "disclosure": (
            "Diagnostic only - predicts BP3's own already-computed bp3_predicted_label from "
            "BP2/BP4/BP1's OTHER real fields (never a raw CFPB column, never a barred field), "
            "surfacing which of those fields correlate with BP3's own assessment. Reported as one "
            "additional disclosed reason-coded input per BP7 Gate 1's policy.json "
            "(target_definition.combining_methodology), never substituted for priority_score/"
            "intervention_flag/recommended_action, which stay this gate's deterministic weighted "
            "rule regardless."
        ),
    }


# ---------------------------------------------------------------------------
# Disparate-impact carry-forward check (BP7 Gate 1's own compliance_touchpoint.ecoa_reg_b
# commitment) - real, live check of whether it can be performed AT Gate 3, or must be honestly
# deferred to Gate 4, never silently skipped either way.
# ---------------------------------------------------------------------------
def check_disparate_impact_carry_forward(gold_pl_columns: list[str]) -> dict[str, Any]:
    """BP3's own real Gate 4/5 disparate-impact check (adverse_impact_ratio_recomputed=0.139,
    flagged=True, grouped by BP3's own real `tags_group`) is a real, already-closed governance
    finding BP7 Gate 1's policy.json commits to carrying forward and re-checking against BP7's own
    champion `intervention_flag`. That real re-check needs a Complaint-ID-keyed `tags_group` (or
    equivalent) column on BP7's own Gate 2 Gold layer. BP7 Gate 2's real re-scoring join
    (`score_bp3_population` above) does not produce one - `tags_group` lives only in BP3's own
    held-out TEST-SPLIT `gate5_decision_records.csv`, keyed by a `row_index` local to that split,
    not `Complaint ID` (this module's own docstring). Reconstructing `tags_group` at BP7 Gate 3
    would require reading the raw, barred `Tags` column as a BP7 input, which Gate 1's
    leakage_rules structurally bars ("'Tags' is barred from every BP7 priority-score input").
    This function performs the real, live column-presence check rather than assuming either way,
    and if `tags_group` is absent, returns an honest deferral - never a silent skip - to Gate 4,
    exactly as Gate 1's own policy.json already committed to doing."""
    tags_group_present = "tags_group" in gold_pl_columns
    return {
        "tags_group_column_present_in_gate2_gold_layer": tags_group_present,
        "real_gold_layer_columns_checked": list(gold_pl_columns),
        "disparate_impact_carry_forward_check_performed_at_gate3": tags_group_present,
        "deferred_to_gate4": not tags_group_present,
        "deferral_reason": (
            None
            if tags_group_present
            else (
                "BP7 Gate 2's real re-scoring join does not preserve BP3's own tags_group "
                "grouping (confirmed live above by column-presence check on the real Gate 2 Gold "
                "layer) - it lives only in BP3's own held-out test-split gate5_decision_records.csv "
                "(row_index-keyed, no Complaint ID). Reconstructing tags_group at BP7 Gate 3 would "
                "require reading the raw, barred 'Tags' column as a BP7 input (Gate 1's "
                "leakage_rules bars this). Per BP7 Gate 1's own policy.json "
                "compliance_touchpoint.ecoa_reg_b, this disparate-impact-style check on BP7's own "
                "champion intervention_flag, grouped by tags_group, is deferred to Gate 4 - "
                "disclosed here explicitly, never silently skipped."
            )
        ),
    }


# ---------------------------------------------------------------------------
# Champion selection - recomputed live from real, per-candidate metrics every time, never
# hardcoded by candidate name (this project's own established idiom - see BP4 Gate 3's own
# `CHAMPION = min(timing_results, key=lambda n: timing_results[n]["min_seconds"])`).
# ---------------------------------------------------------------------------
def select_champion(benchmark_rows: dict[str, dict[str, Any]], bp2_bp3_cramers_v: float) -> str:
    """Champion = the structurally-passing candidate (see `benchmark_candidate`'s
    `structurally_passes`) that allocates the LEAST combined weight-share to the empirically
    correlated BP2+BP3 pair, scaled by the real, live-measured Cramer's V between them
    (`redundancy_double_counting_score = bp2_bp3_cramers_v * (weight_bp2_normalized +
    weight_bp3_normalized)`, lower is better) - this directly operationalizes Gate 1's own mandate
    to "let the finding inform whether/how the benchmark's candidate weighting schemes handle
    BP2/BP3 jointly ... choose an approach that doesn't naively double-weight correlated
    signals". Ties broken by higher `avg_reason_codes_per_row` (richer real disclosure), then
    higher `bp3_agreement_rate` (secondary coherence signal), then by whether the candidate has a
    real fitted LR diagnostic available (`lr_diagnostic_held_out_roc_auc is not None` - a real,
    structural fact about that candidate's own benchmark row, never a name comparison) - prefers
    the candidate carrying more real, disclosed auditability content on a genuine tie. Raises if
    no candidate passes every structural check (a genuine gate failure, never worked around by
    loosening a check)."""
    eligible = {name: row for name, row in benchmark_rows.items() if row["structurally_passes"]}
    if not eligible:
        raise ValueError(
            "No candidate rule scheme passed every structural check (coverage/sanity/reason-code "
            "completeness) - cannot select a champion. This is a genuine gate failure, never "
            "worked around by loosening a structural check."
        )

    def _sort_key(name: str) -> tuple[float, float, float, int]:
        row = eligible[name]
        redundancy = bp2_bp3_cramers_v * (row["weight_bp2_normalized"] + row["weight_bp3_normalized"])
        richness = row["avg_reason_codes_per_row"]
        coherence = row["bp3_agreement_rate"] if row["bp3_agreement_rate"] is not None else 0.0
        has_lr_diagnostic = int(row["lr_diagnostic_held_out_roc_auc"] is not None)
        return (redundancy, -richness, -coherence, -has_lr_diagnostic)

    return min(eligible, key=_sort_key)


# =============================================================================================
# GATE 4 ADDITIONS - statistical validation & explainability (built AT Gate 4, extending this
# module rather than creating a second one - HYPER, matching every other BP's own "one shared
# module, extended gate over gate" precedent, and this module's own Gate 2 -> Gate 3 precedent).
# Master Plan's generic Gate 4 row (Section 8's Gate table): output = "Bootstrap CI, calibration,
# confusion matrix, SHAP sample"; exit criteria = "All checks numeric and reproducible; leakage
# re-confirmed"; compliance touchpoint = "Independent-style validation record (SR 11-7 second-line
# analog); disparate-impact check where applicable (ECOA/Reg B)". BP7 adapts each output the same
# way BP5/BP6 Gate 4 each adapted it for their own non-classic-classifier nature (see those gates'
# own notebooks): BP7 has no trained classifier and no labeled ground-truth column for
# `customer360_priority_decision` (its own Gate 3 `benchmark_candidate()` docstring already
# disclosed this) - so "calibration" and "confusion matrix" map onto real structural analogs
# below, never a fabricated accuracy claim.
#
# The substantive compliance item this gate resolves: BP7 Gate 1's own real, live-run policy.json
# (`compliance_touchpoint.ecoa_reg_b`) committed explicitly to "re-running a disparate-impact-style
# check on BP7's own final priority_score/intervention_flag, grouped by the same tags_group
# dimension [BP3 used], at BP7's own Gate 4". Gate 3's real, live check
# (`check_disparate_impact_carry_forward` above) found BP7's own Gate 2 Gold layer does not carry
# `tags_group` (or raw `Tags`) and honestly deferred the check here rather than reconstructing it
# from the barred `Tags` column as a Gate 3 input. This Gate 4 section resolves that deferral for
# real: BP3's own real, already-governance-approved Gold layer
# (`data/processed/cfpb_intervention_escalation_gold.parquet`) already carries a Complaint-ID-keyed
# `Tags` passthrough column for the FULL real population (not just BP3's own held-out test split) -
# confirmed live, not assumed, by this module's own Gate 4 loader below - because BP3's own Gate 2
# Gold-layer build read the raw CFPB extract directly and BP3's own Gate 4 already established the
# real, governance-approved precedent of reading `Tags` **read-only, never as a model feature**,
# purely for a post-hoc disparate-impact monitoring lens
# (`bp3_complaint_escalation_prediction_g4_statistical_validation_explainability.ipynb`, Section 7:
# `feature_data["Tags"] = df_pl["Tags"].cast(pl.Utf8).fill_null("NO_TAG").to_list()` /
# `X_test_raw["Tags"]` used only in the disparate-impact section, never one-hot encoded, never fit
# on). BP7 Gate 4 follows the identical precedent, one level removed: it reads `Complaint ID` +
# `Tags` from BP3's own already-real-run-confirmed, already-governance-reviewed Gold-layer artifact
# (never BP7 reading the raw CFPB extract itself, and never touching any BP1-6 source file), builds
# `tags_group` with BP3's own byte-for-byte identical convention (cast Utf8, fill_null "NO_TAG"),
# and left-joins it onto BP7's own already-scored population **strictly for audit grouping, after
# `priority_score`/`intervention_flag`/`recommended_action` are already computed** - `tags_group`
# never enters `attach_normalized_signal_columns()` or `score_priority_rule()` above, and this
# section's own `reconfirm_no_barred_columns_in_gold_layer()` re-verifies live that BP7's own
# scoring Gold layer (`cfpb_decision_engine_context_gold.parquet`) still carries no `Tags` column
# at all. This resolves Gate 1's own leakage_rules text ("'Tags' is barred from every BP7 [scoring]
# input") against Gate 1's own separately-stated Gate 4 commitment to a downstream, decision-blind
# monitoring use of the same `tags_group` dimension BP3's own closed governance investigation used
# - the same input-vs-audit-only distinction BP3's own Gate 4 already drew and BP7 Gate 1's own
# `compliance_touchpoint.ecoa_reg_b` text explicitly anticipated ("a monitoring signal for a human
# reviewer... exactly BP3's own stated limitation").
#
# Public additions:
#   bootstrap_ci_for_rate(values, n_bootstrap, random_state)          -> dict
#   build_bp3_agreement_crosstab(scored_pl)                            -> dict
#   compute_priority_score_contribution_decomposition(scored_pl, weights_normalized) -> pl.DataFrame
#   summarize_contribution_decomposition(decomp_pl)                    -> dict
#   reconfirm_no_barred_columns_in_gold_layer(gold_pl_columns)         -> dict
#   KNOWN_TAGS_GROUPS                                                  list[str]
#   load_bp3_gold_tags_group(bp3_gold_path)                            -> pl.DataFrame
#   attach_tags_group_for_audit(scored_pl, tags_group_pl)              -> pl.DataFrame
#   compute_disparate_impact_audit(audited_pl, group_col)              -> dict
# =============================================================================================

N_DEFAULT_BOOTSTRAP: int = 1000


def bootstrap_ci_for_rate(
    values, n_bootstrap: int = N_DEFAULT_BOOTSTRAP, random_state: int = 42
) -> dict[str, Any]:
    """Real percentile-bootstrap 95% CI for the mean of a 0/1 (or boolean) array - used for both
    `intervention_flag_rate` and `bp3_agreement_rate`. `values` must already be a real, live
    numpy array (never a fabricated/simulated one) - the caller extracts it from the real, already
    live-scored Gold layer. Resampling is with replacement, at the SAME size as the real input
    array, `n_bootstrap` times (disclosed, never silently narrowed for speed)."""
    import numpy as np

    values = np.asarray(values, dtype=np.float64)
    n = len(values)
    if n == 0:
        raise ValueError("bootstrap_ci_for_rate called with an empty array - cannot resample.")
    point_estimate = float(values.mean())
    rng = np.random.RandomState(random_state)
    boot = np.empty(n_bootstrap, dtype=np.float64)
    for b in range(n_bootstrap):
        idx = rng.randint(0, n, size=n)
        boot[b] = values[idx].mean()
    ci_lower = float(np.percentile(boot, 2.5))
    ci_upper = float(np.percentile(boot, 97.5))
    return {
        "point_estimate": round(point_estimate, 6),
        "ci_lower_95": round(ci_lower, 6),
        "ci_upper_95": round(ci_upper, 6),
        "n_bootstrap": int(n_bootstrap),
        "n_rows_resampled": int(n),
        "random_state": int(random_state),
    }


# ---------------------------------------------------------------------------
# Confusion-matrix analog. `customer360_priority_decision` has no labeled ground-truth column
# (Gate 3's own `benchmark_candidate()` docstring), so this is honestly built and labeled as an
# AGREEMENT/reference table against BP3's own already-validated `bp3_predicted_label` - never
# presented as a true accuracy confusion matrix.
# ---------------------------------------------------------------------------
def build_bp3_agreement_crosstab(scored_pl: pl.DataFrame) -> dict[str, Any]:
    """Real 2x2 cross-tab of `intervention_flag` (True/False) x `bp3_predicted_label` (1/0) over
    every real row where both are available. Honestly labeled: this is a coherence/agreement
    reference table against BP3's own prediction, not a true confusion matrix (there is no
    labeled ground truth for `customer360_priority_decision`) - mirrors this module's own
    `benchmark_candidate()` `bp3_agreement_rate` disclosure."""
    sub = scored_pl.filter(pl.col("bp3_predicted_label").is_not_null())
    n_compared = sub.height
    if n_compared == 0:
        return {
            "n_compared": 0,
            "intervention_true_bp3_positive": 0,
            "intervention_true_bp3_negative": 0,
            "intervention_false_bp3_positive": 0,
            "intervention_false_bp3_negative": 0,
            "agreement_rate": None,
        }
    grouped = sub.group_by(["intervention_flag", "bp3_predicted_label"]).len()
    counts: dict[tuple[bool, int], int] = {}
    for row in grouped.to_dicts():
        counts[(bool(row["intervention_flag"]), int(row["bp3_predicted_label"]))] = int(row["len"])

    def _get(flag: bool, label: int) -> int:
        return counts.get((flag, label), 0)

    n_true_pos = _get(True, 1)
    n_true_neg = _get(False, 0)
    n_agree = n_true_pos + n_true_neg
    return {
        "n_compared": n_compared,
        "intervention_true_bp3_positive": n_true_pos,
        "intervention_true_bp3_negative": _get(True, 0),
        "intervention_false_bp3_positive": _get(False, 1),
        "intervention_false_bp3_negative": n_true_neg,
        "agreement_rate": round(n_agree / n_compared, 6),
        "disclosure": (
            "Agreement/reference table against BP3's own already-validated bp3_predicted_label, "
            "NOT a true confusion matrix - customer360_priority_decision has no labeled "
            "ground-truth CFPB column. bp3_predicted_label is a real, already-validated upstream "
            "prediction used as a disclosed reference point, not ground truth for BP7's own "
            "decision (same limitation this module's own benchmark_candidate() already stated)."
        ),
    }


# ---------------------------------------------------------------------------
# Explainability - exact per-row contribution decomposition of the deterministic weighted-average
# priority_score formula. A genuine strength over SHAP here (disclosed as such): this is an EXACT
# decomposition of a known, transparent formula, never an approximation.
# ---------------------------------------------------------------------------
def compute_priority_score_contribution_decomposition(
    scored_pl: pl.DataFrame, weights_normalized: dict[str, float]
) -> pl.DataFrame:
    """Return [Complaint ID, priority_score, contribution_bp2, contribution_bp3,
    contribution_bp4] where the three contribution columns sum EXACTLY to priority_score (within
    floating-point tolerance) for every scored row - the identical per-row renormalize-over-
    available-signals arithmetic `score_priority_rule()` above already performs, decomposed back
    out into its three additive terms rather than only returning their sum. Caller must have
    already run `attach_normalized_signal_columns()` on `scored_pl` (the `_bp2_norm`/`_bp3_norm`/
    `_bp4_norm` columns must be present)."""
    w_bp2, w_bp3, w_bp4 = weights_normalized["bp2"], weights_normalized["bp3"], weights_normalized["bp4"]
    denominator = (
        pl.when(pl.col("_bp2_norm").is_not_null()).then(pl.lit(w_bp2)).otherwise(pl.lit(0.0))
        + pl.when(pl.col("_bp3_norm").is_not_null()).then(pl.lit(w_bp3)).otherwise(pl.lit(0.0))
        + pl.when(pl.col("_bp4_norm").is_not_null()).then(pl.lit(w_bp4)).otherwise(pl.lit(0.0))
    )
    out = scored_pl.with_columns(
        [
            pl.when(denominator > 0.0)
            .then(pl.col("_bp2_norm").fill_null(0.0) * pl.lit(w_bp2) / denominator)
            .otherwise(None)
            .alias("contribution_bp2"),
            pl.when(denominator > 0.0)
            .then(pl.col("_bp3_norm").fill_null(0.0) * pl.lit(w_bp3) / denominator)
            .otherwise(None)
            .alias("contribution_bp3"),
            pl.when(denominator > 0.0)
            .then(pl.col("_bp4_norm").fill_null(0.0) * pl.lit(w_bp4) / denominator)
            .otherwise(None)
            .alias("contribution_bp4"),
        ]
    )
    return out.select(
        ["Complaint ID", "priority_score", "contribution_bp2", "contribution_bp3", "contribution_bp4"]
    )


def summarize_contribution_decomposition(decomp_pl: pl.DataFrame) -> dict[str, Any]:
    """Real, live-computed aggregate summary of the exact per-row decomposition above, plus the
    real reconstruction-error structural check (contribution_bp2+contribution_bp3+contribution_bp4
    must equal priority_score for every scored row, within floating-point tolerance) - this is the
    real, structural fact that makes this an EXACT decomposition rather than an approximation."""
    n = decomp_pl.height
    scored = decomp_pl.filter(pl.col("priority_score").is_not_null())
    n_scored = scored.height
    reconstruction_error = (
        scored["contribution_bp2"].fill_null(0.0)
        + scored["contribution_bp3"].fill_null(0.0)
        + scored["contribution_bp4"].fill_null(0.0)
        - scored["priority_score"]
    )
    max_abs_reconstruction_error = float(reconstruction_error.abs().max()) if n_scored else 0.0
    return {
        "n_rows": n,
        "n_scored_rows_compared": n_scored,
        "mean_contribution_bp2": (round(float(scored["contribution_bp2"].mean()), 6) if n_scored else None),
        "mean_contribution_bp3": (round(float(scored["contribution_bp3"].mean()), 6) if n_scored else None),
        "mean_contribution_bp4": (round(float(scored["contribution_bp4"].mean()), 6) if n_scored else None),
        "median_contribution_bp2": (
            round(float(scored["contribution_bp2"].median()), 6) if n_scored else None
        ),
        "median_contribution_bp3": (
            round(float(scored["contribution_bp3"].median()), 6) if n_scored else None
        ),
        "median_contribution_bp4": (
            round(float(scored["contribution_bp4"].median()), 6) if n_scored else None
        ),
        "std_contribution_bp2": (round(float(scored["contribution_bp2"].std()), 6) if n_scored else None),
        "std_contribution_bp3": (round(float(scored["contribution_bp3"].std()), 6) if n_scored else None),
        "std_contribution_bp4": (round(float(scored["contribution_bp4"].std()), 6) if n_scored else None),
        "max_abs_reconstruction_error": round(max_abs_reconstruction_error, 10),
        "reconstruction_exact_within_tolerance": bool(max_abs_reconstruction_error < 1e-6),
        "disclosure": (
            "Exact per-row decomposition of the deterministic weighted-average priority_score "
            "formula - contribution_bp2 + contribution_bp3 + contribution_bp4 reconstructs "
            "priority_score exactly for every scored row (max_abs_reconstruction_error above is "
            "the real, live-computed structural check, expected ~0 within floating-point "
            "tolerance). This is a genuine advantage over an approximate method like SHAP here: "
            "BP7's rule is already a fully transparent linear combination, so its own arithmetic "
            "IS its explanation, not an estimate of one."
        ),
    }


# ---------------------------------------------------------------------------
# Leakage re-confirmation - live, fresh re-check on BP7's own Gate 2 scoring Gold layer, never
# trusted from Gate 1/2/3's own prior claim (Master Plan Gate 4 exit criteria: "leakage
# re-confirmed").
# ---------------------------------------------------------------------------
def reconfirm_no_barred_columns_in_gold_layer(gold_pl_columns: list[str]) -> dict[str, Any]:
    """Live re-check that none of BP7 Gate 1's own `BARRED_COLUMNS` (raw 'Company response to
    consumer', 'Timely response?', 'Date received', 'Date sent to company', 'Tags') are present on
    BP7's own real Gate 2 scoring Gold layer (`cfpb_decision_engine_context_gold.parquet`) - the
    layer `attach_normalized_signal_columns()`/`score_priority_rule()` actually compute
    `priority_score`/`intervention_flag`/`recommended_action` from. This check is deliberately
    run against the SCORING Gold layer's own column list only - `tags_group` (built from BP3's
    OWN separate Gold layer, see `load_bp3_gold_tags_group()` below) is joined onto a DIFFERENT,
    audit-only DataFrame strictly after scoring, and is asserted below to never have touched this
    scoring Gold layer or the scoring computation itself."""
    presence = {col: (col in gold_pl_columns) for col in BARRED_COLUMNS}
    any_present = any(presence.values())
    return {
        "barred_columns_checked": list(BARRED_COLUMNS),
        "presence_in_scoring_gold_layer": presence,
        "any_barred_column_present_in_scoring_gold_layer": any_present,
        "leakage_reconfirmed_clean": not any_present,
        "disclosure": (
            "Live re-check of BP7 Gate 1's own BARRED_COLUMNS against the real scoring Gold "
            "layer's own column list, fresh at Gate 4, never trusted from Gate 1/2/3's own prior "
            "claim. 'Tags' is correctly absent here - it re-enters BP7 Gate 4 only via a separate, "
            "audit-only join (load_bp3_gold_tags_group / attach_tags_group_for_audit below) onto "
            "an already-scored DataFrame, strictly AFTER priority_score/intervention_flag/"
            "recommended_action are computed, and is never merged back into this scoring Gold "
            "layer or re-used as a scoring input."
        ),
    }


# ---------------------------------------------------------------------------
# Disparate-impact / ECOA Reg B audit-only check - the real resolution of Gate 3's honest
# deferral. See this section's own module-level docstring above for the full real investigation
# (BP3's own Gate 4 precedent, Gate 1's input-vs-audit-only distinction) this design follows.
# ---------------------------------------------------------------------------
KNOWN_TAGS_GROUPS: list[str] = [
    "NO_TAG",
    "Servicemember",
    "Older American",
    "Older American, Servicemember",
]


def load_bp3_gold_tags_group(bp3_gold_path: str | Path) -> pl.DataFrame:
    """Load `Complaint ID` + `tags_group` from BP3's OWN real, already-governance-reviewed Gold
    layer (`data/processed/cfpb_intervention_escalation_gold.parquet`) - the full real population,
    not BP3's own held-out test split. `tags_group` is built with BP3's own byte-for-byte
    convention (`bp3_complaint_escalation_prediction_g4_statistical_validation_explainability
    .ipynb`, Section 7: `.cast(pl.Utf8).fill_null("NO_TAG")`), reused here rather than
    reinvented. This is a READ of BP3's own already-delivered, already real-run-confirmed
    artifact only - it never modifies BP3's file, never touches any BP1-6 notebook/module, and
    never reads the raw CFPB extract directly. Raises FileNotFoundError naming the missing path
    if BP3's real Gold layer is not present - never fabricates a tags_group distribution."""
    bp3_gold_path = Path(bp3_gold_path)
    if not bp3_gold_path.exists():
        raise FileNotFoundError(
            f"{bp3_gold_path} not found - BP3's own real Gold layer is required to resolve BP7 "
            "Gate 3's own honestly-deferred disparate-impact carry-forward check. This must not "
            "be worked around by reading the raw CFPB extract directly (Gate 1's leakage_rules "
            "bars 'Tags' as a BP7 input) or by fabricating a tags_group distribution."
        )
    tags_lazy = pl.scan_parquet(bp3_gold_path).select(["Complaint ID", "Tags"])
    tags_pl = (
        tags_lazy.with_columns(pl.col("Tags").cast(pl.Utf8).fill_null("NO_TAG").alias("tags_group"))
        .select(["Complaint ID", "tags_group"])
        .collect()
    )
    n_rows = tags_pl.height
    n_unique_ids = tags_pl["Complaint ID"].n_unique()
    if n_unique_ids != n_rows:
        raise ValueError(
            f"BP3's own Gold layer's 'Complaint ID' is not unique ({n_unique_ids:,} unique / "
            f"{n_rows:,} rows) - cannot use it as a clean 1:1 audit-only join key without risking "
            "row-count fanout onto BP7's own scoring output."
        )
    return tags_pl


def attach_tags_group_for_audit(scored_pl: pl.DataFrame, tags_group_pl: pl.DataFrame) -> pl.DataFrame:
    """Left-join `tags_group_pl` (from `load_bp3_gold_tags_group`) onto `scored_pl` via
    `Complaint ID` - AUDIT-ONLY. Must only ever be called AFTER `score_priority_rule()` has
    already computed `priority_score`/`intervention_flag`/`recommended_action` on `scored_pl`;
    the joined result must never be fed back into `attach_normalized_signal_columns()` or
    `score_priority_rule()`. An unmatched row (not expected - both real populations are the
    identical real CFPB extract keyed by the same real Complaint ID) gets a null `tags_group`,
    excluded from the group breakdown below rather than silently bucketed into a real group."""
    return scored_pl.join(tags_group_pl, on="Complaint ID", how="left")


def compute_disparate_impact_audit(audited_pl: pl.DataFrame, group_col: str = "tags_group") -> dict[str, Any]:
    """The real disparate-impact-style check Gate 1's policy.json committed to and Gate 3
    honestly deferred: per-`tags_group` `intervention_flag` selection rate, and the real
    adverse-impact ratio (min group selection rate / max group selection rate) against the EEOC
    four-fifths-rule convention (< 0.8 flagged) - the IDENTICAL statistical convention BP3's own
    real, already-closed Gate 4 disparate-impact check used (selection-rate-based adverse impact
    ratio), so this re-check is methodologically consistent with that precedent, not a new
    invented approach. `customer360_priority_decision` has no ground-truth column, so (unlike
    BP3's own check, which also had real/predicted labels for recall/FPR) this reports selection-
    rate parity only - the one disparate-impact statistic that requires no ground truth and is
    itself the EEOC four-fifths-rule's own actual basis."""
    n_total = audited_pl.height
    n_matched = int(audited_pl[group_col].is_not_null().sum())
    rows: list[dict[str, Any]] = []
    for group_name in KNOWN_TAGS_GROUPS:
        sub = audited_pl.filter(pl.col(group_col) == group_name)
        n_group = sub.height
        if n_group == 0:
            continue
        n_flagged = int(sub["intervention_flag"].sum())
        rows.append(
            {
                "tags_group": group_name,
                "n_rows": n_group,
                "n_intervention_flagged": n_flagged,
                "selection_rate": round(n_flagged / n_group, 6),
            }
        )
    selection_rates = [r["selection_rate"] for r in rows]
    max_rate = max(selection_rates) if selection_rates else 0.0
    adverse_impact_ratio = (
        round(min(selection_rates) / max_rate, 6) if selection_rates and max_rate > 0.0 else None
    )
    flagged = bool(adverse_impact_ratio is not None and adverse_impact_ratio < 0.8)
    lowest_group = min(rows, key=lambda r: r["selection_rate"])["tags_group"] if rows else None
    highest_group = max(rows, key=lambda r: r["selection_rate"])["tags_group"] if rows else None
    return {
        "n_total_rows": n_total,
        "n_matched_to_tags_group": n_matched,
        "join_coverage_pct": round(100.0 * n_matched / n_total, 6) if n_total else 0.0,
        "group_breakdown": rows,
        "adverse_impact_ratio": adverse_impact_ratio,
        "flagged_four_fifths_rule": flagged,
        "lowest_selection_rate_group": lowest_group,
        "highest_selection_rate_group": highest_group,
        "methodology": (
            "adverse_impact_ratio = min(group selection_rate) / max(group selection_rate); "
            "flagged if < 0.8 (EEOC four-fifths-rule convention) - the identical selection-rate-"
            "based convention BP3's own real, already-closed Gate 4 disparate-impact check used."
        ),
        "limitation": (
            "Monitoring signal for a human reviewer, not a legal determination of ECOA/Reg B "
            "compliance - selection-rate parity alone does not establish or rule out disparate "
            "impact. customer360_priority_decision has no ground-truth column, so (unlike BP3's "
            "own check) this reports selection-rate parity only, never a recall/false-positive-"
            "rate breakdown that would require a real/predicted label pair BP7 does not have."
        ),
    }


# =============================================================================================
# GATE 5 ADDITIONS - decision layer & full-population reporting (built AT Gate 5, extending this
# module rather than creating a second one - HYPER, matching every prior gate's own "one shared
# module, extended gate over gate" precedent). Master Plan's generic Gate 5 row (Section 8's Gate
# table) is "Decision / GenAI Layer & Reporting". For every other BP in this suite, that row's
# "Decision" (a priority/intervention score COMBINING multiple BPs' outputs) was explicitly
# NOT_APPLICABLE and named as BP7's own job instead (BP1/BP2/BP3/BP4 Gate 5's own disclosures,
# carried forward verbatim - Master Plan Section 5.1/7: "Customer Navigator Decision Engine -
# transparent, auditable decision rules combining BP1-BP5 outputs"). BP7 Gate 5 is where that
# deferred cross-BP decision is finally, actually computed and written, for real, for every one
# of the real 1,048,575 CFPB rows - using Gate 3's already-selected champion rule scheme, now
# independently re-verified bit-exact by Gate 4 (including Gate 4's own real resolution of the
# ECOA/Reg B disparate-impact check Gate 3 honestly deferred).
#
# This gate does NOT re-derive the champion identity from scratch (that already happened, twice -
# once at Gate 3's own benchmark/select_champion, once at Gate 4's own independent reproduction).
# It also deliberately does NOT read the champion weights directly off
# `configs/bp7_customer_navigator_decision_engine.yaml` and use them as-is for scoring: those
# config values are rounded to 6 decimal places for human-readable config storage
# (`benchmark_candidate()`'s own `round(..., 6)` - see Gate 3 above), while Gate 3/4 themselves
# always scored using the FULL-PRECISION unrounded normalized weights. Reading the rounded config
# value back in and scoring with IT would risk a small (~1e-6-scale) numeric drift from what Gate
# 3/4 actually validated - a real, avoidable precision bug this module's own Gate 4 section
# already implicitly proved is negligible (its own `weights_match` cross-check against the
# identical rounded config values passed within a 1e-6 tolerance) but which this gate avoids
# entirely by construction: it independently RE-DERIVES the full-precision normalized weights for
# the one, already-locked-in `champion_rule_scheme` name (read live from config), via the
# identical real function chain Gate 3/4 both used
# (`compute_bp2_bp3_correlation`/`compute_bp4_join_coverage`/`compute_candidate_raw_weights`/
# `normalize_candidate_weights`) - never re-running `select_champion()` itself (that would risk
# silently landing on a DIFFERENT champion if any upstream artifact had since drifted, which is
# Gate 3/4's own job to catch, not this gate's) - and cross-checks the result against the
# recorded config values with the SAME tolerances Gate 4 already established for this exact
# rounding gap, before using the freshly-recomputed, full-precision weights for the real,
# full-population scoring pass below.
#
# Public additions:
#   FINAL_OUTPUT_COLUMNS                                       list[str]
#   build_full_population_decision_records(scored_pl, decomp_pl, tags_group_pl) -> pl.DataFrame
#   summarize_recommended_action_breakdown(records_pl)          -> pl.DataFrame
#   summarize_bp4_tier_intervention_crosstab(records_pl)         -> pl.DataFrame
# =============================================================================================

FINAL_OUTPUT_COLUMNS: list[str] = [
    "Complaint ID",
    "priority_score",
    "intervention_flag",
    "recommended_action",
    "reason_codes",
    "contribution_bp2",
    "contribution_bp3",
    "contribution_bp4",
    "bp2_predicted_label",
    "bp2_confidence",
    "bp3_predicted_label",
    "bp3_probability_positive_class",
    "bp4_review_priority_tier",
    "bp4_review_priority_score",
    "bp4_join_status",
    "bp1_context_status",
    "bp5_outcome_1_context",
    "bp5_outcome_2_context",
    "tags_group",
]


def build_full_population_decision_records(
    scored_pl: pl.DataFrame,
    decomp_pl: pl.DataFrame,
    tags_group_pl: Optional[pl.DataFrame],
) -> pl.DataFrame:
    """Assemble BP7's own real, final full-population deliverable - one row per real complaint
    (`Complaint ID`), Gate 1's own named `priority_score`/`intervention_flag`/`recommended_action`/
    `reason_codes` output fields plus every real upstream field that fed (or was context for) that
    score, plus the exact per-row `contribution_bp2`/`contribution_bp3`/`contribution_bp4`
    decomposition (`decomp_pl`, from `compute_priority_score_contribution_decomposition`) and -
    AUDIT-ONLY, never a scoring input, joined here strictly for downstream governance review,
    never fed back into any scoring function - BP3's own real `tags_group`
    (`tags_group_pl`, from `load_bp3_gold_tags_group`; if that real artifact is unavailable,
    every row gets NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED for `tags_group` rather than a silently
    omitted column). `scored_pl` must already carry `priority_score`/`intervention_flag`/
    `recommended_action`/`reason_codes` (from `score_priority_rule`) and every other real Gate 2
    field `FINAL_OUTPUT_COLUMNS` names. Returns exactly `FINAL_OUTPUT_COLUMNS`, in that order -
    never more, never fewer - one row per input row (left joins on the real, unique
    `Complaint ID` key; raises if a join fanout is ever detected, which must never happen)."""
    n_in = scored_pl.height
    out = scored_pl.join(
        decomp_pl.select(["Complaint ID", "contribution_bp2", "contribution_bp3", "contribution_bp4"]),
        on="Complaint ID",
        how="left",
    )
    if tags_group_pl is None:
        out = out.with_columns(pl.lit(NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED).alias("tags_group"))
    else:
        out = out.join(tags_group_pl, on="Complaint ID", how="left")
        out = out.with_columns(pl.col("tags_group").fill_null(NOT_AVAILABLE_BUNDLE_NOT_YET_PERSISTED))
    n_out = out.height
    if n_out != n_in:
        raise ValueError(
            f"build_full_population_decision_records: row count changed from {n_in:,} to "
            f"{n_out:,} after joining contribution decomposition / tags_group - a join fanout "
            "occurred, which must never happen on the real, unique Complaint ID key."
        )
    return out.select(FINAL_OUTPUT_COLUMNS)


def summarize_recommended_action_breakdown(records_pl: pl.DataFrame) -> pl.DataFrame:
    """Real, live-computed per-`recommended_action` rollup: row count, % of the real full
    population, mean `priority_score`, and `intervention_flag` rate within that action bucket -
    Gate 1's own named `recommended_action` output field, reported by its real value distribution
    over the full real population rather than only spot-checked."""
    n = records_pl.height
    agg = (
        records_pl.group_by("recommended_action")
        .agg(
            pl.len().alias("n_rows"),
            pl.col("priority_score").mean().alias("mean_priority_score"),
            pl.col("intervention_flag").cast(pl.Int8).cast(pl.Float64).mean().alias("intervention_flag_rate"),
        )
        .with_columns((pl.col("n_rows") / pl.lit(n) * 100.0).round(6).alias("pct_of_population"))
        .sort("n_rows", descending=True)
    )
    return agg


def summarize_bp4_tier_intervention_crosstab(records_pl: pl.DataFrame) -> pl.DataFrame:
    """Real, live-computed cross-tab of BP4's own real `bp4_review_priority_tier` (HIGH/MEDIUM/
    LOW/NONE, or null for an unjoined row) x BP7's own `intervention_flag` (True/False) - a real,
    structural comparison of BP7's cross-BP decision against BP4's own already-confirmed local
    reporting layer (BP4 Gate 5's own explicit disclosure: "this gate's local flag is not BP7's
    cross-BP decision engine" - this is the real, live-computed comparison that disclosure
    anticipated a downstream consumer would eventually want)."""
    return (
        records_pl.group_by(["bp4_review_priority_tier", "intervention_flag"])
        .agg(pl.len().alias("n_rows"))
        .sort(["bp4_review_priority_tier", "intervention_flag"])
    )
