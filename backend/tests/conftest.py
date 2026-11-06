import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientConnectionError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.auth import ALGORITHMS, CachedKeyClient, Settings, Verifier, get_verifier
from app.db import Base, get_db
from app.main import app

ISSUER = "https://idp.test/default"
AUDIENCE = "convai-api"
JWKS_URL = "https://idp.test/default/jwks"
KID = "test-key"


def _new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def signing_key():
    return _new_key()


@pytest.fixture(scope="session")
def wrong_key():
    """A key the identity provider has never published."""
    return _new_key()


def jwk_for(private_key, kid):
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


class FakeKeyClient(CachedKeyClient):
    """The real key client (cache, cooldown, last-good fallback) with the network call replaced."""

    def __init__(self, keys, **kwargs):
        super().__init__(JWKS_URL, **kwargs)
        self.keys = keys  # list of jwk dicts
        self.fail = False
        self.fetches = 0

    def _fetch_remote(self):
        self.fetches += 1
        if self.fail:
            raise PyJWKClientConnectionError("fetch failed: connection refused")
        data = {"keys": list(self.keys)}
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(data)
        return data


@pytest.fixture
def keys(signing_key):
    return FakeKeyClient([jwk_for(signing_key, KID)], cooldown_duration=0)


@pytest.fixture
def verifier(keys):
    v = Verifier(Settings(ISSUER, AUDIENCE, JWKS_URL), keys)
    app.dependency_overrides[get_verifier] = lambda: v
    yield v
    app.dependency_overrides.pop(get_verifier, None)


@pytest.fixture
def make_token(signing_key):
    def make(sub="alice", key=None, headers=None, **claims):
        now = int(time.time())
        # ai_planning: the default user may use AI planning (spec 009); pass None to drop it.
        payload = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300, "sub": sub, "ai_planning": True}
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}  # None removes a claim
        hdrs = {"kid": KID, **(headers or {})}
        return jwt.encode(payload, key or signing_key, algorithm="RS256", headers=hdrs)

    return make


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


@pytest.fixture
def unsigned_token():
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "exp": now + 300, "sub": "alice"}
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."


@pytest.fixture
def engine():
    """In-memory SQLite, so tests need no running Postgres."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(dbapi_conn, _record):  # SQLite ignores FKs unless asked, unlike Postgres
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def raw_client(engine, monkeypatch, verifier):
    """A client that sends no token."""
    monkeypatch.delenv("AGENT_URL", raising=False)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(raw_client, make_token):
    """The default client: signed in as alice. Pass headers= per request to act as someone else."""
    raw_client.headers["Authorization"] = f"Bearer {make_token()}"
    return raw_client


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


assert ALGORITHMS  # keep the import honest: tests rely on the same list as the app
