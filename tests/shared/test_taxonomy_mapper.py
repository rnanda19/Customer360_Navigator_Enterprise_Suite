"""
tests/shared/test_taxonomy_mapper.py — Customer360 Navigator

Full pytest coverage for src/taxonomy/taxonomy_mapper.py (BP1 Gate 6 governance requirement).
Covers every public function's happy path AND its documented failure modes (missing config,
missing keys, wrong category count, unmapped category rejection) - the zero-fabrication rule
this module follows ("never silently assign an unmapped category to a default bucket") is only
actually enforced if these raise-paths are tested, not just the success paths.
"""

from __future__ import annotations

import json

import polars as pl
import pytest
import yaml

from taxonomy import taxonomy_mapper as tm

# ---------------------------------------------------------------------------
# Fixtures - small, real, schema-correct mapping/data (never fabricated numbers baked into
# the module itself - these are test-local synthetic fixtures, same discipline as the
# notebook-level synthetic-fixture dry-runs used to verify every BP1 notebook this session).
# ---------------------------------------------------------------------------


def _make_valid_mapping_dict(n_categories: int = 77) -> dict:
    banking77_category_to_bucket = {
        f"intent_{i}": "BUCKET_A" if i % 2 == 0 else "BUCKET_B" for i in range(n_categories)
    }
    return {
        "cfpb_product_distribution": [
            {"product": "Checking or savings account", "count": 100},
            {"product": "Credit card or prepaid card", "count": 50},
            {"product": "Some other product", "count": 10},
        ],
        "common_taxonomy_buckets": {
            "BUCKET_A": {"cfpb_product_candidates": ["Checking or savings account"]},
            "BUCKET_B": {
                "cfpb_product_candidates": ["Credit card or prepaid card", "Checking or savings account"]
            },
        },
        "banking77_category_to_bucket": banking77_category_to_bucket,
    }


@pytest.fixture
def valid_mapping():
    return _make_valid_mapping_dict()


@pytest.fixture
def mapping_config_path(tmp_path, valid_mapping):
    path = tmp_path / "taxonomy_mapping.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(valid_mapping, f)
    return path


# ---------------------------------------------------------------------------
# load_mapping_config
# ---------------------------------------------------------------------------


def test_load_mapping_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Taxonomy mapping config not found"):
        tm.load_mapping_config(tmp_path / "does_not_exist.yaml")


def test_load_mapping_config_missing_keys_raises(tmp_path):
    path = tmp_path / "bad_mapping.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"cfpb_product_distribution": []}, f)
    with pytest.raises(ValueError, match="missing required keys"):
        tm.load_mapping_config(path)


def test_load_mapping_config_wrong_category_count_raises(tmp_path):
    bad_mapping = _make_valid_mapping_dict(n_categories=10)  # not 77
    path = tmp_path / "bad_count.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(bad_mapping, f)
    with pytest.raises(ValueError, match="Expected exactly 77"):
        tm.load_mapping_config(path)


def test_load_mapping_config_valid_returns_dict(mapping_config_path):
    mapping = tm.load_mapping_config(mapping_config_path)
    assert len(mapping["banking77_category_to_bucket"]) == 77
    assert "cfpb_product_distribution" in mapping


# ---------------------------------------------------------------------------
# bucket_for_banking77_category
# ---------------------------------------------------------------------------


def test_bucket_for_banking77_category_found(valid_mapping):
    assert tm.bucket_for_banking77_category("intent_0", valid_mapping) == "BUCKET_A"
    assert tm.bucket_for_banking77_category("intent_1", valid_mapping) == "BUCKET_B"


def test_bucket_for_banking77_category_not_found_returns_none(valid_mapping):
    assert tm.bucket_for_banking77_category("intent_does_not_exist", valid_mapping) is None


# ---------------------------------------------------------------------------
# _product_to_bucket_lookup (private helper, but load-bearing for cfpb_bucket_expr - tested
# directly since its documented "first bucket wins" tie-break rule is easy to silently break).
# ---------------------------------------------------------------------------


