"""BP8 Gate 3 (Decision-Engine KPI Extension) — Gold-table builders.

This module is BP8's Gate 3. It is ADDITIVE ONLY: it never modifies,
overwrites, or re-reads-and-rewrites anything written by BP8's Gate 1
(``configs/bp8_executive_product_analytics.yaml`` front matter,
``notebooks/bp8_executive_product_analytics/artifacts/policy.json``) or
BP8's Gate 2 (``src/features/bp8_gold_table_builders.py``, the Gate 2
notebook, its 7 Gold Parquet tables under ``powerbi/gold_tables/``, and
``notebooks/bp8_executive_product_analytics/artifacts/gate2_gold_table_manifest.json``).
It only ever creates brand-new files with new names.

Why ``decision_engine_kpis`` (BP7) is built now, at Gate 3, instead of at
Gate 2: at Gate 2 time no ``data/processed/*_gold.parquet`` final
decision-output table existed for BP7, so the category was correctly
deferred. Since then, real analysis has confirmed that BP7's own Gate 5
already produced rich, real, governed, population-scale (1,048,575-row)
summary artifacts under BP7's own
``notebooks/bp7_customer_navigator_decision_engine/artifacts/`` folder
(``gate5_decision_layer_summary.json``,
``gate5_recommended_action_breakdown.csv``,
``gate5_bp4_tier_intervention_crosstab.csv``,
``gate5_disparate_impact_breakdown.csv``). Those artifacts were simply
never aggregated into BP8 Gold tables. This module rolls them up and
reformats them into BP8 Gold tables — it NEVER recomputes any BP7 value
(``priority_score``, ``intervention_flag``, ``recommended_action``,
champion weights, or the disparate-impact ratio all remain exactly as
BP7's own Gate 5 computed and wrote them).

Why ``genai_resolution_kpis`` (BP6) is explicitly OUT OF SCOPE for this
gate, and stays permanently deferred: BP6's real Gate 5 output is a
single generated recommendation (n=1), not a scored population. There is
no real trend, volume, or distribution to aggregate — building a "KPI"
out of one row would not be a genuine population-scale signal, so this
gate does not build anything for ``genai_resolution_kpis`` and never
will.

Public functions:
    build_decision_engine_action_breakdown_gold
    build_decision_engine_tier_crosstab_gold
    build_decision_engine_disparate_impact_gold
    build_decision_engine_summary_gold
    gate3_manifest
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from features.bp8_gold_table_builders import UNSPECIFIED_TIER_SENTINEL

__all__ = [
    "build_decision_engine_action_breakdown_gold",
    "build_decision_engine_tier_crosstab_gold",
    "build_decision_engine_disparate_impact_gold",
    "build_decision_engine_summary_gold",
    "gate3_manifest",
]


def build_decision_engine_action_breakdown_gold(action_breakdown_csv_path: Path) -> pl.DataFrame:
    """Near-direct read of BP7 Gate 5's recommended-action breakdown CSV.

    Source columns (real, 3 rows): recommended_action, n_rows,
    mean_priority_score, intervention_flag_rate, pct_of_population. No
    value is recomputed — this is a Gold-layer reformat of what BP7's own
    Gate 5 already wrote.
    """
    action_breakdown_csv_path = Path(action_breakdown_csv_path)
    df = pl.read_csv(action_breakdown_csv_path)
    df = df.with_columns(
        [
            pl.col("recommended_action").cast(pl.Utf8),
            pl.col("n_rows").cast(pl.Int64),
            pl.col("mean_priority_score").cast(pl.Float64),
            pl.col("intervention_flag_rate").cast(pl.Float64),
            pl.col("pct_of_population").cast(pl.Float64),
        ]
    )
    return df


def build_decision_engine_tier_crosstab_gold(tier_crosstab_csv_path: Path) -> pl.DataFrame:
    """Read of BP7 Gate 5's BP4-tier x intervention-flag crosstab CSV.

    Source columns (real, 8 rows): bp4_review_priority_tier,
    intervention_flag, n_rows. The real source has two rows where
    ``bp4_review_priority_tier`` is blank; those are bucketed into
    ``UNSPECIFIED_TIER_SENTINEL`` (imported from
    ``features.bp8_gold_table_builders``, never redefined here) rather
    than left as an empty string or null, mirroring the exact same
    sentinel treatment Gate 2 already applied to this same field
    elsewhere.
    """
    tier_crosstab_csv_path = Path(tier_crosstab_csv_path)
    df = pl.read_csv(
        tier_crosstab_csv_path,
        schema_overrides={"bp4_review_priority_tier": pl.Utf8},
    )
    df = df.with_columns(
        pl.when(
            pl.col("bp4_review_priority_tier").is_null()
            | (pl.col("bp4_review_priority_tier").str.strip_chars() == "")
        )
        .then(pl.lit(UNSPECIFIED_TIER_SENTINEL))
        .otherwise(pl.col("bp4_review_priority_tier"))
        .alias("bp4_review_priority_tier")
    )
    df = df.with_columns(
        [
            pl.col("intervention_flag").cast(pl.Boolean),
            pl.col("n_rows").cast(pl.Int64),
        ]
    )
    return df


def build_decision_engine_disparate_impact_gold(disparate_impact_csv_path: Path) -> pl.DataFrame:
    """Read of BP7 Gate 5's disparate-impact-audit breakdown CSV.

    Source columns (real, 4 rows): tags_group, n_rows,
    n_intervention_flagged, selection_rate. One real value
    (``"Older American, Servicemember"``) is a single string containing a
    comma, correctly CSV-quoted in the source — this uses Polars' real
    CSV parser (``pl.read_csv``), never a manual ``.split(",")``, so that
    value is never mis-split.
    """
    disparate_impact_csv_path = Path(disparate_impact_csv_path)
    df = pl.read_csv(disparate_impact_csv_path)
    df = df.with_columns(
        [
            pl.col("tags_group").cast(pl.Utf8),
            pl.col("n_rows").cast(pl.Int64),
            pl.col("n_intervention_flagged").cast(pl.Int64),
            pl.col("selection_rate").cast(pl.Float64),
        ]
    )
    return df


def build_decision_engine_summary_gold(decision_layer_summary_json_path: Path) -> pl.DataFrame:
    """Single-row Gold table assembled from BP7 Gate 5's summary JSON.

    Every value is read by key from the real JSON at runtime (never
    hardcoded as a literal in this module). The JSON has additional keys
    beyond what is selected here (e.g. ``weight_rederivation_cross_check``,
    ``cross_checks_vs_gate3_gate4``, ``gate4_bootstrap_ci_carried_forward``,
    ``upstream_field_coverage``, ``compliance_touchpoint``); this function
    only reads the top-level scalar/nested-scalar fields it needs and does
    not assume the file contains only those fields.
    """
    decision_layer_summary_json_path = Path(decision_layer_summary_json_path)
    with decision_layer_summary_json_path.open("r", encoding="utf-8") as fh:
        report = json.load(fh)

    champion_weights = report["champion_weights_normalized"]
    champion_stats = report["champion_stats"]
    contribution_summary = report["contribution_decomposition_summary"]
    disparate_impact_audit = report["disparate_impact_audit"]

    row = {
        "bp_id": report["bp_id"],
        "gate": report["gate"],
        "generated_at_utc": report["generated_at_utc"],
        "live_row_count": report["live_row_count"],
        "champion_rule_scheme": report["champion_rule_scheme"],
        "champion_weight_bp2": champion_weights["bp2"],
        "champion_weight_bp3": champion_weights["bp3"],
        "champion_weight_bp4": champion_weights["bp4"],
        "intervention_threshold": report["intervention_threshold"],
        "coverage_pct": champion_stats["coverage_pct"],
        "intervention_flag_rate": champion_stats["intervention_flag_rate"],
        "bp3_agreement_rate": champion_stats["bp3_agreement_rate"],
        "avg_reason_codes_per_row": champion_stats["avg_reason_codes_per_row"],
        "mean_contribution_bp2": contribution_summary["mean_contribution_bp2"],
        "mean_contribution_bp3": contribution_summary["mean_contribution_bp3"],
        "mean_contribution_bp4": contribution_summary["mean_contribution_bp4"],
        "max_abs_reconstruction_error": contribution_summary["max_abs_reconstruction_error"],
        "adverse_impact_ratio": disparate_impact_audit["adverse_impact_ratio"],
        "flagged_four_fifths_rule": disparate_impact_audit["flagged_four_fifths_rule"],
        "lowest_selection_rate_group": disparate_impact_audit["lowest_selection_rate_group"],
        "highest_selection_rate_group": disparate_impact_audit["highest_selection_rate_group"],
    }
    return pl.DataFrame([row])


def gate3_manifest(tables_written: list[dict]) -> dict:
    """Assemble the Gate 3 manifest dict (assembly only — no I/O).

    Mirrors the small assembly-only shape of Gate 2's own
    ``gold_table_manifest()`` but is written fresh here: Gate 3 owns its
    own manifest file (``gate3_decision_engine_kpi_manifest.json``) and
    never imports or touches Gate 2's ``gold_table_manifest()`` function
    or Gate 2's own manifest file.
    """
    return {
        "gold_tables_written": tables_written,
        "n_gold_tables_written": len(tables_written),
    }
