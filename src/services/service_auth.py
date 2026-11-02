"""
src/services/service_auth.py — Customer360 Navigator

Shared API-key authentication dependency for all 7 FastAPI services (BP1-BP7). Deliberately its
own module, NOT part of service_common.py: service_common.py transitively imports
models/model_persistence.py (joblib/numpy/pandas/scipy), which BP4/BP5/BP6/BP7's own Dockerfiles
never install (grep-verified against each service's own real imports - see each Dockerfile's
"MINIMAL REAL RUNTIME DEPENDENCY LIST" comment). Importing service_common from those 4 services
would silently break their containers at startup the first time this dependency is exercised, with
a ModuleNotFoundError for a package that Dockerfile never installs. This module imports only
stdlib (hmac) and fastapi, plus the sibling `secrets_provider` module (Phase J - itself stdlib +
fastapi only, see its own docstring) - all already installed/shipped in every one of the 7
services' Dockerfiles (every one already does `COPY src/ ./src/`) - it is safe for all 7 services
to import with zero new runtime dependencies.

Design, matching this project's zero-fabrication/no-silent-failure convention already established
in service_common.py's ModelBundleHandle (a missing model bundle is a documented 503, never a
fabricated prediction): a service with no C360_API_KEY set in its environment is a misconfigured
service, not an open one. It serves 503 on every protected endpoint, naming exactly what to set,
rather than silently accepting an unauthenticated request. A request presenting a missing or wrong
key gets 401. `/` and `/health` stay unauthenticated on every service (container orchestrators,
load balancers, and uptime monitors need to probe those with no secret).

One shared secret (C360_API_KEY) across all 7 services, not one per service - this project ships
one deployment unit (docker-compose.yml aggregates all 7 under one compose file), matching the
precedent BP6's own single shared GEMINI_API_KEY already set. See SECURITY.md and .env.example for
how to set it locally and in production.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from services.secrets_provider import (
    SecretNotFoundError,
    SecretsProviderUnavailableError,
    get_secrets_provider,
)

API_KEY_ENV_VAR = "C360_API_KEY"
API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def require_api_key(provided_key: Optional[str] = Security(_api_key_header)) -> None:
    """FastAPI dependency - attach with `dependencies=[Depends(require_api_key)]` on every route
    except `/` and `/health`. Raises before the route body ever runs, so an unauthenticated or
    misconfigured request never reaches model inference, a GenAI call, or a read of any real
    artifact.

    Phase J: the expected key is now resolved through `secrets_provider.get_secrets_provider()`
    rather than a direct `os.environ.get(...)` call. By default (`C360_SECRETS_PROVIDER` unset
    or "env") this is byte-for-byte the same behavior as before this change - the provider
    abstraction exists so a deployment can opt in to Vault (`C360_SECRETS_PROVIDER=vault`)
    without any code change here, never so that the default behavior shifts underneath existing
    deployments.

    Fails closed on every path: a service whose configured secrets backend cannot resolve
    `C360_API_KEY` at all (unset env var, or Vault unreachable / missing the key) refuses every
    protected request with 503 rather than silently serving them unauthenticated, and
    `hmac.compare_digest` is used instead of `==` so a wrong key is rejected in constant time
    rather than leaking the correct key's length/prefix through response-timing differences. The
    503 detail message never includes the secret's value - only which backend/name failed to
    resolve, which `secrets_provider`'s own exception messages already restrict themselves to.
    """
    try:
        expected_key = get_secrets_provider().get_secret(API_KEY_ENV_VAR)
    except SecretsProviderUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Service misconfigured: the configured secrets provider could not be reached "
                f"to resolve {API_KEY_ENV_VAR}. Refusing to serve an unauthenticated request "
                f"rather than silently allowing one. Detail: {exc}"
            ),
        ) from exc
    except SecretNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Service misconfigured: {API_KEY_ENV_VAR} is not set. Set it to a real secret "
                "before starting this service - see SECURITY.md and .env.example. Refusing to "
                "serve an unauthenticated request rather than silently allowing one."
            ),
        )
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=401,
            detail=f"Missing or invalid {API_KEY_HEADER_NAME} header.",
        )
    return None
