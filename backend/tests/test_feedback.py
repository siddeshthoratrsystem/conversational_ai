import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import feedback, main, models
from app.agent import AgentReply


# --- helpers -----------------------------------------------------------------------------------


def send_chat(client, session_id="s1", message="hello"):
    """Send a chat message and return the assistant message_id from the reply."""
    r = client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert r.status_code == 200
    return r.json()["message_id"]


def user_message_id(client, session_id="s1"):
    """The id of the first user message in the session, read from the history endpoint."""
    messages = client.get(f"/api/chat/{session_id}/history").json()["messages"]
    return next(m["id"] for m in messages if m["role"] == "user")


def add_turn(engine, session_id="s1", user_id="alice"):
    """Insert a session with one user and one assistant message directly. Returns (user_id, assistant_id)."""
    with Session(engine) as db:
        db.add(models.Session(id=session_id, user_id=user_id))
        db.flush()
        user = models.Message(session_id=session_id, role="user", content="hi")
        assistant = models.Message(
            session_id=session_id, role="assistant", content="hello", source="mock"
        )
        db.add_all([user, assistant])
        db.commit()
        return user.id, assistant.id


# --- table rules (data-model.md) ---------------------------------------------------------------


def insert_feedback(engine, message_id, **fields):
    with Session(engine) as db:
        db.add(models.Feedback(message_id=message_id, **fields))
        db.commit()


def test_one_feedback_row_per_message(engine):
    _, assistant_id = add_turn(engine)
    insert_feedback(engine, assistant_id, rating="up")

    with pytest.raises(IntegrityError):
        insert_feedback(engine, assistant_id, rating="down")


@pytest.mark.parametrize("rating", ["up", "down"])
def test_rating_accepts_up_and_down(engine, rating):
    _, assistant_id = add_turn(engine)
    insert_feedback(engine, assistant_id, rating=rating)


@pytest.mark.parametrize("rating", ["Up", "maybe", ""])
def test_rating_rejects_other_values(engine, rating):
    _, assistant_id = add_turn(engine)
    with pytest.raises(IntegrityError):
        insert_feedback(engine, assistant_id, rating=rating)


def test_reason_is_rejected_with_up_and_accepted_with_down(engine):
    _, first = add_turn(engine, "s1")
    _, second = add_turn(engine, "s2")

    with pytest.raises(IntegrityError):
        insert_feedback(engine, first, rating="up", reason="unclear")
    insert_feedback(engine, second, rating="down", reason="unclear")


@pytest.mark.parametrize("rating", ["up", "down"])
def test_null_reason_is_accepted_with_either_rating(engine, rating):
    _, assistant_id = add_turn(engine)
    insert_feedback(engine, assistant_id, rating=rating, reason=None)


def test_defaults_trace_id_null_and_timestamps_set(engine):
    _, assistant_id = add_turn(engine)
    insert_feedback(engine, assistant_id, rating="up")

    with Session(engine) as db:
        row = db.query(models.Feedback).one()
        assert row.trace_id is None
        assert row.reason is None and row.comment is None
        assert row.created_at is not None and row.updated_at is not None


def test_feedback_for_a_missing_message_is_rejected(engine):
    with pytest.raises(IntegrityError):
        insert_feedback(engine, 999, rating="up")


# --- User Story 1: rate an answer --------------------------------------------------------------

def rate(client, message_id, **body):
    return client.post(f"/api/messages/{message_id}/feedback", json=body)


def feedback_rows(engine):
    with Session(engine) as db:
        return db.query(models.Feedback).all()


@pytest.mark.parametrize("rating", ["up", "down"])
def test_rating_is_confirmed_and_stored(client, engine, rating):
    message_id = send_chat(client)

    r = rate(client, message_id, rating=rating)

    assert r.status_code == 200
    body = r.json()
    assert body["message_id"] == message_id
    assert body["rating"] == rating
    assert body["reason"] is None and body["comment"] is None and body["trace_id"] is None
    assert body["created_at"] and body["updated_at"]
    rows = feedback_rows(engine)
    assert [(row.message_id, row.rating) for row in rows] == [(message_id, rating)]


def test_feedback_on_a_mock_reply_is_accepted(client, engine):
    message_id = send_chat(client)

    assert rate(client, message_id, rating="up").status_code == 200

    with Session(engine) as db:
        message = db.get(models.Message, message_id)
        row = db.query(models.Feedback).filter_by(message_id=message_id).one()
        assert (message.role, message.source, row.rating) == ("assistant", "mock", "up")


