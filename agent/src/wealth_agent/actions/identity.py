"""Verify the participant's own bearer token inside the agent (spec 011, FR-014 to FR-016).

The rules are those of `backend/app/auth.py`, copied because the agent cannot import the back end;
`tests/test_identity.py` mirrors the back end's token cases so drift is caught. Only public-key
algorithms are accepted and the key always comes from the provider's key set. `verify_participant`
never raises and never logs the token.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import jwt
from jwt import PyJWKClient
from jwt.exceptions import ExpiredSignatureError, PyJWKClientConnectionError, PyJWKClientError, PyJWTError

logger = logging.getLogger("wealth_agent.actions.identity")

ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
LEEWAY_SECONDS = 60  # tolerance for small clock differences, as in the back end
SETTING_NAMES = ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL")

SignInFailure = Literal["sign_in_token_missing", "sign_in_token_expired", "sign_in_token_invalid"]


@dataclass(frozen=True)
class Participant:
    id: str  # the verified token's sub
    claims: dict  # for ai_planning and StepUpCheck; never logged or stored


@dataclass(frozen=True)
class Verification:
    participant: Participant | None
    failure: SignInFailure | None  # set exactly when participant is None


@dataclass(frozen=True)
class OidcSettings:
    issuer: str
    audience: str
    jwks_url: str


class CachedKeyClient(PyJWKClient):
    """PyJWKClient that keeps using the last key set it fetched while the key address is down."""

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
            logger.warning("Key address unreachable (%s); using the last key set fetched", type(e).__name__)
            return self._last_good
        self._last_good = data
        return data


@dataclass
class Verifier:
    settings: OidcSettings
    keys: PyJWKClient


def read_oidc_settings(env=None) -> OidcSettings | None:
    """The three OIDC settings, or None if any is missing or blank."""
    env = os.environ if env is None else env
    values = {name: (env.get(name) or "").strip() for name in SETTING_NAMES}
    if not all(values.values()):
        return None
    return OidcSettings(values["OIDC_ISSUER"], values["OIDC_AUDIENCE"], values["OIDC_JWKS_URL"])


@lru_cache
def get_verifier() -> Verifier | None:
    """Settings plus the key client; no network call is made here. Tests replace this."""
    settings = read_oidc_settings()
    return Verifier(settings, CachedKeyClient(settings.jwks_url)) if settings else None


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        return None
    return parts[1]


def _failure(failure: SignInFailure) -> Verification:
    return Verification(None, failure)


def verify_participant(authorization: str | None) -> Verification:
    """The participant behind an `Authorization` header, or the reason there is none."""
    token = _bearer_token(authorization)
    if token is None:
        return _failure("sign_in_token_missing")
    try:
        verifier = get_verifier()
        if verifier is None:
            logger.warning("Sign-in settings are missing; cannot verify the token")
            return _failure("sign_in_token_invalid")
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
    except ExpiredSignatureError:
        return _failure("sign_in_token_expired")
    except PyJWKClientConnectionError as e:
        logger.warning("Could not fetch the key set (%s)", type(e).__name__)
        return _failure("sign_in_token_invalid")
    except (PyJWKClientError, PyJWTError) as e:
        logger.info("Sign-in token refused (%s)", type(e).__name__)
        return _failure("sign_in_token_invalid")
    except Exception as e:  # noqa: BLE001 - a bad header must never break chat
        logger.warning("Sign-in token check failed (%s)", type(e).__name__)
        return _failure("sign_in_token_invalid")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        return _failure("sign_in_token_invalid")
    return Verification(Participant(sub, claims), None)
