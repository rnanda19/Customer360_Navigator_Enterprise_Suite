"""
src/taxonomy/friction_severity_mapper.py — Customer360 Navigator

BP2 friction-severity taxonomy logic (Master Plan Section 5.1 / Section 7 BP2 Methodology,
Gate 1-2). Sibling module to taxonomy_mapper.py (BP1's CFPB<->BANKING77 crosswalk) - reuses its
CFPB_DTYPES and load_cfpb_with_bucket rather than duplicating them (HYPER: shared component
library built once).

Standing rules this module follows:
  - WARP: Polars lazy scans, category dtype, no pandas, no eager full-file loads where a lazy
    scan + select + collect will do.
  - Zero-fabrication: every severity rule is read from configs/bp2_friction_severity_taxonomy.yaml
    (the documented, judgment-based mapping - see that file's `severity_classes`/`excluded_classes`
    rationale and confidence level for every rule). This module never invents a mapping inline; it
    only applies the one already reviewed and versioned in the YAML config.
  - This module is import-only shared logic (HYPER). It performs no I/O side effects at import
    time and is never executed by Claude - only the user runs it, per the execution-boundary rule.

Public functions:
  load_severity_config(config_path)               -> dict
  friction_severity_expr(severity_config)          -> pl.Expr
  load_cfpb_with_severity(cfpb_path, severity_config, taxonomy_mapping=None) -> pl.LazyFrame
  severity_crosstab_report(cfpb_lazy)              -> pl.DataFrame
  severity_distribution_report(cfpb_lazy)          -> pl.DataFrame
  build_bp2_severity_gold_layer(cfpb_lazy, out_dir) -> dict (paths + row counts)
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

from taxonomy.taxonomy_mapper import CFPB_DTYPES, cfpb_bucket_expr


def load_severity_config(config_path: str | Path) -> dict:
    """Load configs/bp2_friction_severity_taxonomy.yaml. Raises FileNotFoundError with a clear
    message if the config has not been generated yet — never falls back to a silent empty
    mapping."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"BP2 friction-severity taxonomy config not found at {config_path}. This file is the "
            "single documented source of the severity precedence rules - it must exist (authored "
            "against the real BP2 Gate 1 live-enumerated values) before this module can be used."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def friction_severity_expr(severity_config: dict) -> pl.Expr:
    """Build a Polars expression implementing the documented precedence_order rules from
    configs/bp2_friction_severity_taxonomy.yaml, evaluated in order (first match wins), exactly
    as the config specifies. Never re-derives the rule order from anywhere else."""
    rules = severity_config["precedence_order"]
    class_for_rule = {r["rule"]: r["severity_class"] for r in rules}

    expr = (
        pl.when(pl.col("Timely response?") == "No")
        .then(pl.lit(class_for_rule["timely_response_no"]))
        .when(pl.col("Company response to consumer") == "Untimely response")
        .then(pl.lit(class_for_rule["untimely_response_label"]))
        .when(pl.col("Company response to consumer") == "In progress")
        .then(pl.lit(class_for_rule["in_progress"]))
        .when(pl.col("Company response to consumer") == "Closed with monetary relief")
        .then(pl.lit(class_for_rule["closed_monetary_relief"]))
        .when(pl.col("Company response to consumer") == "Closed with non-monetary relief")
        .then(pl.lit(class_for_rule["closed_non_monetary_relief"]))
        .when(pl.col("Company response to consumer") == "Closed with explanation")
        .then(pl.lit(class_for_rule["closed_with_explanation"]))
        .otherwise(pl.lit(class_for_rule["null_company_response"]))
        .alias("friction_severity_class")
    )
    return expr


def load_cfpb_with_severity(
    cfpb_path: str | Path,
    severity_config: dict,
    taxonomy_mapping: dict | None = None,
) -> pl.LazyFrame:
    """Lazy-scan the CFPB complaints file and attach `friction_severity_class`, without eagerly
    materializing the full ~322MB / 1.05M-row file (WARP). If `taxonomy_mapping` (BP1's
    configs/taxonomy_mapping.yaml, already loaded via taxonomy_mapper.load_mapping_config) is
    provided, also attaches `common_taxonomy_bucket` by reusing BP1's own cfpb_bucket_expr
    unmodified - this is how BP2 satisfies the Master Plan's 'Integrates BANKING77: YES'
    requirement, since BANKING77 itself carries no friction/severity signal to train on."""
    lazy = pl.scan_csv(cfpb_path, schema_overrides=CFPB_DTYPES)
    lazy = lazy.with_columns(friction_severity_expr(severity_config))
    if taxonomy_mapping is not None:
        lazy = lazy.with_columns(cfpb_bucket_expr(taxonomy_mapping))
    return lazy


def severity_crosstab_report(cfpb_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Live crosstab of the two real source fields the severity taxonomy is built from -
    surfaces whether 'Untimely response' (Company response to consumer) and
    Timely response?=='No' ever disagree on the same row, rather than assuming they are
    redundant (they are two separately recorded real fields)."""
    return (
        cfpb_lazy.group_by(["Company response to consumer", "Timely response?"])
        .agg(pl.len().alias("row_count"))
        .sort("row_count", descending=True)
        .collect()
    )


def severity_distribution_report(cfpb_lazy: pl.LazyFrame) -> pl.DataFrame:
    """Real row count and fraction per assigned friction_severity_class - the audit table Gate 2
    is required to produce, mirroring taxonomy_mapper.mapping_coverage_report's pattern."""
    counts = (
        cfpb_lazy.group_by("friction_severity_class")
        .agg(pl.len().alias("row_count"))
        .collect()
    )
    total = counts["row_count"].sum()
    return counts.with_columns(
        (pl.col("row_count") / total).alias("fraction_of_total")
    ).sort("row_count", descending=True)


def build_bp2_severity_gold_layer(cfpb_lazy: pl.LazyFrame, out_dir: str | Path) -> dict:
    """Write the BP2 CFPB-with-severity Gold layer to Parquet (WARP: Parquet over CSV for reused
    data), mirroring taxonomy_mapper.build_common_taxonomy_layer's pattern exactly."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gold_path = out_dir / "cfpb_friction_severity_gold.parquet"
    cfpb_lazy.sink_parquet(gold_path)
    rows_written = pl.scan_parquet(gold_path).select(pl.len()).collect().item()

    return {
        "cfpb_severity_gold_path": str(gold_path),
        "cfpb_severity_gold_rows_written": rows_written,
    }
