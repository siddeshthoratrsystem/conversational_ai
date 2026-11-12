"""TC-G08/H01/H06/J03/L06: contract negatives (P4 batch 3).

Characterization tests: they pin actual behavior measured on this backend.
- G08 trailing slash / double slash -> 307 to canonical (Starlette) or 404
- H01 interleaved chats to one session -> history complete and ordered
- H06 very long session id (10kB) -> tolerated (no cap), title still from message
- J03 no PII in server logs -> message text never logged (session_id only)
- L06 client never sees raw tracebacks -> uniform JSON detail envelope
"""

import logging

import pytest

def _no_stack_trace(res):
    assert "Traceback" not in res.text
    assert 'File "' not in res.text
    assert res.status_code != 500

# --- TC-G08 -----------------------------------------------------------------

def test_g08_trailing_slash_redirects_to_canonical(client):
    # Starlette convention: /api/chat/ -> 307 to /api/chat (does not create a chat)
    res = client.post("/api/chat/", json={"session_id": "g8a", "message": "hi"}, follow_redirects=False)
    assert res.status_code == 307
    assert res.headers.get("location", "").endswith("/api/chat")
    # Nothing was created: history is the uniform 404 for a missing session (spec 008)
    h = client.get("/api/chat/g8a/history")
    assert h.status_code == 404
    assert h.json() == {"detail": "session not found"}

def test_g08_history_trailing_slash_and_inner_double_slash(client):
    # Seed one chat
    assert client.post("/api/chat", json={"session_id": "g8b", "message": "hi"}).status_code == 200
    res = client.get("/api/chat/g8b/history/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers.get("location", "").endswith("/api/chat/g8b/history")
    res2 = client.get("/api/chat/g8b//history", follow_redirects=False)
    _no_stack_trace(res2)
    assert res2.status_code == 404

def test_g08_sessions_trailing_slash(client):
    res = client.get("/api/sessions/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers.get("location", "").endswith("/api/sessions")

# --- TC-H01 -----------------------------------------------------------------

def test_h01_interleaved_chats_to_one_session_complete_and_ordered(client):
    for text in ("first", "second", "third"):
        res = client.post("/api/chat", json={"session_id": "h1", "message": text})
        assert res.status_code == 200
    body = client.get("/api/chat/h1/history").json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"] * 3
    assert body["messages"][0]["content"] == "first"
    assert body["messages"][2]["content"] == "second"
    assert body["messages"][4]["content"] == "third"
    assert body["messages"][1]["content"] == "(mock) You said: first"

# --- TC-H06 -----------------------------------------------------------------

def test_h06_very_long_session_id_tolerated_and_listed(client):
    sid = "s" * 10240
    res = client.post("/api/chat", json={"session_id": sid, "message": "long id test"})
    assert res.status_code == 200
    assert res.json()["session_id"] == sid
    h = client.get(f"/api/chat/{sid}/history")
    assert h.status_code == 200
    assert h.json()["messages"][0]["content"] == "long id test"
    # Sessions list still works; title comes from the first message, not the id
    lst = client.get("/api/sessions", params=[("ids", sid)])
    assert lst.status_code == 200
    assert lst.json()["sessions"][0]["title"] == "long id test"

# --- TC-J03 -----------------------------------------------------------------

def test_j03_user_message_text_never_logged(client, caplog):
    secret = "SECRET-PII-98765-handle-family-finance"
    with caplog.at_level(logging.WARNING, logger="app.chat"):
        res = client.post("/api/chat", json={"session_id": "j03s", "message": secret})
    assert res.status_code == 200
    assert secret not in caplog.text
    # Session ids ARE logged (allowed); message bodies must not be
    assert "j03s" in caplog.text

# --- TC-L06 -----------------------------------------------------------------

@pytest.mark.parametrize("method,url,kwargs", [
    ("GET", "/api/nope", {}),
    ("POST", "/api/messages/abc/feedback", {"json": {"rating": "up"}}),
    ("POST", "/api/messages/1/feedback", {"json": {}}),
])
def test_l06_client_never_sees_raw_tracebacks(client, method, url, kwargs):
    res = client.request(method, url, **kwargs)
    _no_stack_trace(res)
    assert res.status_code in (400, 404, 422)
    assert "application/json" in res.headers.get("content-type", "")
    body = res.json()
    assert "detail" in body
    assert "Traceback" not in str(body)