def test_feedback_on_an_agent_reply_is_accepted(client, engine, monkeypatch):
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    monkeypatch.setattr(
        main,
        "call_agent",
        lambda url, sid, msg, **kwargs: AgentReply(reply="Sure!", intent="get_quote", latency_ms=42),
    )
    message_id = send_chat(client)

    assert rate(client, message_id, rating="down").status_code == 200

    with Session(engine) as db:
        assert db.get(models.Message, message_id).source == "agent"
        assert db.query(models.Feedback).filter_by(message_id=message_id).count() == 1


def test_history_is_unchanged_and_has_no_feedback(client):
    message_id = send_chat(client)
    before = client.get("/api/chat/s1/history").json()

    rate(client, message_id, rating="up")

    after = client.get("/api/chat/s1/history").json()
    assert after == before
    assert all(
        set(m) == {"id", "role", "content", "intent", "latency_ms", "source", "created_at"}
        for m in after["messages"]
    )


# --- User Story 2: refuse feedback that doesn't make sense -------------------------------------

ID_DETAIL = "message_id must be a positive whole number of at most 18 digits"
BODY_DETAIL = "request body must be a JSON object"
RATING_DETAIL = 'rating must be "up" or "down"'


def message_count(engine):
    with Session(engine) as db:
        return db.query(models.Message).count()


def post_raw(client, path_id, content):
    return client.post(
        f"/api/messages/{path_id}/feedback",
        content=content,
        headers={"content-type": "application/json"},
    )


def assert_refused(client, engine, response, status, detail):
    """The refusal has the documented status and detail, and nothing was written (FR-012, FR-014)."""
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert feedback_rows(engine) == []


@pytest.mark.parametrize("path_id", ["abc", "1.5", "-1", "0", "007", "1" * 19])
def test_bad_message_id_is_refused(client, engine, path_id):
    send_chat(client)
    before = message_count(engine)

    r = rate(client, path_id, rating="up")

    assert_refused(client, engine, r, 400, ID_DETAIL)
    assert message_count(engine) == before


@pytest.mark.parametrize("content", ["not json", "[]", '"up"', "null", "5", ""])
def test_body_that_is_not_a_json_object_is_refused(client, engine, content):
    message_id = send_chat(client)

    assert_refused(client, engine, post_raw(client, message_id, content), 400, BODY_DETAIL)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"rating": None},
        {"rating": ""},
        {"rating": "Up"},
        {"rating": "UP"},
        {"rating": "thumbs_up"},
        {"rating": True},
        {"rating": 5},
        {"rating": ["up"]},
    ],
)
def test_bad_rating_is_refused(client, engine, body):
    message_id = send_chat(client)

    assert_refused(client, engine, rate(client, message_id, **body), 400, RATING_DETAIL)


def test_reason_with_an_up_rating_is_refused(client, engine):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", reason="incorrect")

    assert_refused(client, engine, r, 400, 'reason is only allowed with a "down" rating')


def test_unknown_message_is_not_found(client, engine):
    send_chat(client)

    r = rate(client, 999, rating="up")

    assert_refused(client, engine, r, 404, "message not found")


def test_user_message_is_refused(client, engine):
    send_chat(client)
    before = message_count(engine)

    r = rate(client, user_message_id(client), rating="up")

    assert_refused(client, engine, r, 400, "feedback is only allowed on assistant messages")
    assert message_count(engine) == before


def test_an_invalid_body_is_refused_before_the_message_is_looked_up(client, engine):
    # No message 999 exists, but the bad rating wins: cheap checks run before the database is read.
    r = rate(client, 999, rating="Up")

    assert_refused(client, engine, r, 400, RATING_DETAIL)


def test_trace_id_in_the_body_is_ignored(client, engine):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", trace_id="abc")

    assert r.status_code == 200
    assert r.json()["trace_id"] is None
    assert [row.trace_id for row in feedback_rows(engine)] == [None]


# --- User Story 3: say why an answer was not helpful -------------------------------------------

REASON_DETAIL = "reason must be one of: incorrect, unclear, wanted_a_person, other"


@pytest.mark.parametrize("reason", feedback.REASONS)
def test_each_listed_reason_is_stored_with_a_down_rating(client, engine, reason):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="down", reason=reason)

    assert r.status_code == 200
    assert r.json()["reason"] == reason
    assert [row.reason for row in feedback_rows(engine)] == [reason]


