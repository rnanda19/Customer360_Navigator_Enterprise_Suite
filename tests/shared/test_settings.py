"""
tests/shared/test_settings.py — Customer360 Navigator

Real, non-fabricated tests for src/utils/settings.py (hygiene pass, 2026-09-26). Covers: defaults
when no environment variables are set, real values being read and type-coerced correctly, the
fail-fast validator on a bad C360_PROJECT_ROOT override, and the force_reload cache-bypass contract
- matching this project's own test style (tests/shared/test_performance_setup.py,
tests/shared/test_taxonomy_mapper.py) rather than inventing a new one.
"""

from __future__ import annotations

import pytest

from utils.settings import C360Settings, get_settings


class TestC360SettingsDefaults:
    def test_defaults_with_no_env_vars_set(self, monkeypatch, tmp_path):
        monkeypatch.delenv("C360_PROJECT_ROOT", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        # Point pydantic-settings at an isolated cwd so it can't pick up a real .env file left by
        # a developer's own shell (this project's real .env, if any, is gitignored - see
        # .env.example's own header - so a test run must never depend on one existing on disk).
        monkeypatch.chdir(tmp_path)

        settings = C360Settings()

        assert settings.c360_project_root is None
        assert settings.gemini_api_key is None
        assert settings.gemini_model == "gemini-3.5-flash"


class TestC360SettingsRealValues:
    def test_reads_gemini_api_key_and_model_from_environment(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real-1234")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")
        monkeypatch.delenv("C360_PROJECT_ROOT", raising=False)

        settings = C360Settings()

        assert settings.gemini_api_key == "test-key-not-real-1234"
        assert settings.gemini_model == "gemini-2.0-flash"

    def test_reads_and_coerces_project_root_to_a_path(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        real_dir = tmp_path / "fake_project_root"
        real_dir.mkdir()
        monkeypatch.setenv("C360_PROJECT_ROOT", str(real_dir))

        settings = C360Settings()

        assert settings.c360_project_root == real_dir
        assert isinstance(settings.c360_project_root, type(real_dir))


class TestC360SettingsValidation:
    def test_project_root_override_pointing_at_nonexistent_directory_fails_fast(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("C360_PROJECT_ROOT", str(tmp_path / "does_not_exist_at_all"))

        with pytest.raises(ValueError, match="does not exist"):
            C360Settings()

    def test_unrelated_environment_variables_are_ignored(self, monkeypatch, tmp_path):
        # extra="ignore" must hold: a CI runner's own environment carries dozens of unrelated
        # variables (PATH, GITHUB_*, RUNNER_*, ...) that must never raise a validation error here.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SOME_UNRELATED_CI_VARIABLE", "anything")

        settings = C360Settings()

        assert not hasattr(settings, "some_unrelated_ci_variable")


class TestGetSettingsCache:
    def test_get_settings_caches_across_calls(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        first = get_settings(force_reload=True)
        second = get_settings()

        assert first is second

    def test_force_reload_picks_up_a_changed_environment_variable(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")
        first = get_settings(force_reload=True)
        assert first.gemini_model == "gemini-3.5-flash"

        monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")
        second = get_settings(force_reload=True)

        assert second.gemini_model == "gemini-2.0-flash"
        assert first is not second
