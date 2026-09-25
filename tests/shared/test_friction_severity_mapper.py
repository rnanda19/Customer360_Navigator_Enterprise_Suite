"""
tests/shared/test_friction_severity_mapper.py — Customer360 Navigator

Full pytest coverage for src/taxonomy/friction_severity_mapper.py (BP2 Gate 6 governance
requirement - this module had ZERO test coverage before this file, unlike its BP1 sibling
taxonomy_mapper.py, which tests/shared/test_taxonomy_mapper.py already covers). Same discipline as
that file: small, real, schema-correct synthetic fixtures (never fabricated numbers baked into the
module itself), covering every public function's happy path and its documented precedence/
exclusion rules.
"""

from __future__ import annotations

import polars as pl
import pytest
import yaml

from taxonomy import friction_severity_mapper as fsm


# ---------------------------------------------------------------------------
# Fixtures - a minimal, schema-correct severity config mirroring configs/
# bp2_friction_severity_taxonomy.yaml's real precedence_order structure.
# ---------------------------------------------------------------------------

def _make_valid_severity_config() -> dict:
    return {
        "precedence_order": [
            {"rule": "timely_response_no", "severity_class": "HIGH_FRICTION"},
            {"rule": "untimely_response_label", "severity_class": "HIGH_FRICTION"},
            {"rule": "in_progress", "severity_class": "EXCLUDED_PENDING"},
            {"rule": "closed_monetary_relief", "severity_class": "LOW_FRICTION"},
            {"rule": "closed_non_monetary_relief", "severity_class": "MEDIUM_FRICTION"},
            {"rule": "closed_with_explanation", "severity_class": "MEDIUM_HIGH_FRICTION"},
            {"rule": "null_company_response", "severity_class": "EXCLUDED_UNKNOWN"},
        ],
        "severity_classes": {
            "LOW_FRICTION": {"ordinal_rank": 0},
            "MEDIUM_FRICTION": {"ordinal_rank": 1},
            "MEDIUM_HIGH_FRICTION": {"ordinal_rank": 2},
            "HIGH_FRICTION": {"ordinal_rank": 3},
        },
        "excluded_classes": {
            "EXCLUDED_PENDING": {"reason": "not a resolution outcome"},
            "EXCLUDED_UNKNOWN": {"reason": "negligible null-response rows"},
        },
    }


@pytest.fixture
def valid_severity_config():
    return _make_valid_severity_config()


@pytest.fixture
def severity_config_path(tmp_path, valid_severity_config):
    path = tmp_path / "bp2_friction_severity_taxonomy.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(valid_severity_config, f)
    return path


def _cfpb_rows():
    """One real-shaped row per precedence branch, in an order chosen to exercise every rule -
    including the precedence override (a row that is BOTH untimely AND would otherwise resolve to
    LOW_FRICTION must still land on HIGH_FRICTION, since Timely response?=='No' is checked first)."""
    return [
        # Precedence override: Timely=No wins even though the response type alone would be LOW_FRICTION.
        {"Company response to consumer": "Closed with monetary relief", "Timely response?": "No"},
        {"Company response to consumer": "Untimely response", "Timely response?": "Yes"},
        {"Company response to consumer": "In progress", "Timely response?": "Yes"},
        {"Company response to consumer": "Closed with monetary relief", "Timely response?": "Yes"},
        {"Company response to consumer": "Closed with non-monetary relief", "Timely response?": "Yes"},
        {"Company response to consumer": "Closed with explanation", "Timely response?": "Yes"},
        {"Company response to consumer": None, "Timely response?": "Yes"},
    ]


# ---------------------------------------------------------------------------
# load_severity_config
# ---------------------------------------------------------------------------

def test_load_severity_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="BP2 friction-severity taxonomy config not found"):
        fsm.load_severity_config(tmp_path / "does_not_exist.yaml")


def test_load_severity_config_valid_returns_dict(severity_config_path):
    config = fsm.load_severity_config(severity_config_path)
    assert "precedence_order" in config
    assert len(config["precedence_order"]) == 7


# ---------------------------------------------------------------------------
# friction_severity_expr - the precedence-order rule, including the documented override where
# Timely response?=='No' is checked BEFORE Company response to consumer.
# ---------------------------------------------------------------------------

