"""
tests/monitoring/test_model_registry.py — Customer360 Navigator

Real pytest coverage for src/monitoring/model_registry.py. Asserts against the exact real champion
identifiers already committed in each BP's own config YAML - re-confirming the aggregation reads
the right field for each BP's genuinely different schema, and is honest (None + note) where no
discrete field exists.
"""

from __future__ import annotations

from monitoring.model_registry import build_model_registry


def test_registry_has_exactly_one_entry_per_bp():
    registry = build_model_registry()
    assert {e["bp_id"] for e in registry} == {f"bp{i}" for i in range(1, 9)}


def test_bp1_bp2_bp3_champion_identifiers_match_real_config():
    registry = {e["bp_id"]: e for e in build_model_registry()}
    assert registry["bp1"]["champion_identifier"] == "logistic_regression"
    assert registry["bp2"]["champion_identifier"] == "xgboost"
    assert registry["bp3"]["champion_identifier"] == "xgboost"


def test_bp4_bp6_bp7_champion_identifiers_match_real_config():
    registry = {e["bp_id"]: e for e in build_model_registry()}
    assert registry["bp4"]["champion_identifier"] == "polars_lazy_streaming"
    assert registry["bp6"]["champion_identifier"] == "taxonomy_bucket_match"
    assert registry["bp7"]["champion_identifier"] == "correlation_aware_plus_lr_diagnostic"


def test_bp5_and_bp8_are_honestly_none_with_a_note_not_a_guessed_label():
    registry = {e["bp_id"]: e for e in build_model_registry()}
    assert registry["bp5"]["champion_identifier"] is None
    assert registry["bp5"]["note"] is not None
    assert registry["bp8"]["champion_identifier"] is None
    assert registry["bp8"]["note"] is not None
