"""
src/monitoring/model_registry.py — Customer360 Navigator

A real, honest consolidated Model Registry view — aggregation only, never a new computation. Every
value below is read directly from each BP's own already-committed `configs/<bp>.yaml` Gate 3 block
(the same file each BP's own gate notebooks write to), so this can never disagree with what that
BP's own config already states.

WHY THE PER-BP FIELD MAP: BP1-8 are eight structurally different kinds of problems (trained
classifiers, a benchmark pipeline, an association/reporting tool, a retrieval strategy, a rule
engine, a Gold-layer aggregation) and their Gate 3 config blocks were never designed to share one
schema — forcing a single generic "champion_model" key across all eight would mean either silently
misreading a field or inventing one that was never there. This module names, per BP, exactly which
real config key (if any) holds that BP's champion identifier, and is honest — `model_name: None`
with a `note` — for the two BPs (BP5, BP8) whose config genuinely has no single discrete
model-name field, rather than guessing a label.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGS_DIR = REPO_ROOT / "configs"

# (config filename, dotted path to the real champion-identifier field, or None with a note).
_REGISTRY_SOURCES: dict[str, dict] = {
    "bp1": {
        "config_file": "bp1_customer_intent_classification.yaml",
        "champion_path": ("gate3_model_benchmark", "champion_model"),
        "problem_type": "trained_classifier",
    },
    "bp2": {
        "config_file": "bp2_customer_friction_classification.yaml",
        "champion_path": ("gate3_model_benchmark", "champion_model"),
        "problem_type": "trained_classifier",
    },
    "bp3": {
        "config_file": "bp3_complaint_escalation_prediction.yaml",
        "champion_path": ("gate3_model_benchmark", "champion_model"),
        "problem_type": "trained_classifier",
    },
    "bp4": {
        "config_file": "bp4_customer_journey_analytics.yaml",
        "champion_path": ("champion_pipeline",),
        "problem_type": "benchmark_pipeline",
    },
    "bp5": {
        "config_file": "bp5_root_cause_driver_analytics.yaml",
        "champion_path": None,
        "note": (
            "Association/reporting BP (per-category univariate logistic regression) - no single "
            "discrete model-name config field; see "
            "docs/architecture/bp5_root_cause_driver_analytics_architecture.md"
        ),
        "problem_type": "association_reporting",
    },
    "bp6": {
        "config_file": "bp6_genai_resolution_assistant.yaml",
        "champion_path": ("gate3_retrieval_benchmark", "champion_strategy"),
        "problem_type": "retrieval_strategy",
    },
    "bp7": {
        "config_file": "bp7_customer_navigator_decision_engine.yaml",
        "champion_path": ("champion_rule_scheme",),
        "problem_type": "rule_engine",
    },
    "bp8": {
        "config_file": "bp8_executive_product_analytics.yaml",
        "champion_path": None,
        "note": "Gold-layer aggregation only - never treated as a modeling problem.",
        "problem_type": "gold_layer_aggregation",
    },
}


def _dig(d: dict, path: tuple[str, ...]) -> Optional[object]:
    cur: object = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def build_model_registry(configs_dir: Path = CONFIGS_DIR) -> list[dict]:
    """Real read of every BP's own committed config file - no fabricated entries, and an explicit
    None + note for the two BPs with no discrete champion field."""
    entries = []
    for bp_id, source in _REGISTRY_SOURCES.items():
        config_path = configs_dir / source["config_file"]
        raw = yaml.safe_load(config_path.read_text())
        champion_path = source["champion_path"]
        champion = _dig(raw, champion_path) if champion_path else None
        entries.append(
            {
                "bp_id": bp_id,
                "bp_name": raw.get("bp_name", bp_id),
                "status": raw.get("status"),
                "problem_type": source["problem_type"],
                "champion_identifier": champion,
                "note": source.get("note"),
                "config_file": str(config_path.relative_to(REPO_ROOT)),
            }
        )
    return entries


def main() -> None:
    registry = build_model_registry()
    print("Real consolidated Model Registry (read live from every BP's own committed config):")
    for e in registry:
        champ = e["champion_identifier"] if e["champion_identifier"] is not None else "(none)"
        print(f"  {e['bp_id']}: {champ}  [{e['problem_type']}]  status={e['status']}")
        if e["note"]:
            print(f"      note: {e['note']}")


if __name__ == "__main__":
    main()
