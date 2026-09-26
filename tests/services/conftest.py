"""
tests/services/conftest.py — Customer360 Navigator

Shared pytest fixtures for tests/services/. Auto-sets C360_API_KEY in the environment for every
test collected under this directory so each service's real `require_api_key` dependency
(src/services/service_auth.py) resolves without every existing fixture needing to thread
`monkeypatch` into every TestClient-constructing function just to set this one env var. Each
test's TestClient is still constructed with the matching X-API-Key header explicitly (see
TEST_API_KEY in each test file) - this fixture only supplies the server side of that pair, so a
test exercising a missing/wrong key (401) or a missing-env-var (503) case can still do so by
overriding the header or the env var locally within that one test.
"""

from __future__ import annotations

import pytest

TEST_API_KEY = "test-api-key-for-ci"


@pytest.fixture(autouse=True)
def _c360_api_key_env(monkeypatch):
    monkeypatch.setenv("C360_API_KEY", TEST_API_KEY)