def test_product_to_bucket_lookup_first_bucket_wins(valid_mapping):
    lookup = tm._product_to_bucket_lookup(valid_mapping)
    # "Checking or savings account" is a candidate under BOTH BUCKET_A and BUCKET_B - the
    # module's docstring says the FIRST bucket listed in the YAML (dict insertion order) wins.
    assert lookup["Checking or savings account"] == "BUCKET_A"
    assert lookup["Credit card or prepaid card"] == "BUCKET_B"


# ---------------------------------------------------------------------------
# cfpb_bucket_expr
# ---------------------------------------------------------------------------


def test_cfpb_bucket_expr_maps_known_out_of_scope_and_unknown(valid_mapping):
    df = pl.DataFrame(
        {
            "Product": [
                "Checking or savings account",  # mapped -> BUCKET_A
                "Credit card or prepaid card",  # mapped -> BUCKET_B
                "Some other product",  # known product, not a candidate for any bucket -> OUT_OF_SCOPE
                "A totally new product",  # never seen in cfpb_product_distribution at all -> UNMAPPED
            ]
        }
    )
    result = df.with_columns(tm.cfpb_bucket_expr(valid_mapping))["common_taxonomy_bucket"].to_list()
    assert result == [
        "BUCKET_A",
        "BUCKET_B",
        "OUT_OF_SCOPE_NO_BANKING77_OVERLAP",
        "UNMAPPED_UNKNOWN_PRODUCT",
    ]


# ---------------------------------------------------------------------------
# load_banking77_with_bucket
# ---------------------------------------------------------------------------


def _write_banking77_fixture(tmp_path, mapping, n_rows_per_split=3):
    categories = list(mapping["banking77_category_to_bucket"].keys())
    categories_path = tmp_path / "banking77_categories.json"
    categories_path.write_text(json.dumps(categories))

    train_path = tmp_path / "banking77_train.csv"
    test_path = tmp_path / "banking77_test.csv"
    train_rows = [
        {"text": f"train utterance {i}", "category": categories[i % len(categories)]}
        for i in range(n_rows_per_split)
    ]
    test_rows = [
        {"text": f"test utterance {i}", "category": categories[i % len(categories)]}
        for i in range(n_rows_per_split)
    ]
    pl.DataFrame(train_rows).write_csv(train_path)
    pl.DataFrame(test_rows).write_csv(test_path)
    return train_path, test_path, categories_path


def test_load_banking77_with_bucket_wrong_category_count_raises(tmp_path, valid_mapping):
    train_path, test_path, _ = _write_banking77_fixture(tmp_path, valid_mapping)
    bad_categories_path = tmp_path / "bad_categories.json"
    bad_categories_path.write_text(json.dumps(["intent_0", "intent_1"]))  # not 77
    with pytest.raises(ValueError, match="Expected 77"):
        tm.load_banking77_with_bucket(train_path, test_path, bad_categories_path, valid_mapping)


def test_load_banking77_with_bucket_unmapped_category_raises(tmp_path, valid_mapping):
    train_path, test_path, categories_path = _write_banking77_fixture(tmp_path, valid_mapping)
    # Corrupt the train file with a category absent from the mapping.
    df = pl.read_csv(train_path)
    df = pl.concat([df, pl.DataFrame({"text": ["rogue row"], "category": ["not_a_real_intent"]})])
    df.write_csv(train_path)
    with pytest.raises(ValueError, match="absent from taxonomy_mapping.yaml"):
        tm.load_banking77_with_bucket(train_path, test_path, categories_path, valid_mapping)


def test_load_banking77_with_bucket_success(tmp_path, valid_mapping):
    train_path, test_path, categories_path = _write_banking77_fixture(
        tmp_path, valid_mapping, n_rows_per_split=4
    )
    result = tm.load_banking77_with_bucket(train_path, test_path, categories_path, valid_mapping)
    assert result.height == 8  # 4 train + 4 test
    assert set(result["split"].unique().to_list()) == {"train", "test"}
    assert result["common_taxonomy_bucket"].null_count() == 0
    # spot-check: intent_0 (even index) must resolve to BUCKET_A per the fixture mapping
    row0 = result.filter(pl.col("category") == "intent_0").row(0, named=True)
    assert row0["common_taxonomy_bucket"] == "BUCKET_A"


