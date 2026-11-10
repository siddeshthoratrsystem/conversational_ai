"""Access to AI planning (spec 009 US3, research R8, contracts/api-auth.md)."""

import json
import logging

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import agent, main, models
from app.agent import AgentReply
from conftest import bearer


@pytest.fixture
def as_user(make_token):
    """Headers for a signed-in user with the given claims (None removes a claim)."""

    def headers(sub="alice", **claims):
        return bearer(make_token(sub, **claims))

    return headers


def access_for(client, headers):
    return client.get("/api/me", headers=headers).json()["access"]


def chat(client, headers, session_id="s1", message="hello"):
    return client.post("/api/chat", json={"session_id": session_id, "message": message}, headers=headers)


@pytest.fixture
def agent_calls(monkeypatch):
    """Answer through a fake agent and record how it was called."""
    calls = []

    def fake_call_agent(url, session_id, message, education_only=False, **kwargs):
        calls.append({"session_id": session_id, "education_only": education_only})
        return AgentReply(reply="agent reply", intent=None, latency_ms=5)

    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    return calls


# --- who is signed in --------------------------------------------------------------------------


def test_me_reports_the_signed_in_user(client, as_user):
    r = client.get("/api/me", headers=as_user("sub-alice", name="Alice Ng", ai_planning=True))
    assert r.status_code == 200
    assert r.json() == {"user_id": "sub-alice", "name": "Alice Ng", "access": "granted"}


def test_me_name_falls_back_to_username_then_sub(client, as_user):
    assert client.get("/api/me", headers=as_user("sub-a", preferred_username="alice")).json()["name"] == "alice"
    assert client.get("/api/me", headers=as_user("sub-a")).json()["name"] == "sub-a"


def test_me_needs_a_token(raw_client):
    assert raw_client.get("/api/me").status_code == 401


# --- the decision ------------------------------------------------------------------------------


def test_claim_true_is_granted(client, as_user):
    assert access_for(client, as_user(ai_planning=True)) == "granted"


def test_claim_false_is_denied(client, as_user):
    assert access_for(client, as_user(ai_planning=False)) == "denied"


@pytest.mark.parametrize("claim", [None, "true", 1])
def test_missing_or_unreadable_claim_is_unavailable(client, as_user, claim):
    assert access_for(client, as_user(ai_planning=claim)) == "unavailable"


@pytest.mark.parametrize("deny", ["bob", "sub-bob", " other , bob "])
def test_deny_list_wins_over_the_claim(client, as_user, monkeypatch, deny):
    monkeypatch.setenv("ENTITLEMENT_DENY", deny)
    assert access_for(client, as_user("sub-bob", preferred_username="bob", ai_planning=True)) == "denied"
    assert access_for(client, as_user("sub-alice", preferred_username="alice", ai_planning=True)) == "granted"


def test_forced_unavailable_mode(client, as_user, monkeypatch):
    monkeypatch.setenv("ENTITLEMENT_MODE", "unavailable")
    assert access_for(client, as_user(ai_planning=True)) == "unavailable"


# --- what each result does ---------------------------------------------------------------------


def test_denied_chat_is_refused_and_stores_nothing(client, as_user, engine, caplog):
    with caplog.at_level(logging.WARNING, logger="app.chat"):
        r = chat(client, as_user("bob", ai_planning=False))
    assert r.status_code == 403
    assert r.json() == {"detail": "AI planning is not available for this account"}
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(models.Session)) == 0
    assert "bob" in caplog.text and "s1" in caplog.text


def test_unavailable_chat_is_education_only(client, as_user, engine, agent_calls):
    r = chat(client, as_user(ai_planning=None))
    assert r.status_code == 200
    assert r.json()["education_only"] is True
    assert agent_calls == [{"session_id": "s1", "education_only": True}]
    with Session(engine) as db:
        session = db.get(models.Session, "s1")
        assert session.access == "unavailable"
        assert session.access_checked_at is not None


def test_granted_chat_is_not_education_only(client, as_user, engine, agent_calls):
    r = chat(client, as_user(ai_planning=True))
    assert "education_only" not in r.json()
    assert agent_calls == [{"session_id": "s1", "education_only": False}]
    with Session(engine) as db:
        assert db.get(models.Session, "s1").access == "granted"


def test_access_is_updated_on_every_turn(client, as_user, engine, monkeypatch, agent_calls):
    chat(client, as_user(ai_planning=True))
    monkeypatch.setenv("ENTITLEMENT_MODE", "unavailable")
    chat(client, as_user(ai_planning=True), message="again")
    with Session(engine) as db:
        assert db.get(models.Session, "s1").access == "unavailable"


def test_mock_reply_also_reports_education_only(client, as_user):
    r = chat(client, as_user(ai_planning=None))  # no AGENT_URL: mock reply
    assert r.json()["education_only"] is True


def test_someone_elses_chat_is_still_404_before_the_access_check(client, as_user):
    chat(client, as_user("alice", ai_planning=True))
    assert chat(client, as_user("bob", ai_planning=False)).status_code == 404


# --- the agent request -------------------------------------------------------------------------


def _agent_body(monkeypatch, **kwargs):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"reply": "ok", "intent": None})

    real_client = httpx.Client
    monkeypatch.setattr(agent.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    agent.call_agent("http://agent.test/invocations", "s1", "hi", **kwargs)
    return bodies[0]


def test_agent_gets_education_only_flag_when_set(monkeypatch):
    assert _agent_body(monkeypatch, education_only=True) == {"prompt": "hi", "session_id": "s1", "education_only": True}


def test_agent_body_is_unchanged_otherwise(monkeypatch):
    assert _agent_body(monkeypatch) == {"prompt": "hi", "session_id": "s1"}
