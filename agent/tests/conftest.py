"""Fixtures for the action gate tests (spec 011, task T016).

Everything runs without Postgres, Ollama, an identity provider or a network:
- signed tokens and a fake key client (the real cache and fallback code, with the network call replaced);
- an in-memory SQLite store with the gate's tables and a switch that makes the next statement fail;
- a scripted model that can wait on a barrier, so two turns can be held inside it at once;
- an injected clock and an injected monotonic that a test can advance mid-turn.

Gate modules are imported inside the fixtures, so tests that don't use them still collect.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from strands.models.model import Model

ISSUER = "https://idp.test/default"
AUDIENCE = "convai-api"
JWKS_URL = "https://idp.test/default/jwks"
KID = "test-key"
START = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


# --- tokens --------------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def wrong_key():
    """A key the identity provider has never published."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk_for(private_key, kid):
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


@pytest.fixture
def make_token(signing_key):
    """make_token(sub, ai_planning=True, key=None, headers=None, **claims) -> signed RS256 token.

    Pass a claim as None to drop it.
    """

    def make(sub="alice", ai_planning=True, key=None, headers=None, **claims):
        now = int(time.time())
        payload = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300, "sub": sub}
        if ai_planning is not None:
            payload["ai_planning"] = ai_planning
        payload.update(claims)
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, key or signing_key, algorithm="RS256", headers={"kid": KID, **(headers or {})})

    return make


@pytest.fixture
def bearer(make_token):
    """bearer(sub, **kw) -> the Authorization header value for a fresh signed token."""

    def header(sub="alice", **kw):
        return f"Bearer {make_token(sub, **kw)}"

    return header


@pytest.fixture
def keys(signing_key):
    """A fake key client publishing the signing key. `keys.fail = True` simulates an unreachable key set."""
    from jwt.exceptions import PyJWKClientConnectionError

    from wealth_agent.actions import identity

    class FakeKeyClient(identity.CachedKeyClient):
        def __init__(self, jwks):
            super().__init__(JWKS_URL, cooldown_duration=0)
            self.jwks = jwks
            self.fail = False
            self.fetches = 0

        def _fetch_remote(self):
            self.fetches += 1
            if self.fail:
                raise PyJWKClientConnectionError("fetch failed: connection refused")
            data = {"keys": list(self.jwks)}
            if self.jwk_set_cache is not None:
                self.jwk_set_cache.put(data)
            return data

    return FakeKeyClient([jwk_for(signing_key, KID)])


@pytest.fixture
def verifier(keys, monkeypatch):
    """Make `identity.verify_participant` use the fake key client and the test issuer and audience."""
    from wealth_agent.actions import identity

    v = identity.Verifier(identity.OidcSettings(ISSUER, AUDIENCE, JWKS_URL), keys)
    monkeypatch.setattr(identity, "get_verifier", lambda: v)
    return v


# --- the store -------------------------------------------------------------------------------------


class StoreSwitch:
    """Makes statements fail: `switch.fail("error")` or `switch.fail("timeout")`, once by default."""

    def __init__(self):
        self.mode = None
        self.times = 0
        self.only = None  # fail only statements whose text contains this

    def fail(self, mode="error", times=1, only=None):
        self.mode, self.times, self.only = mode, times, only

    def heal(self):
        self.mode, self.times, self.only = None, 0, None

    def check(self, statement):
        from sqlalchemy.exc import OperationalError

        if self.mode is None or self.times <= 0:
            return
        if self.only and self.only.lower() not in statement.lower():
            return
        self.times -= 1
        message = (
            "canceling statement due to statement timeout" if self.mode == "timeout" else "connection lost"
        )
        raise OperationalError(statement, {}, Exception(message))


@pytest.fixture
def engine():
    """In-memory SQLite with the gate's tables and the minimal sessions table."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool

    from wealth_agent.actions import store

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def enforce_foreign_keys(dbapi_conn, _record):  # SQLite ignores FKs unless asked, unlike Postgres
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    store.metadata.create_all(eng)
    eng.switch = StoreSwitch()

    @event.listens_for(eng, "before_cursor_execute")
    def maybe_fail(conn, cursor, statement, parameters, context, executemany):
        eng.switch.check(statement)

    yield eng
    eng.dispose()


@pytest.fixture
def switch(engine):
    return engine.switch


@pytest.fixture
def gate_store(engine):
    from wealth_agent.actions import store

    return store.Store(engine, timeout_ms=3000)


def add_session(engine, session_id="s1", user_id="alice"):
    """Insert the chat's session row, as the back end does before it calls the agent.

    The agent's `sessions` table is minimal (just `id`), so `user_id` is accepted only to keep
    call sites readable.
    """
    from sqlalchemy import insert

    from wealth_agent.actions import store

    with engine.begin() as conn:
        conn.execute(insert(store.sessions).values(id=session_id))


@pytest.fixture
def session_row(engine):
    return lambda session_id="s1", user_id="alice": add_session(engine, session_id, user_id)


# --- time ---------------------------------------------------------------------------------------------


class Clock:
    """An injected wall clock: call it for the time, `advance(seconds)` to move it."""

    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class Monotonic:
    """An injected monotonic clock for the staging deadline; a test can advance it during a turn."""

    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def monotonic():
    return Monotonic()


# --- the scripted model ---------------------------------------------------------------------------------


class ScriptedModel(Model):
    """Replays a list of steps, one per model call.

    Steps: ("tool", name, args), ("text", text), or ("do", callable) which runs the callable first
    and then yields "ok" text. It records whether it was called, and can wait on a
    `threading.Barrier` on its first call so two turns can be held inside the model together.
    """

    def __init__(self, steps=(), barrier: threading.Barrier | None = None):
        self.steps = list(steps)
        self.calls = 0
        self.called = False
        self.barrier = barrier
        self.seen_messages: list = []

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {"model_id": "scripted"}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.called = True
        self.seen_messages.append(json.loads(json.dumps(list(messages), default=str)))
        if self.barrier is not None and self.calls == 0:
            self.barrier.wait(timeout=10)
        step = self.steps[self.calls]
        self.calls += 1
        if step[0] == "do":
            step[1]()
            step = ("text", "ok")
        yield {"messageStart": {"role": "assistant"}}
        if step[0] == "tool":
            _, name, args = step
            yield {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": f"t{self.calls}"}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": step[1]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        }
