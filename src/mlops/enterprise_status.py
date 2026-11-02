"""
src/mlops/enterprise_status.py — Customer360 Navigator

PHASE E Stage C: unified, cross-BP (BP1-BP8) governance and lifecycle status view. Real
aggregation only, exactly like src/monitoring/model_registry.py's own design principle - this
module computes nothing new about any model's quality; it reads real, already-computed facts
from three existing, independently-tested sources and combines them into one honest per-BP
record:

  1. src/monitoring/model_registry.py's build_model_registry() - each BP's own committed Gate 3
     config evidence (champion identifier, problem type, gate status string). Reused, not
     duplicated - this module never re-derives what that one already computes correctly.
  2. src/mlops/registry.py's get_version_by_alias() - whether that BP has a real, MLflow-
     registered model version, and whether one currently holds the "champion"/"challenger" alias.
     Returns None gracefully for a BP with no registered model yet (never raises).
  3. A real on-disk artifact check under models/<bp_id>/ - whether a real trained artifact file
     actually exists, and its real SHA-256 if so (via src/mlops/tracking.py's existing hash
     utility - reused, not reimplemented).

WHY NOT ONE SHARED THRESHOLD/REGISTRATION SCHEMA FOR ALL 8 BPs: BP1-8 are eight structurally
different kinds of problems (trained classifiers, a benchmark pipeline, an association/reporting
tool, a retrieval strategy, a rule engine, a Gold-layer aggregation - see model_registry.py's own
docstring for the full breakdown). This module reuses that existing problem_type classification
rather than re-deriving it, and marks every BP whose problem_type is not "trained_classifier" as
governance_applicable=False for the MLflow-registry/threshold machinery in governance.py - not
because those BPs have no governance at all (BP3/BP7 have real disparate-impact checks via
fairness_monitor.py; BP5/BP7 have real Gate 6 pytest-based governance recorded in their own
configs), but because forcing them through a classifier-threshold schema that doesn't fit them
would be exactly the kind of invented, ill-fitting governance this project's zero-fabrication
standard rules out.

LIFECYCLE STATE DERIVATION (real evidence only, never asserted - see _derive_lifecycle_state):
  - PRODUCTION: a real MLflow version currently holds the "champion" alias AND a real artifact
    file is present on disk for this BP.
  - STAGING: a real MLflow version holds "champion" or "challenger", but the on-disk artifact
    check above did not confirm a file (registry says registered; local disk doesn't show it -
    this is the real, honest state for a registry entry created on a different machine/session
    than the one running this check, e.g. models/ is gitignored and not committed).
  - VALIDATION: no MLflow registration exists for this BP, but its own config shows a real,
    already-confirmed Gate 3+ evaluation (candidates benchmarked, champion identified in that
    BP's own documented methodology) - evaluated, not yet operationally registered.
  - DEVELOPMENT: neither of the above - no real MLflow registration and no confirmed Gate 3+
    evidence yet.
  - DEPRECATED / ARCHIVED: never asserted by this function - both are valid LifecycleState values
    a human, or a future real retirement/rollback event, can set explicitly.

As of this writing, the real, honest state across this project is: BP1 is the only BP with both a
real MLflow registration AND a real local artifact (Phase D's real BANKING77 training run) - every
other BP reports VALIDATION or DEVELOPMENT, per its own real config evidence, and this module says
so plainly rather than fabricating a registration that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from mlops import registry as mlops_registry
from mlops.governance import MODEL_PERFORMANCE_THRESHOLDS, LifecycleState
from mlops.tracking import compute_file_sha256
from monitoring.model_registry import build_model_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "models"

# Real, already-established extensions this project's own model_persistence.py and training
# scripts actually produce (joblib for BP1-3/BP7's sklearn-family pipelines, .cbm for a real
# CatBoost booster, .onnx for a possible future exported artifact) - not a generic "any file"
# scan that would also match a stray .gitkeep or README.
_ARTIFACT_EXTENSIONS = (".joblib", ".pkl", ".cbm", ".onnx")


@dataclass
class ArtifactStatus:
    bp_id: str
    present: bool
    files: list[str] = field(default_factory=list)
    sha256: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"bp_id": self.bp_id, "present": self.present, "files": self.files, "sha256": self.sha256}


@dataclass
class BPGovernanceStatus:
    bp_id: str
    bp_name: str
    problem_type: str
    governance_applicable: bool
    config_status: Optional[str]
    config_champion_identifier: Optional[str]
    config_note: Optional[str]
    mlflow_registered_champion_version: Optional[str]
    mlflow_registered_challenger_version: Optional[str]
    artifact_present: bool
    artifact_files: list[str]
    lifecycle_state: str
    has_governance_thresholds: bool

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def real_artifact_status(
    bp_id: str, models_dir: Optional[Path] = None, models_subdir_name: Optional[str] = None
) -> ArtifactStatus:
    """Real on-disk check - lists real files under models/<models_subdir_name>/ (this project's
    real convention names each BP's model directory after its FULL config stem, e.g.
    "bp1_customer_intent_classification", not the short "bp1" id - models_subdir_name defaults to
    bp_id only for direct/test callers that don't have the real full name handy) matching this
    project's own known artifact extensions, and computes each one's real SHA-256 via
    tracking.py's existing compute_file_sha256() (which itself returns path/size_bytes/sha256 -
    only the sha256 field is kept here, since this module's own ArtifactStatus.sha256 is
    documented as a filename -> hash map). Never fabricates a result for a BP with nothing on
    disk: present=False, files=[] is the honest, expected state for every BP except BP1 on a
    fresh checkout, because models/ is gitignored (see MLOPS_ARCHITECTURE.md's "Why BP1 and not
    every BP" section) - this is not an error, it is the real, disclosed state of this
    repository today.

    `models_dir` defaults to None (resolved to the module-level MODELS_DIR INSIDE this function
    body, not as a function-default bound at import time) deliberately - Phase D already hit this
    exact "default argument captured once at def-time, monkeypatch has no effect" bug once before
    (src/mlops/audit_log.py's log_path default - see MLOPS_TEST_REPORT.md) and the fix there was
    the same one applied here: resolve the module global dynamically, so tests (and any future
    caller) that monkeypatch enterprise_status.MODELS_DIR actually take effect."""
    resolved_models_dir = models_dir if models_dir is not None else MODELS_DIR
    subdir = models_subdir_name or bp_id
    bp_dir = resolved_models_dir / subdir
    if not bp_dir.is_dir():
        return ArtifactStatus(bp_id=bp_id, present=False)
    files = sorted(f for f in bp_dir.iterdir() if f.is_file() and f.suffix.lower() in _ARTIFACT_EXTENSIONS)
    sha256 = {f.name: compute_file_sha256(f)["sha256"] for f in files}
    return ArtifactStatus(bp_id=bp_id, present=bool(files), files=[f.name for f in files], sha256=sha256)


def _derive_lifecycle_state(
    *,
    champion_version: Optional[str],
    challenger_version: Optional[str],
    artifact_present: bool,
    config_status: Optional[str],
) -> str:
    if champion_version is not None and artifact_present:
        return LifecycleState.PRODUCTION.value
    if champion_version is not None or challenger_version is not None:
        return LifecycleState.STAGING.value
    if config_status and "gate3" in config_status:
        return LifecycleState.VALIDATION.value
    return LifecycleState.DEVELOPMENT.value


def assess_bp_governance_status(
    bp_id: str, registry_entries: Optional[list[dict]] = None
) -> BPGovernanceStatus:
    """Compose one real, honest governance record for `bp_id` from the three sources named in
    this module's docstring. `registry_entries` lets a caller pass a pre-computed
    build_model_registry() result once when checking all 8 BPs (avoids 8 redundant re-reads of
    every config file); computed fresh if omitted - and also lets tests pass a synthetic entry
    for a bp_id not in the real configs/ directory, without touching real config files."""
    entries = registry_entries if registry_entries is not None else build_model_registry()
    entry = next((e for e in entries if e["bp_id"] == bp_id), None)
    if entry is None:
        raise ValueError(f"No model_registry.py entry found for bp_id={bp_id!r}")

    problem_type = entry["problem_type"]
    governance_applicable = problem_type == "trained_classifier"

    champion = mlops_registry.get_version_by_alias(bp_id, "champion")
    challenger = mlops_registry.get_version_by_alias(bp_id, "challenger")
    # Real convention: models/<full config stem>/, not models/<short bp_id>/ - derived from the
    # same config_file path build_model_registry() already reads, never a second hand-maintained
    # mapping that could silently drift out of sync with it.
    config_file = entry.get("config_file")
    models_subdir_name = Path(config_file).stem if config_file else bp_id
    artifact = real_artifact_status(bp_id, models_subdir_name=models_subdir_name)

    lifecycle_state = _derive_lifecycle_state(
        champion_version=champion.version if champion else None,
        challenger_version=challenger.version if challenger else None,
        artifact_present=artifact.present,
        config_status=entry.get("status"),
    )

    champion_identifier = entry.get("champion_identifier")
    return BPGovernanceStatus(
        bp_id=bp_id,
        bp_name=entry["bp_name"],
        problem_type=problem_type,
        governance_applicable=governance_applicable,
        config_status=entry.get("status"),
        config_champion_identifier=str(champion_identifier) if champion_identifier is not None else None,
        config_note=entry.get("note"),
        mlflow_registered_champion_version=champion.version if champion else None,
        mlflow_registered_challenger_version=challenger.version if challenger else None,
        artifact_present=artifact.present,
        artifact_files=artifact.files,
        lifecycle_state=lifecycle_state,
        has_governance_thresholds=bp_id in MODEL_PERFORMANCE_THRESHOLDS,
    )


def assess_all_bp_governance_status() -> list[BPGovernanceStatus]:
    """Real status for every BP1-8, in configs/ order. The single public entry point
    scripts/mlops/enterprise_governance_report.py calls."""
    entries = build_model_registry()
    return [assess_bp_governance_status(e["bp_id"], registry_entries=entries) for e in entries]
