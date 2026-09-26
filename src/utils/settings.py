"""
src/utils/settings.py — Customer360 Navigator

Typed, validated configuration layer (hygiene pass, 2026-09-26). Additive only: this module wraps
the project's real environment variables in a `pydantic_settings.BaseSettings` model so callers get
type coercion, validation, and a documented default in one place, with a fail-fast, readable error
if something is misconfigured. It does NOT replace any existing `os.environ.get(...)` call site
(e.g. `service_common.py`'s own `resolve_project_root()`, or `bp6_grounded_generation.py`'s direct
reads of GEMINI_API_KEY/GEMINI_MODEL) - those already-tested code paths are left exactly as they
are. New code, or a future refactor of an existing call site, can opt into `get_settings()` instead.

The three fields below are the complete, real set of environment variables this project actually
reads (grep-verified against src/**/*.py, 2026-09-26) - nothing here is aspirational or invented:

  - C360_PROJECT_ROOT   read by every module's own `resolve_project_root()` (notebooks, services,
                        deployment/readiness-verdict scripts) as an override for the default
                        upward-walk project-root resolution. Optional - most real runs never set it.
  - GEMINI_API_KEY       read by src/genai/bp6_grounded_generation.py - the one gate in the whole
                        project (BP6 Gate 5) that makes a real external API call. Required only to
                        run that gate for real; every other gate/BP never touches it.
  - GEMINI_MODEL         read by the same module, with a real default ("gemini-3.5-flash", the
                        no-cost free-tier model this project standardized on - see requirements.txt's
                        own google-genai comment for why). Optional.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class C360Settings(BaseSettings):
    """Typed view of this project's real environment variables. Instantiating this class reads
    `os.environ` (and a `.env` file if present, matching `.env.example`'s documented keys) exactly
    once; pydantic-settings itself reads the environment, so no `os.environ.get(...)` calls appear
    in this module. Values are validated at construction time, never at first use - a missing
    `C360_PROJECT_ROOT` value (when explicitly set) that doesn't point at a real directory fails
    immediately with a clear pydantic ValidationError, not a confusing downstream FileNotFoundError."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # unrelated env vars in the process environment must never break this
    )

    c360_project_root: Optional[Path] = None
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.5-flash"

    @field_validator("c360_project_root")
    @classmethod
    def _project_root_must_exist_if_set(cls, v: Optional[Path]) -> Optional[Path]:
        # Mirrors resolve_project_root()'s own contract (service_common.py): an override that is
        # SET but wrong must fail loudly, never silently fall through to the upward-walk fallback.
        # Left as a directory-existence check only, not a marker-file check, so this validator can
        # be used standalone in tests without a real PROJECT_STRUCTURE_LOCKED.md fixture on disk.
        if v is not None and not v.is_dir():
            raise ValueError(f"C360_PROJECT_ROOT is set to {v!r} but that directory does not exist.")
        return v


_cached_settings: Optional[C360Settings] = None


def get_settings(*, force_reload: bool = False) -> C360Settings:
    """Process-wide cached accessor, mirroring FastAPI's own `lru_cache`-on-settings convention.
    `force_reload=True` bypasses the cache - used by tests that monkeypatch environment variables
    between cases, since a plain module-level singleton would otherwise leak state across tests."""
    global _cached_settings
    if force_reload or _cached_settings is None:
        _cached_settings = C360Settings()
    return _cached_settings