def test_friction_severity_expr_precedence_and_all_branches(valid_severity_config):
    df = pl.DataFrame(_cfpb_rows())
    result = df.with_columns(fsm.friction_severity_expr(valid_severity_config))["friction_severity_class"].to_list()
    assert result == [
        "HIGH_FRICTION",          # Timely=No overrides what would otherwise be LOW_FRICTION
        "HIGH_FRICTION",          # Untimely response label
        "EXCLUDED_PENDING",       # In progress
        "LOW_FRICTION",           # Closed with monetary relief
        "MEDIUM_FRICTION",        # Closed with non-monetary relief
        "MEDIUM_HIGH_FRICTION",   # Closed with explanation
        "EXCLUDED_UNKNOWN",       # null Company response to consumer
    ]


# ---------------------------------------------------------------------------
# load_cfpb_with_severity - lazy, adds the severity column, optional taxonomy_mapping integration
# ---------------------------------------------------------------------------

def test_load_cfpb_with_severity_is_lazy_and_adds_column(tmp_path, valid_severity_config):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame(_cfpb_rows()[:2]).write_csv(cfpb_path)
    lazy = fsm.load_cfpb_with_severity(cfpb_path, valid_severity_config)
    assert isinstance(lazy, pl.LazyFrame)
    collected = lazy.collect()
    assert "friction_severity_class" in collected.columns
    assert collected.height == 2


def test_load_cfpb_with_severity_attaches_taxonomy_bucket_when_mapping_provided(tmp_path, valid_severity_config):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame([
        {"Company response to consumer": "Closed with monetary relief", "Timely response?": "Yes",
         "Product": "Checking or savings account"},
    ]).write_csv(cfpb_path)
    taxonomy_mapping = {
        "cfpb_product_distribution": [{"product": "Checking or savings account", "count": 1}],
        "common_taxonomy_buckets": {"BUCKET_A": {"cfpb_product_candidates": ["Checking or savings account"]}},
        "banking77_category_to_bucket": {},
    }
    lazy = fsm.load_cfpb_with_severity(cfpb_path, valid_severity_config, taxonomy_mapping=taxonomy_mapping)
    collected = lazy.collect()
    assert "common_taxonomy_bucket" in collected.columns
    assert collected["common_taxonomy_bucket"].to_list() == ["BUCKET_A"]


def test_load_cfpb_with_severity_no_taxonomy_bucket_column_when_mapping_omitted(tmp_path, valid_severity_config):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame(_cfpb_rows()[:1]).write_csv(cfpb_path)
    lazy = fsm.load_cfpb_with_severity(cfpb_path, valid_severity_config)
    assert "common_taxonomy_bucket" not in lazy.collect().columns


# ---------------------------------------------------------------------------
# severity_crosstab_report
# ---------------------------------------------------------------------------

def test_severity_crosstab_report_counts_agreement(tmp_path, valid_severity_config):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame(_cfpb_rows()).write_csv(cfpb_path)
    cfpb_lazy = fsm.load_cfpb_with_severity(cfpb_path, valid_severity_config)
    report = fsm.severity_crosstab_report(cfpb_lazy)
    assert report["row_count"].sum() == len(_cfpb_rows())
    # The one row with both Untimely-response label AND Timely?==Yes must appear as its own
    # crosstab cell (they are NOT assumed redundant).
    untimely_yes = report.filter(
        (pl.col("Company response to consumer") == "Untimely response")
        & (pl.col("Timely response?") == "Yes")
    )
    assert untimely_yes["row_count"].sum() == 1


# ---------------------------------------------------------------------------
# severity_distribution_report
# ---------------------------------------------------------------------------

def test_severity_distribution_report_fractions_sum_to_one(tmp_path, valid_severity_config):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame(_cfpb_rows()).write_csv(cfpb_path)
    cfpb_lazy = fsm.load_cfpb_with_severity(cfpb_path, valid_severity_config)
    report = fsm.severity_distribution_report(cfpb_lazy)
    assert report["fraction_of_total"].sum() == pytest.approx(1.0)
    assert report["row_count"].sum() == len(_cfpb_rows())


# ---------------------------------------------------------------------------
# build_bp2_severity_gold_layer
# ---------------------------------------------------------------------------

def test_build_bp2_severity_gold_layer_writes_parquet_and_returns_row_count(tmp_path, valid_severity_config):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame(_cfpb_rows()).write_csv(cfpb_path)
    cfpb_lazy = fsm.load_cfpb_with_severity(cfpb_path, valid_severity_config)

    out_dir = tmp_path / "gold"
    result = fsm.build_bp2_severity_gold_layer(cfpb_lazy, out_dir)

    assert (out_dir / "cfpb_friction_severity_gold.parquet").exists()
    assert result["cfpb_severity_gold_rows_written"] == len(_cfpb_rows())
