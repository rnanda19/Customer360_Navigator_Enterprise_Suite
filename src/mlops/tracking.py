"""
src/mlops/tracking.py — Customer360 Navigator

PHASE D (Enterprise MLOps, Model Registry and Model Governance): real MLflow experiment-tracking
integration, built once and imported by every BP's training/registration path rather than each
duplicating MLflow boilerplate (the same HYPER shared-component pattern as
src/models/model_persistence.py).

This module is deliberately thin over the real `mlflow` SDK - it does not reimplement tracking,
it configures it (a single local, file/sqlite-backed tracking store so the project needs no
external MLflow server) and standardizes what every run records: real dataset fingerprints
(sha256 of the actual file(s) used, never invented), the real git commit SHA of the working tree
at run time, real installed software versions (read from importlib.metadata, never hardcoded),
and the caller's own params/metrics.

Design note on store choice: MLflow's Model Registry (used by src/mlops/registry.py) requires a
database-backed backend store - the plain local FileStore does not support registered models in
this MLflow version. A local SQLite file is the smallest real backend that supports both
tracking and the registry with zero external infrastructure, consistent with this project's
existing "no managed external services" posture (see SECRETS_MANAGEMENT.md, MLOPS_OBSERVABILITY.md).
The SQLite file and its artifact store live under `mlruns/` at the repo root, gitignored (see
.gitignore) exactly like `models/**/*.joblib` already is - tracking runs and registered artifacts
are machine-local outputs, never committed, same rule already applied to every other BP's
trained model file.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MLRUNS_DIR = REPO_ROOT / "mlruns"

# Packages whose installed version is always worth recording for reproducibility - picked
# because every BP's training path imports at least one of these (grep-verified against
# src/models/*.py and requirements.txt), never an exhaustive `pip freeze` dump (which would bury
# the handful of versions that actually matter for reproducing a given run's numbers).
REPRODUCIBILITY_PACKAGES: tuple[str, ...] = (
    "scikit-learn",
    "numpy",
    "pandas",
    "scipy",
    "mlflow",
    "joblib",
    "xgboost",
    "lightgbm",
    "catboost",
)


def get_tracking_uri(mlruns_dir: Path = DEFAULT_MLRUNS_DIR) -> str:
    """Return the sqlite-backed MLflow tracking URI this project uses for both experiment
    tracking and the Model Registry. Reads MLFLOW_TRACKING_URI from the environment first (so a
    future real MLflow server, reached via credentials sourced from the project's existing Vault
    PoC - see SECRETS_MANAGEMENT.md - can override this with zero code changes), falling back to
    a local sqlite file under `mlruns_dir` when unset."""
    env_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if env_uri:
        return env_uri
    mlruns_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{mlruns_dir / 'mlflow.db'}"


def get_artifact_location(mlruns_dir: Path = DEFAULT_MLRUNS_DIR) -> str:
    """Local artifact store root for experiments created against the sqlite tracking URI above.
    Only used when MLFLOW_TRACKING_URI is not externally overridden."""
    artifacts_dir = mlruns_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir.as_uri()


def compute_file_sha256(path: Path) -> dict[str, Any]:
    """Real sha256 + byte size of one file, computed by actually reading it - the same pattern
    already used by src/models/model_persistence.py's save_model_bundle() and the Phase C BP7 CI
    artifact-validation step, never invented or looked up from a cached value."""
    path = Path(path)
    file_bytes = path.read_bytes()
    return {
        "path": str(path),
        "size_bytes": len(file_bytes),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
    }


def compute_dataset_fingerprint(dataset_paths: list[Path]) -> dict[str, Any]:
    """Real, reproducible fingerprint of the dataset(s) used to train/evaluate a model: per-file
    sha256 + size for every path given, plus one combined sha256 over the sorted per-file hashes
    (order-independent, so passing the same files in a different order yields the same combined
    fingerprint). Raises FileNotFoundError if any path does not exist - a fingerprint silently
    computed over a missing file would be worse than no fingerprint at all."""
    per_file = [compute_file_sha256(p) for p in dataset_paths]
    combined = hashlib.sha256("|".join(sorted(f["sha256"] for f in per_file)).encode("utf-8")).hexdigest()
    return {"files": per_file, "combined_sha256": combined}


def get_git_sha(repo_root: Path = REPO_ROOT) -> str | None:
    """Real current git commit SHA of the working tree, via `git rev-parse HEAD` - returns None
    (never a fabricated placeholder) if this is not a git checkout or the command fails for any
    reason, so callers can record 'unknown' honestly rather than a fake hash."""
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell, no user input
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_git_dirty(repo_root: Path = REPO_ROOT) -> bool | None:
    """Whether the working tree has uncommitted changes at run time (`git status --short`), so a
    run's provenance honestly discloses if it was not run against a clean, committed snapshot.
    Returns None if git status cannot be determined."""
    try:
        result = subprocess.run(  # nosec B603 B607 -- fixed argv, no shell, no user input
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def capture_software_versions(packages: tuple[str, ...] = REPRODUCIBILITY_PACKAGES) -> dict[str, str]:
    """Real installed versions of `packages`, read via importlib.metadata.version() - a package
    not installed is recorded as 'not_installed' rather than omitted silently or guessed."""
    versions: dict[str, str] = {"python": platform.python_version()}
    for pkg in packages:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            versions[pkg] = "not_installed"
    return versions


def capture_run_provenance(dataset_paths: list[Path] | None = None) -> dict[str, Any]:
    """One real, structured provenance block for an MLflow run: git SHA, git dirty flag, software
    versions, and (if dataset_paths given) the real dataset fingerprint. This is the single call
    every BP's training script makes to populate the provenance tags Phase D's Model Registry
    requirement (immutable versions, provenance) and CI/CD integration both need."""
    provenance: dict[str, Any] = {
        "git_sha": get_git_sha() or "unknown",
        "git_dirty": get_git_dirty(),
        "software_versions": capture_software_versions(),
    }
    if dataset_paths:
        provenance["dataset_fingerprint"] = compute_dataset_fingerprint(dataset_paths)
    return provenance


def configure_mlflow(experiment_name: str, mlruns_dir: Path = DEFAULT_MLRUNS_DIR) -> str:
    """Point the `mlflow` SDK at this project's tracking URI and ensure `experiment_name` exists
    (creating it against the local sqlite artifact store if needed). Returns the experiment_id.
    Deferred import of mlflow (same convention as src/genai/bp6_grounded_generation.py's deferred
    google-genai import) so importing this module never requires mlflow to be installed unless a
    caller actually starts tracking."""
    import mlflow

    tracking_uri = get_tracking_uri(mlruns_dir)
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
    existing = client.get_experiment_by_name(experiment_name)
    if existing is not None:
        return existing.experiment_id
    artifact_location = (
        get_artifact_location(mlruns_dir) if not os.environ.get("MLFLOW_TRACKING_URI") else None
    )
    return client.create_experiment(experiment_name, artifact_location=artifact_location)