def test_the_reason_list_matches_the_contract():
    assert feedback.REASONS == ("incorrect", "unclear", "wanted_a_person", "other")


@pytest.mark.parametrize("body", [{"rating": "down"}, {"rating": "down", "reason": None}])
def test_down_without_a_reason_is_accepted(client, engine, body):
    message_id = send_chat(client)

    r = rate(client, message_id, **body)

    assert r.status_code == 200
    assert r.json()["reason"] is None
    assert [row.reason for row in feedback_rows(engine)] == [None]


@pytest.mark.parametrize("reason", ["wrong", "", "Incorrect", 5])
def test_a_reason_outside_the_list_is_refused(client, engine, reason):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="down", reason=reason)

    assert_refused(client, engine, r, 400, REASON_DETAIL)


def test_the_reason_value_is_checked_before_the_reason_with_up_rule(client, engine):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", reason="wrong")

    assert_refused(client, engine, r, 400, REASON_DETAIL)


def test_wanted_a_person_stores_only_the_reason(client, engine):
    message_id = send_chat(client)
    with Session(engine) as db:
        before = db.query(models.Session).count(), db.query(models.Message).count()

    assert rate(client, message_id, rating="down", reason="wanted_a_person").status_code == 200

    with Session(engine) as db:
        assert (db.query(models.Session).count(), db.query(models.Message).count()) == before
    assert len(feedback_rows(engine)) == 1


# --- User Story 4: explain a rating with a comment ---------------------------------------------


@pytest.mark.parametrize("rating", ["up", "down"])
def test_a_comment_is_stored_with_either_rating(client, engine, rating):
    message_id = send_chat(client)

    r = rate(client, message_id, rating=rating, comment="Helpful, thanks")

    assert r.status_code == 200
    assert r.json()["comment"] == "Helpful, thanks"
    assert [row.comment for row in feedback_rows(engine)] == ["Helpful, thanks"]


def test_a_comment_is_stored_exactly_as_submitted(client, engine):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", comment="  spaced out  ")

    assert r.json()["comment"] == "  spaced out  "
    assert [row.comment for row in feedback_rows(engine)] == ["  spaced out  "]


@pytest.mark.parametrize("body", [{"comment": ""}, {"comment": "   "}, {"comment": None}, {}])
def test_an_empty_or_missing_comment_is_stored_as_null(client, engine, body):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", **body)

    assert r.status_code == 200
    assert r.json()["comment"] is None
    assert [row.comment for row in feedback_rows(engine)] == [None]


def test_a_comment_of_exactly_the_limit_is_accepted(client, engine):
    message_id = send_chat(client)
    comment = "x" * feedback.MAX_COMMENT_CHARS

    assert feedback.MAX_COMMENT_CHARS == 1000
    assert rate(client, message_id, rating="up", comment=comment).status_code == 200
    assert [row.comment for row in feedback_rows(engine)] == [comment]


def test_a_comment_over_the_limit_is_refused(client, engine):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", comment="x" * 1001)

    assert_refused(client, engine, r, 400, "comment must be at most 1000 characters")


@pytest.mark.parametrize("comment", [5, ["x"], {"a": 1}, True])
def test_a_comment_that_is_not_a_string_is_refused(client, engine, comment):
    message_id = send_chat(client)

    r = rate(client, message_id, rating="up", comment=comment)

    assert_refused(client, engine, r, 400, "comment must be a string")


# --- User Story 5: change a previous rating ----------------------------------------------------


def test_a_second_submission_replaces_the_first(client, engine):
    message_id = send_chat(client)
    rate(client, message_id, rating="up")

    r = rate(client, message_id, rating="down", reason="unclear", comment="confusing")

    assert r.status_code == 200
    assert (r.json()["rating"], r.json()["reason"], r.json()["comment"]) == ("down", "unclear", "confusing")
    rows = feedback_rows(engine)
    assert [(row.rating, row.reason, row.comment) for row in rows] == [("down", "unclear", "confusing")]


def test_omitting_reason_and_comment_clears_the_earlier_ones(client, engine):
    message_id = send_chat(client)
    rate(client, message_id, rating="down", reason="incorrect", comment="wrong price")

    r = rate(client, message_id, rating="down")

    assert (r.json()["reason"], r.json()["comment"]) == (None, None)
    assert [(row.reason, row.comment) for row in feedback_rows(engine)] == [(None, None)]


