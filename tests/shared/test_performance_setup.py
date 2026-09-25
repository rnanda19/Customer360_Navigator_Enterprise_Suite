"""
tests/shared/test_performance_setup.py — Customer360 Navigator

Full pytest coverage for src/utils/performance_setup.py (BP1 Gate 6 governance requirement -
"Full test coverage is the standing standard for this suite - smoke-testing-only is never
substituted", Master Execution Plan Section 16.1). Every public function is covered, including
its documented failure modes (missing config, unsafe config, ceiling already breached) - not
just the happy path.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils import performance_setup as ps


# ---------------------------------------------------------------------------
# resolve_project_root
# ---------------------------------------------------------------------------

def test_resolve_project_root_env_override_valid(tmp_path, monkeypatch):
    marker = tmp_path / "PROJECT_STRUCTURE_LOCKED.md"
    marker.write_text("locked")
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    result = ps.resolve_project_root()
    assert result == tmp_path


def test_resolve_project_root_env_override_invalid_raises(tmp_path, monkeypatch):
    # tmp_path has no marker file - the override must be honored (never silently fall through).
    monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="C360_PROJECT_ROOT"):
        ps.resolve_project_root()


def test_resolve_project_root_upward_walk(tmp_path, monkeypatch):
    monkeypatch.delenv("C360_PROJECT_ROOT", raising=False)
    marker = tmp_path / "PROJECT_STRUCTURE_LOCKED.md"
    marker.write_text("locked")
    nested = tmp_path / "notebooks" / "bp1_customer_intent_classification"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    result = ps.resolve_project_root()
    assert result == tmp_path


def test_resolve_project_root_downward_search(tmp_path, monkeypatch):
    # Real bug this guards against (LESSONS_LEARNED_APPLIED.md): kernel cwd is a PARENT of the
    # project folder, not inside it.
    monkeypatch.delenv("C360_PROJECT_ROOT", raising=False)
    project_dir = tmp_path / "Customer360_Navigator_Enterprise_Suite"
    project_dir.mkdir()
    (project_dir / "PROJECT_STRUCTURE_LOCKED.md").write_text("locked")
    monkeypatch.chdir(tmp_path)
    result = ps.resolve_project_root()
    assert result == project_dir


def test_resolve_project_root_raises_when_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("C360_PROJECT_ROOT", raising=False)
    empty_dir = tmp_path / "nowhere"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    with pytest.raises(RuntimeError, match="Could not locate"):
        ps.resolve_project_root()


# ---------------------------------------------------------------------------
# load_resource_limits
# ---------------------------------------------------------------------------

def test_load_resource_limits_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ps.load_resource_limits(tmp_path)


def test_load_resource_limits_loads_valid_yaml(tmp_path):
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    (configs_dir / "resource_limits.yaml").write_text(
        "ceilings:\n  max_ram_fraction: 0.92\n  max_cpu_thread_fraction: 0.95\n"
        "  never_target_100_percent: true\ncv:\n  n_splits: 5\n"
    )
    limits = ps.load_resource_limits(tmp_path)
    assert limits["ceilings"]["max_ram_fraction"] == 0.92
    assert limits["cv"]["n_splits"] == 5


# ---------------------------------------------------------------------------
# configure_performance
# ---------------------------------------------------------------------------

def _make_project_root(tmp_path, never_target_100=True, cpu_fraction=0.95, ram_fraction=0.92):
    configs_dir = tmp_path / "configs"
    configs_dir.mkdir()
    flag_line = "true" if never_target_100 else "false"
    (configs_dir / "resource_limits.yaml").write_text(
        f"ceilings:\n  max_ram_fraction: {ram_fraction}\n  max_cpu_thread_fraction: {cpu_fraction}\n"
        f"  never_target_100_percent: {flag_line}\n"
    )
    return tmp_path


def test_configure_performance_sets_env_vars_and_returns_summary(tmp_path, monkeypatch):
    project_root = _make_project_root(tmp_path, cpu_fraction=0.5)

    fake_vmem = SimpleNamespace(total=16 * (1024 ** 3), available=8 * (1024 ** 3))
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 8)
    monkeypatch.setattr("psutil.virtual_memory", lambda: fake_vmem)

    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        monkeypatch.delenv(var, raising=False)

    summary = ps.configure_performance(project_root=project_root, verbose=False)

    # 8 logical threads * 0.5 ceiling = 4
    assert summary["n_threads_configured"] == 4
    assert summary["logical_threads_detected"] == 8
    assert os.environ["OMP_NUM_THREADS"] == "4"
    assert os.environ["MKL_NUM_THREADS"] == "4"
    assert os.environ["OPENBLAS_NUM_THREADS"] == "4"
    assert os.environ["NUMEXPR_NUM_THREADS"] == "4"
    assert os.environ["VECLIB_MAXIMUM_THREADS"] == "4"
    assert summary["ram_total_gb"] == 16.0
    assert summary["ram_ceiling_gb"] == round(16.0 * 0.92, 2)


def test_configure_performance_min_one_thread_never_zero(tmp_path, monkeypatch):
    # A tiny ceiling fraction must never round down to 0 threads (max(1, ...) guard).
    project_root = _make_project_root(tmp_path, cpu_fraction=0.01)
    fake_vmem = SimpleNamespace(total=8 * (1024 ** 3), available=4 * (1024 ** 3))
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 2)
    monkeypatch.setattr("psutil.virtual_memory", lambda: fake_vmem)
    summary = ps.configure_performance(project_root=project_root, verbose=False)
    assert summary["n_threads_configured"] >= 1


def test_configure_performance_raises_without_safety_flag(tmp_path, monkeypatch):
    # Real incident this guards: a config missing/false on never_target_100_percent must be
    # refused outright, never silently defaulted to a "safe-ish" value.
    project_root = _make_project_root(tmp_path, never_target_100=False)
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 8)
    monkeypatch.setattr("psutil.virtual_memory", lambda: SimpleNamespace(total=16 * (1024 ** 3), available=8 * (1024 ** 3)))
    with pytest.raises(RuntimeError, match="never_target_100_percent"):
        ps.configure_performance(project_root=project_root, verbose=False)


# ---------------------------------------------------------------------------
# pin_core_affinity
# ---------------------------------------------------------------------------

def test_pin_core_affinity_applies_and_returns_target(monkeypatch):
    calls = {}

    class FakeProcess:
        def cpu_affinity(self, target=None):
            if target is None:
                return calls.get("target")
            calls["target"] = target

    monkeypatch.setattr("psutil.Process", lambda: FakeProcess())
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 8)
    result = ps.pin_core_affinity(4)
    assert result == [0, 1, 2, 3]
    assert calls["target"] == [0, 1, 2, 3]


def test_pin_core_affinity_returns_none_when_unsupported(monkeypatch):
    class FakeProcessNoAffinity:
        pass  # deliberately has no cpu_affinity attribute

    monkeypatch.setattr("psutil.Process", lambda: FakeProcessNoAffinity())
    assert ps.pin_core_affinity(4) is None


def test_pin_core_affinity_returns_none_on_oserror(monkeypatch):
    class FakeProcessRaises:
        def cpu_affinity(self, target=None):
            raise OSError("not permitted")

    monkeypatch.setattr("psutil.Process", lambda: FakeProcessRaises())
    monkeypatch.setattr("psutil.cpu_count", lambda logical=True: 8)
    assert ps.pin_core_affinity(4) is None


# ---------------------------------------------------------------------------
# memory_headroom_gb
# ---------------------------------------------------------------------------

def test_memory_headroom_gb_default_ceiling(monkeypatch):
    fake_vmem = SimpleNamespace(total=16 * (1024 ** 3), available=4 * (1024 ** 3))
    monkeypatch.setattr("psutil.virtual_memory", lambda: fake_vmem)
    headroom = ps.memory_headroom_gb()
    # ceiling = 16*0.92 = 14.72 GB; used = 12 GB; headroom = 2.72 GB
    assert headroom == pytest.approx(2.72, abs=0.01)


def test_memory_headroom_gb_custom_ceiling(monkeypatch):
    fake_vmem = SimpleNamespace(total=10 * (1024 ** 3), available=1 * (1024 ** 3))
    monkeypatch.setattr("psutil.virtual_memory", lambda: fake_vmem)
    headroom = ps.memory_headroom_gb(ceiling_fraction=0.5)
    # ceiling = 5 GB; used = 9 GB -> already over ceiling -> clamped to 0.0, never negative
    assert headroom == 0.0


# ---------------------------------------------------------------------------
# assert_within_ram_ceiling
# ---------------------------------------------------------------------------

def test_assert_within_ram_ceiling_passes_when_below(monkeypatch):
    fake_vmem = SimpleNamespace(total=16 * (1024 ** 3), available=8 * (1024 ** 3))  # 50% used
    monkeypatch.setattr("psutil.virtual_memory", lambda: fake_vmem)
    ps.assert_within_ram_ceiling({"ceilings": {"max_ram_fraction": 0.92}})  # must not raise


def test_assert_within_ram_ceiling_raises_when_above(monkeypatch):
    fake_vmem = SimpleNamespace(total=16 * (1024 ** 3), available=1 * (1024 ** 3))  # ~93.75% used
    monkeypatch.setattr("psutil.virtual_memory", lambda: fake_vmem)
    with pytest.raises(AssertionError, match="CHECK FAILED"):
        ps.assert_within_ram_ceiling({"ceilings": {"max_ram_fraction": 0.92}})
