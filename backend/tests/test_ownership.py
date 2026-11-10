"""Per-user ownership (spec 008, contracts/auth-api.md test points 12-19 and 26)."""

import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import main, models
from app.agent import AgentReply
from tests.conftest import bearer

NOT_FOUND_SESSION = {"detail": "session not found"}
NOT_FOUND_MESSAGE = {"detail": "message not found"}


@pytest.fixture
def bob(make_token):
    return bearer(make_token(sub="bob"))


def chat(client, session_id="s1", message="hello", **kw):
    return client.post("/api/chat", json={"session_id": session_id, "message": message}, **kw)


def owner_of(engine, session_id):
    with Session(engine) as db:
        return db.get(models.Session, session_id).user_id


def message_count(engine):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(models.Message))


def ownerless_session(engine, session_id="old"):
    """A chat stored before this feature: it has no owner."""
    with Session(engine) as db:
        db.add(models.Session(id=session_id))
        db.flush()
        db.add(models.Message(session_id=session_id, role="user", content="old question"))
        db.add(models.Message(session_id=session_id, role="assistant", content="old", source="mock"))
        db.commit()
        return [m.id for m in db.scalars(select(models.Message).order_by(models.Message.id))]


def test_new_chat_is_stored_under_the_caller(client, engine):
    assert chat(client).status_code == 200
    assert owner_of(engine, "s1") == "alice"


def test_user_id_in_the_request_is_ignored(client, engine):
    r = client.post(
        "/api/chat?user_id=mallory",
        json={"session_id": "s1", "message": "hi", "user_id": "mallory"},
        headers={"X-User-Id": "mallory"},
    )
    assert r.status_code == 200
    assert owner_of(engine, "s1") == "alice"


def test_owner_reads_own_history(client):
    chat(client)
    r = client.get("/api/chat/s1/history")
    assert r.status_code == 200
    assert [m["role"] for m in r.json()["messages"]] == ["user", "assistant"]


def test_other_users_history_is_404_same_as_unknown(client, bob, engine):
    chat(client)
    other = client.get("/api/chat/s1/history", headers=bob)
    unknown = client.get("/api/chat/does-not-exist/history")
    assert other.status_code == 404
    assert other.json() == NOT_FOUND_SESSION
    assert (unknown.status_code, unknown.json()) == (other.status_code, other.json())
    with Session(engine) as db:
        assert db.get(models.Session, "does-not-exist") is None


def test_other_users_chat_post_is_404_and_stores_nothing(client, bob, engine, monkeypatch):
    chat(client)
    before = message_count(engine)
    monkeypatch.setenv("AGENT_URL", "http://agent.invalid/invocations")

    def spy(*a, **k):
        raise AssertionError("agent must not be called")

    monkeypatch.setattr(main, "call_agent", spy)

    r = chat(client, message="intruding", headers=bob)
    assert r.status_code == 404
    assert r.json() == NOT_FOUND_SESSION
    assert message_count(engine) == before
    assert owner_of(engine, "s1") == "alice"


def test_feedback_on_other_users_answer_is_404_and_leaves_feedback(client, bob, engine):
    message_id = chat(client).json()["message_id"]
    client.post(f"/api/messages/{message_id}/feedback", json={"rating": "up"})

    r = client.post(f"/api/messages/{message_id}/feedback", json={"rating": "down"}, headers=bob)
    assert r.status_code == 404
    assert r.json() == NOT_FOUND_MESSAGE
    with Session(engine) as db:
        assert db.scalars(select(models.Feedback)).one().rating == "up"


def test_feedback_on_other_users_user_message_is_404_not_400(client, bob):
    chat(client)
    messages = client.get("/api/chat/s1/history").json()["messages"]
    user_msg = next(m["id"] for m in messages if m["role"] == "user")

    mine = client.post(f"/api/messages/{user_msg}/feedback", json={"rating": "up"})
    theirs = client.post(f"/api/messages/{user_msg}/feedback", json={"rating": "up"}, headers=bob)
    assert mine.status_code == 400  # the owner still gets the spec 002 refusal
    assert theirs.status_code == 404
    assert theirs.json() == NOT_FOUND_MESSAGE


def test_feedback_for_unknown_message_matches_other_users_message(client, bob):
    message_id = chat(client).json()["message_id"]
    other = client.post(f"/api/messages/{message_id}/feedback", json={"rating": "up"}, headers=bob)
    unknown = client.post("/api/messages/99999/feedback", json={"rating": "up"}, headers=bob)
    assert (other.status_code, other.json()) == (unknown.status_code, unknown.json())


def test_session_list_only_has_the_callers_chats(client, bob):
    chat(client, "alice-chat")
    chat(client, "bob-chat", headers=bob)
    ids = "ids=alice-chat&ids=bob-chat"

    mine = client.get(f"/api/sessions?{ids}").json()["sessions"]
    theirs = client.get(f"/api/sessions?{ids}", headers=bob).json()["sessions"]
    assert [s["session_id"] for s in mine] == ["alice-chat"]
    assert [s["session_id"] for s in theirs] == ["bob-chat"]


def test_chats_without_an_owner_look_nonexistent_to_everyone(client, engine):
    ids = ownerless_session(engine)
    assistant_id = ids[1]
    before = message_count(engine)

    assert client.get("/api/chat/old/history").status_code == 404
    assert chat(client, "old").status_code == 404
    r = client.post(f"/api/messages/{assistant_id}/feedback", json={"rating": "up"})
    assert r.status_code == 404
    assert client.get("/api/sessions?ids=old").json() == {"sessions": []}
    assert message_count(engine) == before
    assert owner_of(engine, "old") is None


def test_ownership_refusals_are_logged_with_the_case(client, bob, caplog):
    chat(client)
    with caplog.at_level(logging.WARNING, logger="app.chat"):
        client.get("/api/chat/s1/history", headers=bob)
        client.get("/api/chat/nope/history", headers=bob)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "someone else" in text
    assert "missing" in text


def test_two_users_racing_for_one_new_session_id(client, bob, engine, monkeypatch):
    """Bob creates the chat between alice's owner check and her insert; only one user can own it.

    The race is now at session creation, before the agent call: alice gets 404 and the agent is
    not called for her (research R20).
    """
    monkeypatch.setenv("AGENT_URL", "http://agent.invalid/invocations")
    calls = []

    def agent_spy(url, session_id, message, **kwargs):
        calls.append(session_id)
        return AgentReply(reply="agent says hi", intent=None, latency_ms=5)

    monkeypatch.setattr(main, "call_agent", agent_spy)

    real_check = main._check_owner
    state = {"calls": 0}

    def check_then_lose_the_race(db, session_id, user_id):
        found = real_check(db, session_id, user_id)
        state["calls"] += 1
        if not found and state["calls"] == 2:  # the check made while creating the session row
            with Session(engine) as other:  # bob's chat is stored right after alice's check
                other.add(models.Session(id=session_id, user_id="bob"))
                other.commit()
        return found

    monkeypatch.setattr(main, "_check_owner", check_then_lose_the_race)
    r = chat(client, "race", "alices first")

    assert r.status_code == 404
    assert r.json() == NOT_FOUND_SESSION
    assert owner_of(engine, "race") == "bob"
    assert calls == []
    assert message_count(engine) == 0
