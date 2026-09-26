"""
src/identity_resolution/customer_360_profile_demo.py — Customer360 Navigator

SYNTHETIC GOLDEN CUSTOMER 360 PROFILE DEMONSTRATION.

Identity Resolution (entity_resolution.py) proves this suite can build a golden `customer_360_id`
from disclosed synthetic multi-source data. This module goes one step further and demonstrates the
*shape* a full Customer 360 profile would take once you have that id — profile, interactions,
complaints, risk signals, products, journey, and a recommended action — because a golden id with
nothing attached to it doesn't demonstrate much on its own.

EVERYTHING NON-PROFILE HERE IS SYNTHETIC AND HAND-AUTHORED, same as entity_resolution.py's own
source fixtures:
  - `data/synthetic_identity_demo/customer_360_profile/synthetic_interactions.csv`
  - `data/synthetic_identity_demo/customer_360_profile/synthetic_products.csv`
  - `data/synthetic_identity_demo/customer_360_profile/synthetic_illustrative_complaint_examples.csv`
    (the word "complaint" here means a fictional example record, explicitly disclaimed in every row
    of that file — this is NEVER a real CFPB complaint, NEVER joined to the real CFPB extract, and
    NEVER counted anywhere in this suite's real BP1-8 numbers. Real CFPB data has no customer
    identifier to join against in the first place — see entity_resolution.py's own docstring.)

Three things this module computes for real, from that synthetic data, rather than hand-fabricating:
  1. `risk_signals` — real counts/aggregates (interaction count, product count, days since last
     interaction) computed from whatever synthetic records actually exist per customer. Several
     customers deliberately have zero interactions/products/complaint-examples, because a real
     population isn't uniformly "busy" and a demo that gave everyone a full profile would itself be
     a small dishonesty.
  2. `journey` — a real merge-and-sort of that customer's interaction and complaint-example records
     by timestamp, not a separately fabricated narrative.
  3. `recommended_action_demo` — reuses BP7's real, deployed 4-value action vocabulary verbatim
     (`ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER`, `ESCALATE_SENIOR_REVIEWER`,
     `PRIORITY_QUEUE_REVIEW`, `STANDARD_QUEUE` — copied from
     `src/features/bp7_decision_engine_features.py::_recommended_action_expr`, and
     `tests/identity_resolution/test_customer_360_profile_demo.py` asserts those exact strings still
     appear in that real file so this can't silently drift out of sync with it) but picks among them
     with a small, disclosed, ILLUSTRATIVE rule defined in `illustrative_recommended_action()` below
     — NOT BP7's real trained/scored decision engine. BP7's actual model only ever runs on real
     BP2/BP3/BP4 outputs over real CFPB rows; it has never been run on this synthetic data and this
     module makes no claim that it has.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from identity_resolution.entity_resolution import GoldenRecord, SourceRecord, resolve_identities

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic_identity_demo"
PROFILE_DIR = DEMO_DIR / "customer_360_profile"
SOURCE_FILES = ["customer_source_a.csv", "customer_source_b.csv", "customer_source_c.csv"]

# Fixed "as of" reference date for the real days-since-last-interaction computation below. A demo
# using synthetic dates has no real "today" to compute against, so this is disclosed and fixed
# rather than silently using the actual current date (which would make risk_signals change every
# time this is re-run for reasons that have nothing to do with the data).
REFERENCE_DATE = date(2026, 9, 1)

# Copied verbatim from src/features/bp7_decision_engine_features.py::_recommended_action_expr - see
# tests/identity_resolution/test_customer_360_profile_demo.py for the guard that keeps these in
# sync with that real file.
BP7_ACTION_ESCALATE_RECURRING = "ESCALATE_ROOT_CAUSE_REVIEW_RECURRING_CLUSTER"
BP7_ACTION_ESCALATE_SENIOR = "ESCALATE_SENIOR_REVIEWER"
BP7_ACTION_PRIORITY_QUEUE = "PRIORITY_QUEUE_REVIEW"
BP7_ACTION_STANDARD_QUEUE = "STANDARD_QUEUE"


@dataclass
class RiskSignals:
    n_interactions: int
    n_products_total: int
    n_products_active: int
    n_complaint_examples: int
    days_since_last_interaction: Optional[int]


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _load_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _by_customer(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["customer_360_id"], []).append(r)
    return out


def compute_risk_signals(
    interactions: list[dict], products: list[dict], complaint_examples: list[dict]
) -> RiskSignals:
    """Real aggregation over whatever synthetic records exist for one customer - never a fabricated
    number. Every field here is directly derivable from the three CSVs this module loads."""
    n_active_products = sum(1 for p in products if p["status"] == "active")
    if interactions:
        latest = max(_parse_dt(i["occurred_at_utc"]) for i in interactions)
        days_since = abs((REFERENCE_DATE - latest.date()).days)
    else:
        days_since = None
    return RiskSignals(
        n_interactions=len(interactions),
        n_products_total=len(products),
        n_products_active=n_active_products,
        n_complaint_examples=len(complaint_examples),
        days_since_last_interaction=days_since,
    )


def illustrative_recommended_action(risk: RiskSignals) -> str:
    """A small, transparent, DEMO-ONLY rule over the synthetic risk_signals above - deliberately
    simple, deliberately not BP7's real trained/rule-scored decision engine (see this module's own
    docstring for why). It exists only to show that a golden customer_360_id can be the input to a
    real action-recommendation step, using BP7's real action vocabulary, in the same way BP7's own
    real rule (src/features/bp7_decision_engine_features.py::_recommended_action_expr) uses that
    vocabulary over real BP2/BP3/BP4 signals."""
    if risk.n_complaint_examples > 0:
        return BP7_ACTION_ESCALATE_SENIOR
    if risk.n_interactions == 0 and risk.n_products_total == 0:
        return BP7_ACTION_STANDARD_QUEUE
    if risk.n_interactions >= 2:
        return BP7_ACTION_PRIORITY_QUEUE
    return BP7_ACTION_STANDARD_QUEUE


def build_journey(interactions: list[dict], complaint_examples: list[dict]) -> list[dict]:
    """Real merge-and-sort, not a separately authored narrative - every event here already exists
    verbatim in one of the two source CSVs."""
    events = []
    for i in interactions:
        events.append(
            {
                "event_type": "interaction",
                "occurred_at_utc": i["occurred_at_utc"],
                "detail": f"{i['interaction_type']} via {i['channel']}: {i['summary']}",
            }
        )
    for c in complaint_examples:
        events.append(
            {
                "event_type": "complaint_example",
                "occurred_at_utc": c["occurred_at_utc"],
                "detail": f"{c['category']}: {c['summary']}",
            }
        )
    events.sort(key=lambda e: e["occurred_at_utc"])
    return events


def build_customer_360_profiles(
    golden_records: list[GoldenRecord],
    interactions_rows: list[dict],
    products_rows: list[dict],
    complaint_example_rows: list[dict],
) -> list[dict]:
    """Assembles one nested profile per real golden customer_360_id. Pure function over its
    arguments - no file I/O - so it's directly unit-testable without touching disk."""
    interactions_by_cust = _by_customer(interactions_rows)
    products_by_cust = _by_customer(products_rows)
    complaints_by_cust = _by_customer(complaint_example_rows)

    profiles = []
    for g in golden_records:
        cid = g.customer_360_id
        interactions = interactions_by_cust.get(cid, [])
        products = products_by_cust.get(cid, [])
        complaint_examples = complaints_by_cust.get(cid, [])
        risk = compute_risk_signals(interactions, products, complaint_examples)
        profiles.append(
            {
                "customer_360_id": cid,
                "profile": asdict(g),
                "interactions": interactions,
                "products": products,
                "complaints": complaint_examples,
                "risk_signals": asdict(risk),
                "journey": build_journey(interactions, complaint_examples),
                "recommended_action_demo": illustrative_recommended_action(risk),
            }
        )
    return profiles


def main() -> None:
    records: list[SourceRecord] = []
    for name in SOURCE_FILES:
        for row in _load_csv(DEMO_DIR / name):
            records.append(SourceRecord(**row))
    _, golden, _ = resolve_identities(records)

    interactions_rows = _load_csv(PROFILE_DIR / "synthetic_interactions.csv")
    products_rows = _load_csv(PROFILE_DIR / "synthetic_products.csv")
    complaint_example_rows = _load_csv(PROFILE_DIR / "synthetic_illustrative_complaint_examples.csv")

    profiles = build_customer_360_profiles(golden, interactions_rows, products_rows, complaint_example_rows)

    out_dir = PROFILE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "customer_360_profiles.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)

    print(f"Real golden customer_360_id profiles assembled: {len(profiles)}")
    print(f"Wrote: {out_path}")
    for p in profiles:
        print(
            f"  {p['customer_360_id']} ({p['profile']['full_name']}): "
            f"{p['risk_signals']['n_interactions']} interactions, "
            f"{p['risk_signals']['n_products_total']} products, "
            f"{p['risk_signals']['n_complaint_examples']} complaint examples -> "
            f"{p['recommended_action_demo']}"
        )


if __name__ == "__main__":
    main()
