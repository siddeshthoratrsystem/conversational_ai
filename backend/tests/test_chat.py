import logging

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app import agent as agent_module
from app import main, models
from app.agent import AgentError, AgentReply


def post_chat(client, session_id="s1", message="hello"):
    return client.post("/api/chat", json={"session_id": session_id, "message": message})


def test_mock_fallback_when_agent_url_empty(client, engine, caplog):
    with caplog.at_level(logging.WARNING, logger="app.chat"):
        r = post_chat(client, message="hi")

    assert r.status_code == 200
    body = r.json()
    message_id = body.pop("message_id")  # added by spec 002; checked in test_chat_response_*
    assert body == {"session_id": "s1", "reply": "(mock) You said: hi", "intent": None}
    assert isinstance(message_id, int)
    assert any("mock reply" in rec.message for rec in caplog.records)

    with Session(engine) as db:
        rows = db.scalars(select(models.Message).order_by(models.Message.id)).all()
        assert [(m.role, m.content, m.source) for m in rows] == [
            ("user", "hi", None),
            ("assistant", "(mock) You said: hi", "mock"),
        ]


def test_mock_fallback_when_agent_call_fails(client, monkeypatch, caplog):
    monkeypatch.setenv("AGENT_URL", "http://agent.invalid/invocations")

    def boom(*args, **kwargs):
        raise AgentError("ConnectTimeout: timed out")

    monkeypatch.setattr(main, "call_agent", boom)

    with caplog.at_level(logging.WARNING, logger="app.chat"):
        r = post_chat(client, message="hi")

    assert r.status_code == 200
    assert r.json()["reply"] == "(mock) You said: hi"
    assert any("ConnectTimeout" in rec.message for rec in caplog.records)
    assert client.get("/api/chat/s1/history").json()["messages"][1]["source"] == "mock"


def test_agent_reply_is_stored_with_source_agent(client, monkeypatch):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    monkeypatch.setattr(
        main,
        "call_agent",
        lambda url, sid, msg, **kwargs: AgentReply(reply="Sure!", intent="get_quote", latency_ms=42),
    )

    r = post_chat(client, message="I need a quote")

    body = r.json()
    message_id = body.pop("message_id")  # added by spec 002; checked in test_chat_response_*
    assert body == {"session_id": "s1", "reply": "Sure!", "intent": "get_quote"}
    assert isinstance(message_id, int)
    assistant = client.get("/api/chat/s1/history").json()["messages"][1]
    assert assistant["source"] == "agent"
    assert assistant["intent"] == "get_quote"
    assert assistant["latency_ms"] == 42


@pytest.mark.parametrize(
    "payload, detail",
    [
        ({"session_id": "s1", "message": ""}, "message must not be empty"),
        ({"session_id": "s1", "message": "   "}, "message must not be empty"),
        ({"session_id": "", "message": "hi"}, "session_id must not be empty"),
        ({"session_id": "  ", "message": "hi"}, "session_id must not be empty"),
    ],
)
def test_empty_fields_return_400_and_store_nothing(client, engine, payload, detail):
    r = client.post("/api/chat", json=payload)

    assert r.status_code == 400
    assert r.json() == {"detail": detail}
    with Session(engine) as db:
        assert db.scalars(select(models.Message)).all() == []
        assert db.scalars(select(models.Session)).all() == []


def test_history_returns_messages_in_order(client):
    post_chat(client, message="first")
    post_chat(client, message="second")
    post_chat(client, session_id="other", message="not mine")

    r = client.get("/api/chat/s1/history")

    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s1"
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "first"),
        ("assistant", "(mock) You said: first"),
        ("user", "second"),
        ("assistant", "(mock) You said: second"),
    ]
    ids = [m["id"] for m in body["messages"]]
    assert ids == sorted(ids)


def test_history_for_unknown_session_is_404_and_creates_nothing(client, engine):
    r = client.get("/api/chat/does-not-exist/history")

    assert r.status_code == 404  # spec 008 FR-014: same answer as another user's chat
    assert r.json() == {"detail": "session not found"}
    with Session(engine) as db:
        assert db.scalars(select(models.Session)).all() == []


# --- message_id on the chat response (spec 002, contract point 1) -------------------------------


def assistant_row(engine, message_id):
    with Session(engine) as db:
        return db.get(models.Message, message_id)


def test_chat_response_has_exactly_the_documented_keys(client):
    r = post_chat(client, message="hi")

    assert set(r.json()) == {"session_id", "reply", "intent", "message_id"}
    assert isinstance(r.json()["message_id"], int)  # typed integer | null, never null today


