"""Sign-in check: verify the bearer token from the identity provider (spec 008).

Everything specific to the identity provider is configuration (OIDC_ISSUER, OIDC_AUDIENCE,
OIDC_JWKS_URL). Only public-key algorithms are accepted, and the key always comes from the
provider's key set, never from the token.
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError, PyJWTError

logger = logging.getLogger("app.auth")

SETTING_NAMES = ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL")
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
LEEWAY_SECONDS = 60  # FR-004: tolerance for small clock differences


@dataclass(frozen=True)
class Settings:
    issuer: str
    audience: str
    jwks_url: str


def load_settings() -> Settings:
    """Read the three settings. Raises RuntimeError naming every missing or blank one (FR-021)."""
    values = {name: (os.getenv(name) or "").strip() for name in SETTING_NAMES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("Missing required setting(s): " + ", ".join(missing))
    return Settings(values["OIDC_ISSUER"], values["OIDC_AUDIENCE"], values["OIDC_JWKS_URL"])


class CachedKeyClient(PyJWKClient):
    """PyJWKClient that keeps using the last key set it fetched while the key address is down.

    The library's cache returns nothing once it expires, and a failed refetch would then fail
    every request even though the old keys are still valid (research R2).
    """

    def __init__(self, uri: str, **kwargs: Any):
        kwargs.setdefault("lifespan", 300)
        kwargs.setdefault("timeout", 5)
        super().__init__(uri, **kwargs)
        self._last_good: Any = None

    def _fetch_remote(self) -> Any:
        return super().fetch_data()  # the HTTP call; tests replace this

    def fetch_data(self) -> Any:
        try:
            data = self._fetch_remote()
        except PyJWKClientConnectionError as e:
            if self._last_good is None:
                raise
            logger.warning("Key address unreachable (%s); using the last key set fetched", e)
            return self._last_good
        self._last_good = data
        return data


@dataclass
class Verifier:
    settings: Settings
    keys: PyJWKClient


@lru_cache
def get_verifier() -> Verifier:
    """Settings plus the key client. Creating it makes no network call. Tests override this."""
    settings = load_settings()
    return Verifier(settings, CachedKeyClient(settings.jwks_url))


def _unauthorized(reason: str, token_given: bool) -> HTTPException:
    """401 with the same body whatever failed (FR-005). The reason goes to the log only."""
    logger.warning("Request refused (401): %s", reason)
    challenge = 'Bearer error="invalid_token"' if token_given else "Bearer"
    return HTTPException(
        status_code=401,
        detail="missing or invalid bearer token",
        headers={"WWW-Authenticate": challenge},
    )


def _unavailable(reason: str) -> HTTPException:
    logger.warning("Request refused (503): %s", reason)
    return HTTPException(status_code=503, detail="sign-in service unavailable, try again later")


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if header is None:
        raise _unauthorized("missing Authorization header", False)
    parts = header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise _unauthorized("Authorization header is not 'Bearer <token>'", False)
    return parts[1]


def verified_claims(request: Request, verifier: Verifier = Depends(get_verifier)) -> dict[str, Any]:
    """FastAPI dependency: the verified token's claims, or a 401 / 503. The only source of identity."""
    token = _bearer_token(request)
    try:
        key = verifier.keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=ALGORITHMS,
            audience=verifier.settings.audience,
            issuer=verifier.settings.issuer,
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except PyJWKClientError as e:
        if "Unable to find a signing key" in str(e):
            raise _unauthorized(f"{type(e).__name__}: {e}", True) from None
        raise _unavailable(f"{type(e).__name__}: {e}") from None  # includes connection errors
    except PyJWTError as e:
        raise _unauthorized(f"{type(e).__name__}: {e}", True) from None
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise _unauthorized("empty or non-string sub", True)
    return claims


def verified_token(request: Request, _claims: dict[str, Any] = Depends(verified_claims)) -> str:
    """FastAPI dependency: the raw bearer token, once `verified_claims` has accepted it.

    It is forwarded to the agent so the agent can verify it itself (spec 011). Never log it.
    """
    return _bearer_token(request)


def current_user(claims: dict[str, Any] = Depends(verified_claims)) -> str:
    """FastAPI dependency: the verified token's subject."""
    return claims["sub"]
