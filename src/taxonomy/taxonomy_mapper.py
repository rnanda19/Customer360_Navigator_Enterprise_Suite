"""
src/taxonomy/taxonomy_mapper.py — Customer360 Navigator

CFPB <-> BANKING77 common-taxonomy mapping logic (Master Plan Section 6 Integration Architecture,
Section 7 BP1 Methodology, Gate 2 Data Verification & Feature/Taxonomy Engineering).

Standing rules this module follows:
  - WARP: Polars lazy scans, category dtype, no pandas, no eager full-file loads where a lazy
    scan + select + collect will do.
  - Zero-fabrication: every mapping decision is read from configs/taxonomy_mapping.yaml (the
    documented, judgment-based crosswalk — see docs/data_dictionary/CFPB_BANKING77_TAXONOMY_MAPPING.md
    for the rationale and confidence level behind every bucket). This module never invents a
    mapping inline; it only applies the one already reviewed and versioned in the YAML config.
  - This module is import-only shared logic (HYPER: shared component library). It performs no
    I/O side effects at import time and is never executed by Claude — only the user runs it, in
    their own environment, per the project's execution-boundary rule.

Public functions:
  load_mapping_config(config_path)          -> dict
  bucket_for_banking77_category(category, mapping) -> str | None
  cfpb_bucket_expr(mapping)                  -> pl.Expr   (Product -> bucket, else "OUT_OF_SCOPE"/"UNMAPPED")
  load_banking77_with_bucket(train_path, test_path, categories_path, mapping) -> pl.DataFrame
  load_cfpb_with_bucket(cfpb_path, mapping)  -> pl.LazyFrame
  build_common_taxonomy_layer(cfpb_lazy, banking77_df, out_dir) -> dict (paths + summary)
  mapping_coverage_report(cfpb_lazy, banking77_df, mapping) -> pl.DataFrame
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import polars as pl
import yaml

# Real, verified CFPB schema (docs/data_dictionary/RAW_DATA_MANIFEST.md) - the single shared dtype
# map for this 15-column file. Exposed as a module constant (HYPER: shared component library) so
# every notebook that scans data/raw/cfpb_complaints.csv - profiling included, not just taxonomy
# mapping - uses the identical schema rather than re-deriving or duplicating it inline.
CFPB_DTYPES: dict[str, pl.PolarsDataType] = {
    "Date received": pl.Utf8,
    "Product": pl.Categorical,
    "Sub-product": pl.Categorical,
    "Issue": pl.Categorical,
    "Sub-issue": pl.Categorical,
    "Company public response": pl.Categorical,
    "Company": pl.Categorical,
    "State": pl.Categorical,
    "ZIP code": pl.Utf8,
    "Tags": pl.Categorical,
    "Submitted via": pl.Categorical,
    "Date sent to company": pl.Utf8,
    "Company response to consumer": pl.Categorical,
    "Timely response?": pl.Categorical,
    "Complaint ID": pl.Int64,
}


def load_mapping_config(config_path: str | Path) -> dict:
    """Load configs/taxonomy_mapping.yaml. Raises FileNotFoundError with a clear message if
    the config has not been generated yet — never falls back to a silent empty mapping.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Taxonomy mapping config not found at {config_path}. This file is the single "
            "source of truth for the CFPB<->BANKING77 crosswalk — generate it before running "
            "any BP that depends on the common taxonomy layer (BP1, BP2, BP4, BP6, BP8)."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f)
    required_keys = {
        "cfpb_product_distribution",
        "common_taxonomy_buckets",
        "banking77_category_to_bucket",
    }
    missing = required_keys - set(mapping.keys())
    if missing:
        raise ValueError(f"Taxonomy mapping config is missing required keys: {missing}")
    if len(mapping["banking77_category_to_bucket"]) != 77:
        raise ValueError(
            "Expected exactly 77 BANKING77 categories mapped (the dataset's real category "
            f"count); found {len(mapping['banking77_category_to_bucket'])}. Do not proceed "
            "with a partial mapping — re-verify banking77_categories.json."
        )
    return mapping


def bucket_for_banking77_category(category: str, mapping: dict) -> Optional[str]:
    """Look up the common-taxonomy bucket for one BANKING77 category label."""
    return mapping["banking77_category_to_bucket"].get(category)


def _product_to_bucket_lookup(mapping: dict) -> dict[str, str]:
    """Flatten common_taxonomy_buckets -> {cfpb_product_name: bucket_name}.
    A CFPB product can appear under more than one bucket as a candidate (e.g. 'Credit card or
    prepaid card' appears under both CARD_ISSUANCE_AND_LIFECYCLE and CARD_PAYMENT_ISSUES); in
    that case the FIRST bucket listed in the YAML for that product wins for a pure product-level
    join. This is a documented simplification — true row-level bucket assignment for those
    shared products requires the Issue/Sub-issue-level refinement flagged as a Gate 2 follow-up
    in CFPB_BANKING77_TAXONOMY_MAPPING.md section 5, not yet available."""
    lookup: dict[str, str] = {}
    for bucket_name, bucket_def in mapping["common_taxonomy_buckets"].items():
        for product in bucket_def["cfpb_product_candidates"]:
            lookup.setdefault(product, bucket_name)
    return lookup