# ---------------------------------------------------------------------------
# load_cfpb_with_bucket
# ---------------------------------------------------------------------------


def test_load_cfpb_with_bucket_is_lazy_and_adds_column(tmp_path, valid_mapping):
    cfpb_path = tmp_path / "cfpb_complaints.csv"
    pl.DataFrame(
        {
            "Date received": ["2026-01-01"],
            "Product": ["Checking or savings account"],
            "Sub-product": ["Checking account"],
            "Issue": ["Some issue"],
            "Sub-issue": ["Some sub-issue"],
            "Company public response": [""],
            "Company": ["Bank A"],
            "State": ["CA"],
            "ZIP code": ["90001"],
            "Tags": [""],
            "Submitted via": ["Web"],
            "Date sent to company": ["2026-01-02"],
            "Company response to consumer": ["Closed"],
            "Timely response?": ["Yes"],
            "Complaint ID": [1],
        }
    ).write_csv(cfpb_path)

    lazy = tm.load_cfpb_with_bucket(cfpb_path, valid_mapping)
    assert isinstance(lazy, pl.LazyFrame)
    collected = lazy.collect()
    assert collected["common_taxonomy_bucket"].to_list() == ["BUCKET_A"]


# ---------------------------------------------------------------------------
# mapping_coverage_report
# ---------------------------------------------------------------------------


def test_mapping_coverage_report_counts_and_fractions_sum_to_one(tmp_path, valid_mapping):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame(
        {
            "Product": ["Checking or savings account", "Checking or savings account", "Some other product"],
        }
    ).write_csv(cfpb_path)
    cfpb_lazy = pl.scan_csv(cfpb_path).with_columns(tm.cfpb_bucket_expr(valid_mapping))

    b77_df = pl.DataFrame(
        {
            "category": ["intent_0", "intent_0", "intent_1"],
            "common_taxonomy_bucket": ["BUCKET_A", "BUCKET_A", "BUCKET_B"],
        }
    )

    report = tm.mapping_coverage_report(cfpb_lazy, b77_df, valid_mapping)
    assert report["cfpb_fraction"].sum() == pytest.approx(1.0)
    assert report["banking77_fraction"].sum() == pytest.approx(1.0)
    bucket_a_row = report.filter(pl.col("common_taxonomy_bucket") == "BUCKET_A").row(0, named=True)
    assert bucket_a_row["cfpb_row_count"] == 2
    assert bucket_a_row["banking77_row_count"] == 2


# ---------------------------------------------------------------------------
# build_common_taxonomy_layer
# ---------------------------------------------------------------------------


def test_build_common_taxonomy_layer_writes_parquet_and_returns_counts(tmp_path, valid_mapping):
    cfpb_path = tmp_path / "cfpb.csv"
    pl.DataFrame({"Product": ["Checking or savings account", "Some other product"]}).write_csv(cfpb_path)
    cfpb_lazy = pl.scan_csv(cfpb_path).with_columns(tm.cfpb_bucket_expr(valid_mapping))

    b77_df = pl.DataFrame(
        {
            "category": ["intent_0", "intent_1", "intent_2"],
            "common_taxonomy_bucket": ["BUCKET_A", "BUCKET_B", "BUCKET_A"],
        }
    )

    out_dir = tmp_path / "gold"
    result = tm.build_common_taxonomy_layer(cfpb_lazy, b77_df, out_dir)

    assert (out_dir / "cfpb_common_taxonomy_gold.parquet").exists()
    assert (out_dir / "banking77_common_taxonomy_gold.parquet").exists()
    assert result["cfpb_rows_written"] == 2
    assert result["banking77_rows_written"] == 3
