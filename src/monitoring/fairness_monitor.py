"""
src/monitoring/fairness_monitor.py — Customer360 Navigator

Consolidates this suite's own real, already-computed disparate-impact findings (BP3's and BP7's
own Gate 4 artifacts) into one real, re-derivable pass/fail view against the standard four-fifths
rule (adverse impact ratio >= 0.8 = not flagged). This module does not compute any new fairness
statistic of its own — every number it reports is read directly from the same real Gate 4 JSON
files the BP3 and BP7 dashboards already cite; this is real aggregation, never a new computation
whose correctness would need separate re-validation.

WHY ONLY BP3 AND BP7: these are the only two BPs in this suite with a real disparate-impact check
in their own Gate 4 artifacts (see docs/PRODUCTION_READINESS_MATRIX.md's Fairness column for why
BP1/BP2/BP4/BP5/BP6/BP8 are each structurally not_applicable or no_check - this module doesn't
invent a check for them).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FOUR_FIFTHS_THRESHOLD = 0.8

BP3_GATE4_FILE = (
    REPO_ROOT
    / "notebooks"
    / "bp3_complaint_escalation_prediction"
    / "artifacts"
    / "gate4_disparate_impact_investigation.json"
)
BP7_GATE4_FILE = (
    REPO_ROOT
    / "notebooks"
    / "bp7_customer_navigator_decision_engine"
    / "artifacts"
    / "gate4_disparate_impact_audit.json"
)


def read_bp3_fairness_status(path: Path = BP3_GATE4_FILE) -> dict:
    data = json.loads(path.read_text())
    ratio = data["source_adverse_impact_ratio_tags"]
    return {
        "bp": "BP3",
        "check_name": "disparate_impact_ratio_on_tags_field",
        "adverse_impact_ratio": ratio,
        "flagged": bool(data["source_flagged"]),
        "passes_four_fifths_rule": ratio >= FOUR_FIFTHS_THRESHOLD,
        "champion_model": data["champion_model"],
        "generated_at_utc": data["generated_at_utc"],
    }


def read_bp7_fairness_status(path: Path = BP7_GATE4_FILE) -> dict:
    data = json.loads(path.read_text())
    ratio = data["adverse_impact_ratio"]
    return {
        "bp": "BP7",
        "check_name": "disparate_impact_ratio_on_bp3_carried_forward_tags_group",
        "adverse_impact_ratio": ratio,
        "flagged": bool(data["flagged_four_fifths_rule"]),
        "passes_four_fifths_rule": ratio >= FOUR_FIFTHS_THRESHOLD,
        "lowest_selection_rate_group": data.get("lowest_selection_rate_group"),
        "highest_selection_rate_group": data.get("highest_selection_rate_group"),
    }


def consolidated_fairness_report() -> dict:
    bp3 = read_bp3_fairness_status()
    bp7 = read_bp7_fairness_status()
    any_flagged = bp3["flagged"] or bp7["flagged"]
    return {
        "four_fifths_threshold": FOUR_FIFTHS_THRESHOLD,
        "checks": [bp3, bp7],
        "any_check_flagged": any_flagged,
        "overall_status": (
            "GOVERNANCE REVIEW REQUIRED - at least one real check is flagged"
            if any_flagged
            else "ALL CHECKS PASS"
        ),
    }


def main() -> None:
    report = consolidated_fairness_report()
    print(f"Real consolidated fairness report (four-fifths threshold: {report['four_fifths_threshold']}):")
    for check in report["checks"]:
        status = "FLAGGED" if check["flagged"] else "PASS"
        print(f"  {check['bp']} ({check['check_name']}): ratio={check['adverse_impact_ratio']} -> {status}")
    print(f"Overall: {report['overall_status']}")


if __name__ == "__main__":
    main()