def test_chat_response_message_id_is_the_mock_assistant_message(client, engine):
    r = post_chat(client, message="hi")

    row = assistant_row(engine, r.json()["message_id"])
    assert (row.role, row.content, row.source) == ("assistant", "(mock) You said: hi", "mock")


def test_chat_response_message_id_is_the_agent_assistant_message(client, engine, monkeypatch):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    monkeypatch.setattr(
        main,
        "call_agent",
        lambda url, sid, msg, **kwargs: AgentReply(reply="Sure!", intent="get_quote", latency_ms=42),
    )

    r = post_chat(client, message="I need a quote")

    row = assistant_row(engine, r.json()["message_id"])
    assert (row.role, row.content, row.source) == ("assistant", "Sure!", "agent")


def test_chat_response_does_not_expose_the_user_message_id(client, engine):
    r = post_chat(client, message="hi")

    with Session(engine) as db:
        user = db.scalars(select(models.Message).where(models.Message.role == "user")).one()
    assert r.json()["message_id"] != user.id


def test_each_turn_returns_a_different_message_id(client):
    first = post_chat(client, message="one").json()["message_id"]
    second = post_chat(client, message="two").json()["message_id"]

    assert first != second


# --- spec 011: the back end is a pass-through that forwards the token -------------------------


def test_the_session_row_is_committed_before_the_agent_is_called(client, engine, monkeypatch):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    commits = []
    event.listen(engine, "commit", lambda conn: commits.append(1))
    seen = {}

    def fake(url, sid, msg, **kwargs):
        seen["commits"] = len(commits)
        with Session(engine) as other:  # a separate session, as another process would be
            seen["row"] = other.get(models.Session, sid)
        return AgentReply(reply="ok", intent=None, latency_ms=1)

    monkeypatch.setattr(main, "call_agent", fake)
    assert post_chat(client).status_code == 200

    assert seen["commits"] >= 1
    assert seen["row"] is not None and seen["row"].user_id == "alice"


def test_the_participants_token_is_forwarded_unchanged_and_never_logged(client, monkeypatch, caplog):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    tokens = []

    def fake(url, sid, msg, **kwargs):
        tokens.append(kwargs.get("token"))
        return AgentReply(reply="ok", intent=None, latency_ms=1)

    monkeypatch.setattr(main, "call_agent", fake)
    sent = client.headers["Authorization"].removeprefix("Bearer ")
    with caplog.at_level(logging.DEBUG):
        assert post_chat(client).status_code == 200

    assert tokens == [sent]
    assert sent not in caplog.text


def test_a_gate_reply_is_stored_and_returned_as_gate(client, monkeypatch):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    monkeypatch.setattr(
        main,
        "call_agent",
        lambda url, sid, msg, **kwargs: AgentReply(reply="Summary", intent=None, latency_ms=3, source="gate"),
    )
    r = post_chat(client, message="change it to 8%")

    assert r.json()["reply"] == "Summary"
    assistant = client.get("/api/chat/s1/history").json()["messages"][1]
    assert assistant["source"] == "gate"


def test_a_malformed_source_is_stored_as_agent(client, monkeypatch):
    import httpx

    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    real_client = httpx.Client
    body = {"reply": "ok", "intent": None, "source": "bogus"}
    monkeypatch.setattr(
        agent_module.httpx,
        "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)), **kw),
    )
    assert post_chat(client).status_code == 200
    assert client.get("/api/chat/s1/history").json()["messages"][1]["source"] == "agent"


def test_the_mock_fallback_is_unchanged(client):
    r = post_chat(client, message="hi")
    assert r.json()["reply"] == "(mock) You said: hi"
    assert client.get("/api/chat/s1/history").json()["messages"][1]["source"] == "mock"


def test_a_failed_message_write_leaves_an_empty_hidden_session(client, engine, monkeypatch):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    monkeypatch.setattr(
        main, "call_agent", lambda url, sid, msg, **kw: AgentReply(reply="ok", intent=None, latency_ms=1)
    )

    def fail_on_message_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO MESSAGES"):
            raise RuntimeError("disk full")

    event.listen(engine, "before_cursor_execute", fail_on_message_insert)
    with pytest.raises(Exception):
        post_chat(client)
    event.remove(engine, "before_cursor_execute", fail_on_message_insert)

    with Session(engine) as db:
        assert db.get(models.Session, "s1") is not None
        assert db.scalars(select(models.Message)).all() == []
    assert client.get("/api/sessions?ids=s1").json() == {"sessions": []}