def test_down_with_details_then_up_leaves_a_bare_up(client, engine):
    message_id = send_chat(client)
    rate(client, message_id, rating="down", reason="other", comment="meh")

    rate(client, message_id, rating="up")

    rows = feedback_rows(engine)
    assert [(row.rating, row.reason, row.comment) for row in rows] == [("up", None, None)]


def test_submitting_identical_values_twice_changes_nothing(client, engine):
    message_id = send_chat(client)
    first = rate(client, message_id, rating="down", reason="unclear", comment="hmm")

    second = rate(client, message_id, rating="down", reason="unclear", comment="hmm")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()  # including created_at and updated_at
    assert len(feedback_rows(engine)) == 1


def test_five_submissions_leave_one_row_with_the_last_values(client, engine):
    message_id = send_chat(client)

    for i in range(5):
        rate(client, message_id, rating="down" if i % 2 else "up", comment=f"try {i}")

    rows = feedback_rows(engine)
    assert [(row.rating, row.comment) for row in rows] == [("up", "try 4")]


def test_losing_the_insert_race_still_stores_the_latest_values(client, engine, monkeypatch):
    message_id = send_chat(client)
    rate(client, message_id, rating="up")  # the "other" request got there first

    real_find = feedback.find_feedback
    calls = []

    def stale_first_lookup(db, mid):
        calls.append(mid)
        return None if len(calls) == 1 else real_find(db, mid)

    monkeypatch.setattr(feedback, "find_feedback", stale_first_lookup)

    r = rate(client, message_id, rating="down", reason="incorrect")

    assert r.status_code == 200
    assert (r.json()["rating"], r.json()["reason"]) == ("down", "incorrect")
    assert len(calls) == 2
    rows = feedback_rows(engine)
    assert [(row.rating, row.reason) for row in rows] == [("down", "incorrect")]


# --- Convergence: input the database can't store must be a 400, not a 500 ----------------------
#
# NOTE: the NUL and surrogate cases only fail on Postgres (it rejects NUL in text, and psycopg
# can't encode a lone surrogate). SQLite accepts a NUL, so for that case this test is a regression
# guard for the validation rule rather than a proof the 500 is gone. The Docker check in the
# quickstart (step 3, "Inputs the database can't store") is what proves it on Postgres.

UNSTORABLE_DETAIL = "comment must not contain null or unpaired surrogate characters"


@pytest.mark.parametrize(
    "comment_json",
    ['"a\\u0000b"', '"\\u0000"', '"a\\ud800b"', '"\\udc00"', '"\\ud83d"'],
    ids=["nul-inside", "nul-only", "high-surrogate", "low-surrogate", "half-an-emoji"],
)
def test_a_comment_the_database_cannot_store_is_refused(client, engine, comment_json):
    message_id = send_chat(client)

    r = post_raw(client, message_id, '{"rating":"up","comment":' + comment_json + "}")

    assert_refused(client, engine, r, 400, UNSTORABLE_DETAIL)


def test_a_valid_emoji_comment_is_accepted(client, engine):
    message_id = send_chat(client)

    # "\ud83d\ude00" is a valid surrogate pair: one emoji once decoded.
    r = post_raw(client, message_id, '{"rating":"up","comment":"great \\ud83d\\ude00"}')

    assert r.status_code == 200
    assert [row.comment for row in feedback_rows(engine)] == ["great \U0001f600"]


def test_the_unstorable_check_comes_after_the_type_check_and_before_the_length_check(client, engine):
    message_id = send_chat(client)

    not_a_string = post_raw(client, message_id, '{"rating":"up","comment":5}')
    too_long_and_nul = post_raw(client, message_id, '{"rating":"up","comment":"\\u0000' + "x" * 1001 + '"}')

    assert not_a_string.json() == {"detail": "comment must be a string"}
    assert too_long_and_nul.json() == {"detail": UNSTORABLE_DETAIL}
    assert feedback_rows(engine) == []


def test_a_deeply_nested_body_is_refused_not_a_server_error(client, engine):
    message_id = send_chat(client)

    r = post_raw(client, message_id, "[" * 200_000)

    assert_refused(client, engine, r, 400, BODY_DETAIL)


def test_a_body_without_a_content_type_is_accepted(client, engine):
    # The contract no longer requires a Content-Type header, matching the other endpoints.
    message_id = send_chat(client)

    r = client.post(f"/api/messages/{message_id}/feedback", content='{"rating":"up"}')

    assert r.status_code == 200
    assert [row.rating for row in feedback_rows(engine)] == ["up"]
