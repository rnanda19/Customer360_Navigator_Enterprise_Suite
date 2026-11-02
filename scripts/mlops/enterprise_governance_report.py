"""
scripts/mlops/enterprise_governance_report.py — Customer360 Navigator

PHASE E Stage C: real, runnable cross-BP (BP1-8) governance status report. Calls
src/mlops/enterprise_status.py's assess_all_bp_governance_status() - every value in the output
is read from this project's own real, already-committed config files and its real (local) MLflow
registry state; nothing here is computed or invented by this script.

Usage:
    python3 scripts/mlops/enterprise_governance_report.py [--out-dir governance]

Writes:
    <out-dir>/enterprise_governance_status.json  (machine-readable, one record per BP)
    <out-dir>/enterprise_governance_status.md    (human-readable table)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mlops.enterprise_status import assess_all_bp_governance_status  # noqa: E402


def build_markdown_table(statuses: list) -> str:
    header = (
        "| BP | Problem type | Lifecycle state | Governance applicable | MLflow champion | "
        "Artifact on disk | Config status |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for s in statuses:
        rows.append(
            f"| {s.bp_id} | {s.problem_type} | {s.lifecycle_state} | "
            f"{'yes' if s.governance_applicable else 'no'} | "
            f"{s.mlflow_registered_champion_version or '(none)'} | "
            f"{'yes' if s.artifact_present else 'no'} | `{s.config_status}` |"
        )
    return header + "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "governance"))
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    statuses = assess_all_bp_governance_status()
    generated_at = datetime.now(timezone.utc).isoformat()

    json_path = out_dir / "enterprise_governance_status.json"
    json_path.write_text(
        json.dumps(
            {"generated_at_utc": generated_at, "statuses": [s.to_dict() for s in statuses]},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    md_path = out_dir / "enterprise_governance_status.md"
    md_path.write_text(
        f"# Customer360 Navigator — Enterprise Governance Status (BP1-BP8)\n\n"
        f"Generated: {generated_at}\n\n"
        f"Real status, read live from this project's own config files and local MLflow registry "
        f"state - never fabricated. See src/mlops/enterprise_status.py's module docstring for "
        f"exactly how each field is derived.\n\n" + build_markdown_table(statuses)
    )

    print(f"Wrote {json_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)}")
    print()
    print(build_markdown_table(statuses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