def cfpb_bucket_expr(mapping: dict) -> pl.Expr:
    """Build a Polars expression mapping the CFPB `Product` column to a common-taxonomy bucket.
    Products present in the file but not listed as an in-scope candidate for any bucket map to
    'OUT_OF_SCOPE_NO_BANKING77_OVERLAP' (the real, measured majority of this CFPB extract — see
    CFPB_BANKING77_TAXONOMY_MAPPING.md section 2). A Product value never seen in the mapping at
    all (e.g. a future CFPB export with a renamed product) maps to 'UNMAPPED_UNKNOWN_PRODUCT' so
    it is surfaced for review rather than silently dropped or silently bucketed."""
    product_to_bucket = _product_to_bucket_lookup(mapping)
    known_products = {p for p, _ in [(d["product"], None) for d in mapping["cfpb_product_distribution"]]}

    return (
        pl.when(pl.col("Product").is_in(list(product_to_bucket.keys())))
        .then(pl.col("Product").replace_strict(product_to_bucket, default="UNMAPPED_UNKNOWN_PRODUCT"))
        .when(pl.col("Product").is_in(list(known_products)))
        .then(pl.lit("OUT_OF_SCOPE_NO_BANKING77_OVERLAP"))
        .otherwise(pl.lit("UNMAPPED_UNKNOWN_PRODUCT"))
        .alias("common_taxonomy_bucket")
    )


def load_banking77_with_bucket(
    train_path: str | Path,
    test_path: str | Path,
    categories_path: str | Path,
    mapping: dict,
) -> pl.DataFrame:
    """Load BANKING77 train+test, tag each row's split, and attach its common-taxonomy bucket.
    Raises if any category in the files is absent from the mapping (zero-fabrication: never
    silently assign an unmapped category to a default bucket)."""
    with open(categories_path, "r", encoding="utf-8") as f:
        categories = json.load(f)
    if len(categories) != 77:
        raise ValueError(f"Expected 77 BANKING77 categories in {categories_path}, found {len(categories)}")

    train = pl.read_csv(
        train_path, schema_overrides={"text": pl.Utf8, "category": pl.Categorical}
    ).with_columns(pl.lit("train").alias("split"))
    test = pl.read_csv(
        test_path, schema_overrides={"text": pl.Utf8, "category": pl.Categorical}
    ).with_columns(pl.lit("test").alias("split"))
    df = pl.concat([train, test])

    unmapped = set(df["category"].unique().to_list()) - set(mapping["banking77_category_to_bucket"].keys())
    if unmapped:
        raise ValueError(
            f"BANKING77 categories present in the data but absent from taxonomy_mapping.yaml: "
            f"{sorted(unmapped)}. Update the mapping config before proceeding — never assign an "
            "unreviewed category to a bucket implicitly."
        )

    bucket_expr = (
        pl.col("category")
        .cast(pl.Utf8)
        .replace_strict(mapping["banking77_category_to_bucket"], default="UNMAPPED_UNKNOWN_CATEGORY")
        .alias("common_taxonomy_bucket")
    )

    return df.with_columns(bucket_expr)


def load_cfpb_with_bucket(cfpb_path: str | Path, mapping: dict) -> pl.LazyFrame:
    """Lazy-scan the CFPB complaints file and attach the common-taxonomy bucket per row, without
    eagerly materializing the full ~322MB / 1.05M-row file (WARP)."""
    lazy = pl.scan_csv(cfpb_path, schema_overrides=CFPB_DTYPES)
    return lazy.with_columns(cfpb_bucket_expr(mapping))


def mapping_coverage_report(
    cfpb_lazy: pl.LazyFrame, banking77_df: pl.DataFrame, mapping: dict
) -> pl.DataFrame:
    """Produce the audit table the Master Plan requires: row counts and fraction per bucket, for
    both datasets, plus the explicit unmapped/out-of-scope counts. This is the artifact that
    should be re-generated (and diffed against CFPB_BANKING77_TAXONOMY_MAPPING.md's documented
    figures) every time the mapping config or the source data changes — never assumed stable.
    """
    cfpb_counts = cfpb_lazy.group_by("common_taxonomy_bucket").agg(pl.len().alias("cfpb_row_count")).collect()
    b77_counts = banking77_df.group_by("common_taxonomy_bucket").agg(pl.len().alias("banking77_row_count"))
    report = cfpb_counts.join(b77_counts, on="common_taxonomy_bucket", how="full", coalesce=True).fill_null(0)
    cfpb_total = report["cfpb_row_count"].sum()
    b77_total = report["banking77_row_count"].sum()
    report = report.with_columns(
        (pl.col("cfpb_row_count") / cfpb_total).alias("cfpb_fraction"),
        (pl.col("banking77_row_count") / b77_total).alias("banking77_fraction"),
    ).sort("cfpb_row_count", descending=True)
    return report


def build_common_taxonomy_layer(
    cfpb_lazy: pl.LazyFrame,
    banking77_df: pl.DataFrame,
    out_dir: str | Path,
) -> dict:
    """Write the Customer360 Gold common-taxonomy layer to Parquet (WARP: Parquet over CSV for
    reused data) and return the output paths + row counts. Does not attempt a row-level join
    between the two datasets — writes two separate bucket-tagged Gold tables, exactly as
    Master Plan Section 6's Integration Architecture diagram specifies (both feed the same
    'Common Taxonomy / Intent Layer', not a merged row set)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfpb_gold_path = out_dir / "cfpb_common_taxonomy_gold.parquet"
    banking77_gold_path = out_dir / "banking77_common_taxonomy_gold.parquet"

    cfpb_lazy.sink_parquet(cfpb_gold_path)
    banking77_df.write_parquet(banking77_gold_path)

    cfpb_rows = pl.scan_parquet(cfpb_gold_path).select(pl.len()).collect().item()
    banking77_rows = banking77_df.height

    return {
        "cfpb_gold_path": str(cfpb_gold_path),
        "banking77_gold_path": str(banking77_gold_path),
        "cfpb_rows_written": cfpb_rows,
        "banking77_rows_written": banking77_rows,
    }
