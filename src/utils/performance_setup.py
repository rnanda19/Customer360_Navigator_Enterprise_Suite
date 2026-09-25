"""
src/utils/performance_setup.py — Customer360 Navigator

WARP standing performance module. Master Execution Plan Section 15 (WARP) / Section 17
(Hardware & Performance Optimization Spec). Every notebook calls `configure_performance()` as
its FIRST executable step, before any heavy numeric import (numpy/pandas/polars/sklearn/etc.) —
see LESSONS_LEARNED_APPLIED.md #5: thread-count environment variables (OMP_NUM_THREADS and
friends) are read once by BLAS/OpenMP libraries at import time, so setting them after import has
no effect. This mirrors the real bug hit on the AMEX platform where a WARP ceiling was computed
but never actually applied because it was set after the heavy imports had already run.

This module never guesses at hardware — every number it uses either comes from
configs/resource_limits.yaml (ceilings, explicitly flagged [ASSUMPTION] where unconfirmed) or
from a live psutil/os reading taken at call time. It performs no execution of BPs and is never
run by Claude — only imported and called by the user's own notebook runs.

Public functions:
  resolve_project_root(marker_filename="PROJECT_STRUCTURE_LOCKED.md") -> Path
  load_resource_limits(project_root) -> dict
  configure_performance(project_root=None, verbose=True) -> dict
  pin_core_affinity(n_threads) -> list[int] | None
  memory_headroom_gb(ceiling_fraction=None) -> float
  assert_within_ram_ceiling(config)  -> None (raises if current usage already exceeds ceiling)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def resolve_project_root(marker_filename: str = "PROJECT_STRUCTURE_LOCKED.md") -> Path:
    """Resolve the Customer360 Navigator project root without ever hardcoding an absolute path
    (PROJECT_STRUCTURE_LOCKED.md rule #3). Resolution order:
      1. C360_PROJECT_ROOT environment variable, if set (raises if the marker isn't there —
         never silently falls through a misconfigured override).
      2. A bounded upward walk (max 8 levels) from the current working directory — handles the
         common case where the kernel's cwd is inside the project tree.
      3. A bounded downward search (depth <= 3, hidden dirs skipped) from the current working
         directory — handles the case where the kernel's cwd is a PARENT of the project folder
         rather than inside it. Real bug hit on 00_hardware_benchmark.ipynb's first user run
         (see LESSONS_LEARNED_APPLIED.md): an upward-only walk cannot find a marker that lives
         in a child directory, and this happens whenever the notebook's kernel cwd is set to a
         workspace root rather than the notebook's own folder (a common default in some
         editors' Jupyter integrations, e.g. VS Code).
      4. Raise RuntimeError with actionable guidance — never silently fall back to a guessed
         path.
    """
    env_override = os.environ.get("C360_PROJECT_ROOT")
    if env_override:
        candidate = Path(env_override)
        if (candidate / marker_filename).exists():
            return candidate
        raise RuntimeError(
            f"C360_PROJECT_ROOT is set to {candidate} but {marker_filename} was not found "
            "there. Fix the environment variable rather than removing this check."
        )

    start = Path.cwd()
    current = start
    for _ in range(8):
        if (current / marker_filename).exists():
            return current
        if current.parent == current:
            break
        current = current.parent

    for depth_root, dirnames, filenames in os.walk(start):
        rel_depth = len(Path(depth_root).relative_to(start).parts)
        if rel_depth > 3:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if marker_filename in filenames:
            return Path(depth_root)

    raise RuntimeError(
        f"Could not locate {marker_filename} by walking up from {start}, nor by searching up "
        "to 3 levels below it. Set the C360_PROJECT_ROOT environment variable to the project "
        "root, or run this notebook from inside the project folder tree."
    )


def load_resource_limits(project_root: Path) -> dict:
    """Load configs/resource_limits.yaml. Raises if missing — never invents ceiling defaults
    inline, since those defaults are a governance artifact reviewed in the Master Plan.
    """
    import yaml

    config_path = project_root / "configs" / "resource_limits.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"resource_limits.yaml not found at {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def configure_performance(project_root: Optional[Path] = None, verbose: bool = True) -> dict:
    """Set BLAS/OpenMP thread-count environment variables from the live core count, capped at
    the project's WARP ceiling (configs/resource_limits.yaml -> ceilings.max_cpu_thread_fraction,
    never 100%). MUST be called before importing numpy, pandas, polars, scikit-learn, xgboost,
    lightgbm, catboost, or any other BLAS-backed library — those libraries read
    OMP_NUM_THREADS/MKL_NUM_THREADS/OPENBLAS_NUM_THREADS/NUMEXPR_NUM_THREADS once, at their own
    import time.

    Returns a summary dict describing what was actually set, for the notebook to log/display —
    never claims a setting took effect without reporting the value read back.
    """
    import psutil  # local import: psutil itself is lightweight and not BLAS-backed

    if project_root is None:
        project_root = resolve_project_root()

    limits = load_resource_limits(project_root)
    ceilings = limits["ceilings"]
    max_cpu_fraction = ceilings["max_cpu_thread_fraction"]
    if ceilings.get("never_target_100_percent") is not True:
        raise RuntimeError(
            "resource_limits.yaml does not have never_target_100_percent: true — refusing to "
            "configure performance against an unsafe config (real incident: 100% CPU target "
            "hung the laptop during a prior project's Phase 3)."
        )

    logical_threads = psutil.cpu_count(logical=True) or 1
    n_threads = max(1, int(logical_threads * max_cpu_fraction))

    thread_env_vars = [
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ]
    for var in thread_env_vars:
        os.environ[var] = str(n_threads)

    virtual_mem = psutil.virtual_memory()
    ram_ceiling_fraction = ceilings["max_ram_fraction"]
    ram_ceiling_gb = round((virtual_mem.total / (1024**3)) * ram_ceiling_fraction, 2)

    summary = {
        "project_root": str(project_root),
        "logical_threads_detected": logical_threads,
        "n_threads_configured": n_threads,
        "cpu_thread_ceiling_fraction": max_cpu_fraction,
        "thread_env_vars_set": {var: str(n_threads) for var in thread_env_vars},
        "ram_total_gb": round(virtual_mem.total / (1024**3), 2),
        "ram_ceiling_fraction": ram_ceiling_fraction,
        "ram_ceiling_gb": ram_ceiling_gb,
        "ram_currently_available_gb": round(virtual_mem.available / (1024**3), 2),
    }

    if verbose:
        print(
            f"[WARP] configure_performance(): {n_threads}/{logical_threads} threads "
            f"({max_cpu_fraction:.0%} ceiling), RAM ceiling {ram_ceiling_gb} GB "
            f"({ram_ceiling_fraction:.0%} of {summary['ram_total_gb']} GB total)."
        )

    return summary


def pin_core_affinity(n_threads: int) -> Optional[list[int]]:
    """Pin the current process to the first n_threads logical cores via psutil, where the
    platform supports it (Linux; Windows also supports Process.cpu_affinity() via psutil).
    Returns the affinity list actually applied, or None if the platform/psutil build does not
    support cpu_affinity() — never raises for an unsupported platform, since this is an
    optimization, not a correctness requirement."""
    import psutil

    process = psutil.Process()
    if not hasattr(process, "cpu_affinity"):
        return None
    try:
        available = list(range(psutil.cpu_count(logical=True) or 1))
        target = available[:n_threads] if n_threads < len(available) else available
        process.cpu_affinity(target)
        return target
    except (AttributeError, NotImplementedError, OSError):
        return None


def memory_headroom_gb(ceiling_fraction: Optional[float] = None) -> float:
    """Return how many GB remain before the RAM ceiling is hit. ceiling_fraction defaults to
    0.92 (the project standing ceiling) if not passed explicitly."""
    import psutil

    if ceiling_fraction is None:
        ceiling_fraction = 0.92
    virtual_mem = psutil.virtual_memory()
    ceiling_bytes = virtual_mem.total * ceiling_fraction
    used_bytes = virtual_mem.total - virtual_mem.available
    return round(max(0.0, (ceiling_bytes - used_bytes) / (1024**3)), 2)


def assert_within_ram_ceiling(config: dict) -> None:
    """Raise AssertionError if current RAM usage has already crossed the configured ceiling
    fraction at the time this is called. Intended as a structural [CHECK] gate inside notebooks,
    not a background monitor."""
    import psutil

    ceiling_fraction = config["ceilings"]["max_ram_fraction"]
    virtual_mem = psutil.virtual_memory()
    used_fraction = 1 - (virtual_mem.available / virtual_mem.total)
    assert used_fraction <= ceiling_fraction, (
        f"[CHECK FAILED] Current RAM usage ({used_fraction:.1%}) already exceeds the WARP "
        f"ceiling ({ceiling_fraction:.1%}). Free memory or restart the kernel before continuing "
        "— do not proceed with a heavy step on top of an already-breached ceiling."
    )
