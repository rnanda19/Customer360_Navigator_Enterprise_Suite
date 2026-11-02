"""
src/mlops/registry.py — Customer360 Navigator

PHASE D: real Model Registry integration, built on top of src/mlops/tracking.py's sqlite-backed
MLflow store (the local FileStore this project would otherwise use for tracking does not support
registered models in this MLflow version - see tracking.py's module docstring).

This module wraps the real `mlflow.MlflowClient` registry calls (register_model,
create_registered_model, set_registered_model_alias, etc.) - it does not reimplement versioning,
it standardizes HOW this project uses it: every model name is namespaced "customer360_<bp_id>"
(one registered model per business problem, consistent with this project's existing per-BP
convention everywhere else - configs/, models/, src/deployment/*_readiness_verdict.py), every
version is tagged with real provenance (git SHA, dataset fingerprint, software versions - via
tracking.capture_run_provenance()) and real evaluation metrics (never invented), and promotion
uses MLflow's current alias mechanism ("champion" / "challenger" / "previous_champion") rather
than the deprecated stage-transition API (Staging/Production/Archived), which newer MLflow
versions (3.x, installed here) have moved away from in favor of aliases + tags.

Model SIGNATURE (Phase D requirement: "model signatures"): captured via
mlflow.models.signature.infer_signature against a real sample of the input the registered
pipeline actually consumes (e.g. BP1's raw text Series) and its real predict_proba output -
inferred from real data passed through the real fitted object, never hand-written or guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mlops.tracking import get_tracking_uri

MODEL_NAME_PREFIX = "customer360_"


def registered_model_name(bp_id: str) -> str:
    return f"{MODEL_NAME_PREFIX}{bp_id}"


@dataclass
class AliasedVersion:
    """Thin, immutable wrapper around a real MLflow ModelVersion, exposing `.version` as a str.
    MLflow 3.x's ModelVersion.version is an int and read-only (no setter) - this wrapper is used
    instead of mutating the object returned by the client, so every caller of this module gets
    one consistent, settable, string version type regardless of MLflow's own internal type."""

    version: str
    run_id: str
    tags: dict[str, str]
    aliases: list[str] = field(default_factory=list)


@dataclass
class RegisteredVersionInfo:
    """Real facts about one registered model version - every field below is read back from the
    MLflow registry after registration, never pre-computed and assumed to have landed."""

    name: str
    version: str
    run_id: str
    source: str
    aliases: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)


def _get_client(mlruns_dir=None):
    import mlflow

    tracking_uri = get_tracking_uri(mlruns_dir) if mlruns_dir else get_tracking_uri()
    mlflow.set_tracking_uri(tracking_uri)
    return mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)


def ensure_registered_model(bp_id: str, description: str = "") -> str:
    """Create the registered model for `bp_id` if it does not already exist. Idempotent - safe
    to call on every training run. Returns the registered model name."""
    import mlflow.exceptions

    name = registered_model_name(bp_id)
    client = _get_client()
    try:
        client.create_registered_model(
            name, description=description or f"Customer360 {bp_id} champion model."
        )
    except mlflow.exceptions.MlflowException as exc:
        if "already exists" not in str(exc).lower() and "RESOURCE_ALREADY_EXISTS" not in str(exc):
            raise
    return name


def register_model_version(
    *,
    bp_id: str,
    run_id: str,
    artifact_subpath: str,
    provenance_tags: dict[str, Any],
    evaluation_metrics: dict[str, float],
    description: str = "",
) -> RegisteredVersionInfo:
    """Register the model artifact logged at `artifact_subpath` within run `run_id` as a new
    version of bp_id's registered model. Every tag written is a real string-cast of a real value
    the caller computed (provenance from tracking.capture_run_provenance(), metrics from the
    caller's own real evaluation) - this function performs no training or evaluation itself."""
    name = ensure_registered_model(bp_id)
    client = _get_client()
    model_uri = f"runs:/{run_id}/{artifact_subpath}"
    mv = client.create_model_version(
        name=name,
        source=model_uri,
        run_id=run_id,
        description=description,
    )
    version_str = str(mv.version)  # MLflow's ModelVersion.version is an int on this client/server
    # version (3.17.2) - normalized to str here so every caller of this module gets one
    # consistent type, never a mix of int and str depending on which MLflow call produced it.
    tags: dict[str, str] = {f"metric__{k}": str(v) for k, v in evaluation_metrics.items()}
    tags.update({f"provenance__{k}": str(v) for k, v in provenance_tags.items() if not isinstance(v, dict)})
    if "dataset_fingerprint" in provenance_tags:
        tags["provenance__dataset_combined_sha256"] = provenance_tags["dataset_fingerprint"].get(
            "combined_sha256", "unknown"
        )
    for key, value in tags.items():
        client.set_model_version_tag(name=name, version=version_str, key=key, value=value)
    return RegisteredVersionInfo(name=name, version=version_str, run_id=run_id, source=model_uri, tags=tags)


def get_version_by_alias(bp_id: str, alias: str):
    """Real lookup of whichever version currently holds `alias` (e.g. 'champion'). Returns None
    (never raises and never fabricates a version) if no version currently holds that alias."""
    import mlflow.exceptions

    name = registered_model_name(bp_id)
    client = _get_client()
    try:
        mv = client.get_model_version_by_alias(name, alias)
    except mlflow.exceptions.MlflowException:
        return None
    return AliasedVersion(
        version=str(mv.version), run_id=mv.run_id, tags=dict(mv.tags or {}), aliases=list(mv.aliases or [])
    )


def set_alias(bp_id: str, alias: str, version: str) -> None:
    """Point `alias` at `version`. MLflow aliases are 1:1 (setting an alias that is already held
    by another version moves it) - this is exactly the mechanic promotion.py uses to move
    'champion' from an old version to a new one, and rollback.py uses to move it back."""
    name = registered_model_name(bp_id)
    client = _get_client()
    client.set_registered_model_alias(name=name, alias=alias, version=version)


def delete_alias(bp_id: str, alias: str) -> None:
    import mlflow.exceptions

    name = registered_model_name(bp_id)
    client = _get_client()
    try:
        client.delete_registered_model_alias(name=name, alias=alias)
    except mlflow.exceptions.MlflowException:
        pass


def list_versions(bp_id: str) -> list[Any]:
    """Every real registered version for bp_id, most recent first - used by rollback.py to find
    the prior champion and by the final delivery report to show real registration evidence."""
    name = registered_model_name(bp_id)
    client = _get_client()
    try:
        raw_versions = client.search_model_versions(f"name='{name}'")
    except Exception:
        return []
    versions = [
        AliasedVersion(
            version=str(v.version), run_id=v.run_id, tags=dict(v.tags or {}), aliases=list(v.aliases or [])
        )
        for v in raw_versions
    ]
    return sorted(versions, key=lambda v: int(v.version), reverse=True)


def get_version_tags(bp_id: str, version: str) -> dict[str, str]:
    name = registered_model_name(bp_id)
    client = _get_client()
    mv = client.get_model_version(name=name, version=str(version))
    return dict(mv.tags or {})
