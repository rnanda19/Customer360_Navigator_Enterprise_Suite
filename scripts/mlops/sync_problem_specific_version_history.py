"""
scripts/mlops/sync_problem_specific_version_history.py — Customer360 Navigator

PHASE I: real, runnable sync of BP4-8's problem-specific champion-identifier version history.
Calls src/mlops/problem_specific_version_history.py's sync_version_history_from_enterprise_status()
- every value is read from this project's own real, already-committed config files via
src/mlops/enterprise_status.py; nothing here is computed or invented by this script. Safe to run
repeatedly (and intended to be re-run whenever a BP4-8 config champion identifier might have
changed) - a run where nothing changed writes nothing new and reports zero entries written.

Usage:
    python3 scripts/mlops/sync_problem_specific_version_history.py [--out-dir governance]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mlops.problem_specific_version_history import (  # noqa: E402
    get_version_history,
    sync_version_history_from_enterprise_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "governance"))
    args = parser.parse_args()
    log_path = Path(args.out_dir) / "problem_specific_version_history.jsonl"

    written = sync_version_history_from_enterprise_status(log_path=log_path)
    if written:
        print(f"Wrote {len(written)} new version-history entr{'y' if len(written) == 1 else 'ies'}:")
        for entry in written:
            print(
                f"  {entry.bp_id} ({entry.problem_type}): {entry.previous_identifier!r} -> "
                f"{entry.config_champion_identifier!r} [{entry.change_type}]"
            )
    else:
        print("No BP4-8 config champion identifier has changed since the last sync - nothing written.")

    print()
    print(f"Full log: {log_path.relative_to(REPO_ROOT) if log_path.is_relative_to(REPO_ROOT) else log_path}")
    for bp_id in ("bp4", "bp5", "bp6", "bp7", "bp8"):
        history = get_version_history(bp_id, log_path=log_path)
        if history:
            latest_identifier = history[-1]["config_champion_identifier"]
            plural = "y" if len(history) == 1 else "ies"
            print(f"  {bp_id}: {len(history)} entr{plural}, current = {latest_identifier!r}")
        else:
            print(f"  {bp_id}: no version history (no discrete champion identifier for this problem type)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
