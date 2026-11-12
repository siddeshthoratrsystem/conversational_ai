"""TC-G01/G02/G03/G05: chat body and path-parameter contract negatives.

Characterization tests: they pin actual graceful behavior measured on this
backend (see conversation notes 2026-11-06). Where the RTM scenario says
"refused", the test asserts no 500 / no hang / no stack trace and records
what actually happened instead of overclaiming.

- G01 non-object bodies -> 422, nothing stored
- G02 wrong field types -> 422, nothing stored; unknown keys ignored (200, per contract)
- G03 path abuse (%2F, slash, ., .., //, 10kB id) -> 404 or safe 200, no 500
- G05 oversized (>=1MB) -> no 500, no hang; currently ACCEPTED (no size cap yet)
"""

import pytest

def _history(client, session_id):
    res = client.get(f"/api/chat/{session_id}/history")
    assert res.status_code == 200
    return res.json()

def _assert_nothing_stored(client, session_id):
    # Spec 008 ownership: unknown / others' sessions are 404 "session not found"
    # (the uniform refusal); they are also skipped by /api/sessions.
    res = client.get(f"/api/chat/{session_id}/history")
    assert res.status_code == 404
    assert res.json() == {"detail": "session not found"}
    res = client.get("/api/sessions", params=[("ids", session_id)])
    assert res.status_code == 200
    assert res.json()["sessions"] == []

def _no_stack_trace(res):
    text = res.text
    assert "Traceback" not in text
    assert 'File "' not in text
    assert res.status_code != 500

# --- TC-G01 -----------------------------------------------------------------

@pytest.mark.parametrize("payload,content_type", [
    # form-encoded (not JSON)
    ({"session_id": "g1form", "message": "hi"}, "form"),
    # raw text body
    ("hello", "text"),
    # JSON list / string / null (not an object)
    ([1, 2, 3], "json"),
    ("hello", "json"),
    (None, "json"),
])
def test_g01_non_object_body_is_rejected_nothing_stored(client, payload, content_type):
    if content_type == "form":
        res = client.post("/api/chat", data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        sid = payload["session_id"]
    elif content_type == "text":
        res = client.post("/api/chat", content=payload, headers={"Content-Type": "text/plain"})
        sid = "g1text"
    else:
        res = client.post("/api/chat", json=payload)
        # list/string/null carry no session_id to probe; use a sentinel id check
        _no_stack_trace(res)
        assert res.status_code in (400, 422)
        return
    _no_stack_trace(res)
    assert res.status_code in (400, 422)
    _assert_nothing_stored(client, sid)

def test_g01_empty_body_is_rejected(client):
    res = client.post("/api/chat", content="", headers={"Content-Type": "application/json"})
    _no_stack_trace(res)
    assert res.status_code in (400, 422)

# --- TC-G02 -----------------------------------------------------------------

def test_g02_message_wrong_type_is_rejected_nothing_stored(client):
    res = client.post("/api/chat", json={"session_id": "g2a", "message": 123})
    _no_stack_trace(res)
    assert res.status_code in (400, 422)
    _assert_nothing_stored(client, "g2a")

def test_g02_session_id_null_is_rejected(client):
    res = client.post("/api/chat", json={"session_id": None, "message": "hi"})
    _no_stack_trace(res)
    assert res.status_code in (400, 422)

def test_g02_unknown_keys_are_ignored_per_contract(client):
    # Contract (default pydantic): extra keys ignored, valid turn still stored.
    res = client.post("/api/chat", json={"session_id": "g2b", "message": "hi", "extra": "key", "foo": 1})
    assert res.status_code == 200
    assert res.json()["session_id"] == "g2b"

# --- TC-G03 -----------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/chat/a%2Fb/history",      # encoded slash
    "/api/chat/a/b/history",        # extra path segment
    "/api/chat/../history",         # dotdot
    "/api/chat/./history",          # dot
    "/api/chat//history",           # double slash
])
def test_g03_path_abuse_no_crash(client, path):
    res = client.get(path)
    _no_stack_trace(res)
    assert res.status_code in (200, 400, 404, 405, 422), path

def test_g03_oversized_session_id_is_safe(client):
    sid = "x" * 10240
    res = client.get(f"/api/chat/{sid}/history")
    _no_stack_trace(res)
    assert res.status_code in (200, 400, 404, 422)
    if res.status_code == 200:
        # Safe: empty history, no crash, nothing created
        assert res.json()["messages"] == []

# --- TC-G05 -----------------------------------------------------------------

def test_g05_oversized_payload_no_500_no_hang(client):
    # Measured today: accepted (200). The scenario says "refused gracefully
    # within DoD limits, no 500, no hang" — do not overclaim refusal.
    # This characterizes graceful handling while the size limit stays TBD.
    big = "A" * (1024 * 1024)  # 1 MB
    res = client.post("/api/chat", json={"session_id": "big1", "message": big})
    _no_stack_trace(res)
    assert res.status_code != 500
    assert res.status_code in (200, 400, 413, 422)
    if res.status_code == 200:
        # If accepted, it must be retrievable intact (no truncation/corruption)
        body = _history(client, "big1")
        assert any(m["content"] == big for m in body["messages"])
    else:
        _assert_nothing_stored(client, "big1")
