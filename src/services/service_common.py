"""
src/services/service_common.py — Customer360 Navigator

Shared helpers for the BP1/BP2 FastAPI inference services (Hardening Step 3). Mirrors the AMEX
RiskIQ platform's own established pattern of factoring shared service-layer code into one module
that each per-problem service file imports from (see the AMEX Phase 2 hardening pass), applied
here for BP1/BP2 rather than reimplemented per service - HYPER.

Applies a real lesson learned on that same AMEX pass (documented there): a service's model-
directory default must NEVER hardcode a real local machine path (that AMEX service shipped a
literal Windows path as its default, a privacy leak once the repo went public on GitHub). This
module resolves the project root the exact same way every notebook in this project already does -
an environment-variable override first, then a bounded upward walk from the running process's own
location - so no service file here, or any future one, can repeat that mistake.

Also applies the standing zero-fabrication rule to the service layer itself: if a champion model
bundle is not present on disk (the user has not yet run that BP's model-persistence notebook for
real), the service must never fall back to a mock/stub prediction. It starts in a documented
"model not loaded" state, serves 503 on prediction endpoints, and says exactly what to run to fix
it - never silently returns a fabricated result.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, Field

from models.model_persistence import load_model_bundle


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Identical resolution order to every notebook in this project (PROJECT_STRUCTURE_LOCKED.md
    rule #3): C360_PROJECT_ROOT env var override first (raises if the marker isn't there - never
    silently falls through a misconfigured override), then a bounded upward walk (max 8 levels)
    from this process's own working directory. No downward search here (unlike the notebooks'
    resolver) - a running service process's cwd is operator-controlled at launch time (systemd
    unit, Docker WORKDIR, uvicorn invocation directory), not a Jupyter kernel's occasionally-
    surprising cwd, so the extra downward-search fallback the notebooks need does not apply.
    """
    env_override = os.environ.get("C360_PROJECT_ROOT")
    if env_override:
        candidate = Path(env_override)
        if (candidate / marker_filename).exists():
            return candidate
        raise RuntimeError(
            f"C360_PROJECT_ROOT is set to {candidate} but {marker_filename} was not found there. "
            "Fix the environment variable rather than removing this check."
        )
    start = Path.cwd()
    current = start
    for _ in range(8):
        if (current / marker_filename).exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise RuntimeError(
        f"Could not resolve PROJECT_ROOT: no {marker_filename} found by walking up from {start}. "
        "Set the C360_PROJECT_ROOT environment variable to the "
        "Customer360_Navigator_Enterprise_Suite folder before starting this service."
    )


class ModelBundleHandle:
    """Loads (or fails to load) one BP's persisted model bundle at service startup, and holds the
    result for the lifetime of the process. Never raises past __init__ - a missing or corrupt
    bundle is recorded as `self.error`, not thrown, so the FastAPI app can still start and serve
    an honest /health response and a clear 503 on /predict, rather than crashing at import time
    with no way to even ask the service what is wrong."""

    def __init__(self, bp_id: str, joblib_path: Path, metadata_path: Optional[Path] = None):
        self.bp_id = bp_id
        self.joblib_path = joblib_path
        self.metadata_path = metadata_path
        self.bundle: Optional[dict[str, Any]] = None
        self.metadata: Optional[dict[str, Any]] = None
        self.error: Optional[str] = None
        self._load()

    def _load(self) -> None:
        try:
            self.bundle = load_model_bundle(self.joblib_path)
        except FileNotFoundError as e:
            self.error = (
                f"Model bundle not found at {self.joblib_path}. Run the "
                f"{self.bp_id}_..._model_persistence.ipynb notebook for real first. ({e})"
            )
            return
        except ValueError as e:
            self.error = f"Model bundle at {self.joblib_path} failed validation: {e}"
            return

        if self.metadata_path is not None and self.metadata_path.exists():
            import json

            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except (OSError, ValueError):
                # Metadata sidecar is documentation, not required for inference - a missing or
                # unreadable sidecar must never block a bundle that loaded successfully.
                self.metadata = None

    @property
    def is_loaded(self) -> bool:
        return self.bundle is not None


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' if the model bundle loaded successfully, else 'model_not_loaded'.")
    bp_id: str
    champion_model: Optional[str] = None
    joblib_path: Optional[str] = None
    joblib_sha256: Optional[str] = None
    fresh_refit_test_accuracy: Optional[float] = None
    gate5_recorded_test_accuracy: Optional[float] = None
    # BP3 addition (Hardening Step 3): BP3's real fidelity metric is PR-AUC/recall, never accuracy
    # (see src/models/model_persistence.py's module docstring) - these stay None for BP1/BP2's
    # metadata sidecars (which never set these keys) and are populated only for BP3, never both
    # sets at once for a given bp_id. Purely additive to this shared response model - BP1's and
    # BP2's already real-run-confirmed services are unaffected.
    fresh_refit_test_pr_auc: Optional[float] = None
    fresh_refit_test_recall: Optional[float] = None
    gate5_recomputed_test_pr_auc: Optional[float] = None
    generated_at_utc: Optional[str] = None
    error: Optional[str] = None


def top3_from_proba(
    proba_row: np.ndarray, class_names: list[str]
) -> tuple[str, float, str, float, str, float]:
    """Rank-1/2/3 label + confidence from one row of predict_proba output, shared by both BP1 and
    BP2's services (identical logic, previously duplicated - HYPER). Pads by repeating the last
    real rank if there are fewer than 3 classes (never indexes past the end); real for BP1 (77
    classes) and BP2 (4 classes) alike, so this never actually triggers today but is kept honest
    for any future reuse with fewer classes."""
    order = np.argsort(proba_row)[::-1]
    top3_idx = order[: min(3, len(class_names))]
    while len(top3_idx) < 3:
        top3_idx = np.append(top3_idx, top3_idx[-1])
    i1, i2, i3 = top3_idx[0], top3_idx[1], top3_idx[2]
    return (
        class_names[i1],
        float(proba_row[i1]),
        class_names[i2],
        float(proba_row[i2]),
        class_names[i3],
        float(proba_row[i3]),
    )


def build_health_response(handle: ModelBundleHandle) -> HealthResponse:
    if not handle.is_loaded:
        return HealthResponse(status="model_not_loaded", bp_id=handle.bp_id, error=handle.error)
    meta = handle.metadata or {}
    return HealthResponse(
        status="ok",
        bp_id=handle.bp_id,
        champion_model=handle.bundle.get("champion_name"),
        joblib_path=meta.get("joblib_relative_path", str(handle.joblib_path)),
        joblib_sha256=meta.get("joblib_sha256"),
        fresh_refit_test_accuracy=meta.get("fresh_refit_test_accuracy"),
        gate5_recorded_test_accuracy=meta.get("gate5_recorded_test_accuracy"),
        fresh_refit_test_pr_auc=meta.get("fresh_refit_test_pr_auc"),
        fresh_refit_test_recall=meta.get("fresh_refit_test_recall"),
        gate5_recomputed_test_pr_auc=meta.get("gate5_recomputed_test_pr_auc"),
        generated_at_utc=meta.get("generated_at_utc"),
    )
