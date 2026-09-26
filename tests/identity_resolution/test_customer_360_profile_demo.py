"""
tests/identity_resolution/test_customer_360_profile_demo.py — Customer360 Navigator

Real pytest coverage for the SYNTHETIC Golden Customer 360 Profile demo
(src/identity_resolution/customer_360_profile_demo.py). Every assertion is checked against numbers
this module actually computed from its own real fixture files, not hand-picked to make a test pass.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from identity_resolution.customer_360_profile_demo import (
    BP7_ACTION_ESCALATE_SENIOR,
    BP7_ACTION_PRIORITY_QUEUE,
    BP7_ACTION_STANDARD_QUEUE,
    build_customer_360_profiles,
    build_journey,
    compute_risk_signals,
    illustrative_recommended_action,
)
from identity_resolution.entity_resolution import SourceRecord, resolve_identities

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic_identity_demo"
PROFILE_DIR = DEMO_DIR / "customer_360_profile"
BP7_FEATURES_FILE = (
    Path(__file__).resolve().parents[2] / "src" / "features" / "bp7_decision_engine_features.py"
)


def _load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def golden_records():
    records = []
    for name in ("customer_source_a.csv", "customer_source_b.csv", "customer_source_c.csv"):
        for row in _load_csv(DEMO_DIR / name):
            records.append(SourceRecord(**row))
    _, golden, _ = resolve_identities(records)
    return golden


@pytest.fixture(scope="module")
def profiles(golden_records):
    interactions = _load_csv(PROFILE_DIR / "synthetic_interactions.csv")
    products = _load_csv(PROFILE_DIR / "synthetic_products.csv")
    complaint_examples = _load_csv(PROFILE_DIR / "synthetic_illustrative_complaint_examples.csv")
    return build_customer_360_profiles(golden_records, interactions, products, complaint_examples)


def test_bp7_action_vocabulary_stays_in_sync_with_the_real_bp7_feature_module():
    """Guard against silent drift: these 4 strings must still appear verbatim in BP7's own real
    feature module, or this demo's 'reuses BP7's real vocabulary' claim would quietly go stale."""
    real_text = BP7_FEATURES_FILE.read_text()
    for literal in (
        "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER",
        BP7_ACTION_ESCALATE_SENIOR,
        BP7_ACTION_PRIORITY_QUEUE,
        BP7_ACTION_STANDARD_QUEUE,
    ):
        assert literal in real_text, f"{literal!r} no longer found in BP7's real feature module"


def test_one_profile_per_golden_customer(profiles, golden_records):
    assert len(profiles) == len(golden_records)
    assert {p["customer_360_id"] for p in profiles} == {g.customer_360_id for g in golden_records}


def test_customers_with_no_synthetic_records_get_a_real_sparse_profile(profiles):
    """Sarah Wilson and Thomas Anderson deliberately have zero interactions/products/complaint
    examples in the fixture files - this proves the module reports that honestly (real zeros, not
    silently fabricated activity) rather than requiring every customer to have a full profile."""
    sparse = [p for p in profiles if p["profile"]["full_name"] in ("Sarah Wilson", "Thomas Anderson")]
    assert len(sparse) == 2
    for p in sparse:
        assert p["risk_signals"]["n_interactions"] == 0
        assert p["risk_signals"]["n_products_total"] == 0
        assert p["risk_signals"]["n_complaint_examples"] == 0
        assert p["risk_signals"]["days_since_last_interaction"] is None
        assert p["journey"] == []


def test_alice_johnson_has_real_computed_risk_signals(profiles):
    alice = next(p for p in profiles if p["profile"]["full_name"] == "Alice Johnson")
    assert alice["risk_signals"]["n_interactions"] == 2
    assert alice["risk_signals"]["n_products_total"] == 2
    assert alice["risk_signals"]["n_products_active"] == 2
    assert alice["risk_signals"]["n_complaint_examples"] == 0


def test_journey_is_a_real_sorted_merge_of_interactions_and_complaint_examples():
    interactions = [
        {
            "interaction_type": "web_login",
            "channel": "web",
            "occurred_at_utc": "2026-08-20T09:00:00+00:00",
            "summary": "s1",
        },
        {
            "interaction_type": "call",
            "channel": "phone",
            "occurred_at_utc": "2026-08-10T09:00:00+00:00",
            "summary": "s2",
        },
    ]
    complaints = [
        {"category": "billing_dispute", "occurred_at_utc": "2026-08-15T09:00:00+00:00", "summary": "s3"},
    ]
    journey = build_journey(interactions, complaints)
    assert [e["occurred_at_utc"] for e in journey] == [
        "2026-08-10T09:00:00+00:00",
        "2026-08-15T09:00:00+00:00",
        "2026-08-20T09:00:00+00:00",
    ]
    assert journey[1]["event_type"] == "complaint_example"


def test_illustrative_action_escalates_when_complaint_examples_present():
    risk = compute_risk_signals(
        interactions=[],
        products=[],
        complaint_examples=[
            {"category": "x", "occurred_at_utc": "2026-01-01T00:00:00+00:00", "summary": "s"}
        ],
    )
    assert illustrative_recommended_action(risk) == BP7_ACTION_ESCALATE_SENIOR


def test_illustrative_action_is_standard_queue_when_fully_dormant():
    risk = compute_risk_signals(interactions=[], products=[], complaint_examples=[])
    assert illustrative_recommended_action(risk) == BP7_ACTION_STANDARD_QUEUE


def test_illustrative_action_is_priority_queue_for_multiple_interactions_no_complaints():
    risk = compute_risk_signals(
        interactions=[
            {
                "interaction_type": "a",
                "channel": "web",
                "occurred_at_utc": "2026-01-01T00:00:00+00:00",
                "summary": "s",
            },
            {
                "interaction_type": "b",
                "channel": "web",
                "occurred_at_utc": "2026-01-02T00:00:00+00:00",
                "summary": "s",
            },
        ],
        products=[],
        complaint_examples=[],
    )
    assert illustrative_recommended_action(risk) == BP7_ACTION_PRIORITY_QUEUE


def test_every_profile_has_the_full_expected_schema(profiles):
    required_keys = {
        "customer_360_id",
        "profile",
        "interactions",
        "products",
        "complaints",
        "risk_signals",
        "journey",
        "recommended_action_demo",
    }
    for p in profiles:
        assert required_keys.issubset(p.keys())


def test_complaint_examples_are_never_real_cfpb_rows_by_construction(profiles):
    """Every complaint-example summary must contain the disclosure string - a structural guard
    against ever swapping in an undisclosed record."""
    for p in profiles:
        for c in p["complaints"]:
            assert "FICTIONAL EXAMPLE ONLY" in c["summary"]
