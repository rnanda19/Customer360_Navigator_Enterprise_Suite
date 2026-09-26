"""
src/identity_resolution/run_demo.py — Customer360 Navigator

Runnable entry point for the SYNTHETIC identity-resolution demo (see entity_resolution.py's own
module docstring for the full disclosure of what this is and is not). Loads the three fictional
source CSVs under data/synthetic_identity_demo/, runs resolve_identities(), and writes two real
output files next to them:

  data/synthetic_identity_demo/output/identity_match_pairs.csv
      customer_360_id, source_system, source_customer_id, match_score, match_method,
      survivorship_rule, confidence  — exactly the schema specified in the architecture review.

  data/synthetic_identity_demo/output/golden_customer_record.csv
      customer_360_id, full_name, email, phone, address_line1, city, state, zip,
      survived_from_source, n_source_records, source_systems

Usage (from the project root):  python -m identity_resolution.run_demo
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from identity_resolution.entity_resolution import SourceRecord, resolve_identities

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic_identity_demo"
SOURCE_FILES = ["customer_source_a.csv", "customer_source_b.csv", "customer_source_c.csv"]


def load_synthetic_sources() -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for name in SOURCE_FILES:
        path = DEMO_DIR / name
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                records.append(SourceRecord(**row))
    return records


def main() -> None:
    records = load_synthetic_sources()
    pairs, golden, diag = resolve_identities(records)

    out_dir = DEMO_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    pairs_path = out_dir / "identity_match_pairs.csv"
    with open(pairs_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "customer_360_id",
                "source_system",
                "source_customer_id",
                "match_score",
                "match_method",
                "survivorship_rule",
                "confidence",
            ],
        )
        writer.writeheader()
        for p in pairs:
            writer.writerow(asdict(p))

    golden_path = out_dir / "golden_customer_record.csv"
    with open(golden_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "customer_360_id",
                "full_name",
                "email",
                "phone",
                "address_line1",
                "city",
                "state",
                "zip",
                "survived_from_source",
                "n_source_records",
                "source_systems",
            ],
        )
        writer.writeheader()
        for g in golden:
            writer.writerow(asdict(g))

    print(f"Real synthetic source rows read: {len(records)}")
    print(f"Real golden customer_360_id clusters resolved: {len(golden)}")
    print(f"Wrote: {pairs_path}")
    print(f"Wrote: {golden_path}")
    print(f"Probabilistic match threshold used: {diag['threshold']}")


if __name__ == "__main__":
    main()
