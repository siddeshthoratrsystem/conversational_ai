"""The demo contribution service and the confirmation token (spec 011; moved out of the policy tests, T020)."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, select

from wealth_agent.actions import gate, store
from wealth_agent.actions.contribution_service import DemoContributionService, load_seed

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(engine):
    with engine.begin() as connection:
        yield connection


@pytest.fixture
def service(conn):
    return DemoContributionService(conn, load_seed())


def test_current_rate_is_the_seed_rate_until_a_change(service):
    assert service.current_rate("alice") == 5


def stage(conn, user="alice", session_id="s1", rate=8):
    if conn.execute(select(store.sessions).where(store.sessions.c.id == session_id)).first() is None:
        conn.execute(insert(store.sessions).values(id=session_id))
    pending_id = conn.execute(
        insert(store.pending_actions)
        .values(
            user_id=user,
            session_id=session_id,
            action_type="contribution_change",
            params={"new_rate_pct": rate},
            snapshot={"current_rate_pct": 5},
            status="confirmed",
            staged_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
        .returning(store.pending_actions.c.id)
    ).scalar_one()
    return pending_id


def rate_row(conn, user):
    return conn.execute(select(store.contributions).where(store.contributions.c.user_id == user)).first()


def test_valid_token_applies_the_change(conn, service):
    token = gate.issue_token(conn, stage(conn), "alice", "s1")
    assert service.apply_change("alice", 8, token) == 8
    assert service.current_rate("alice") == 8
    assert rate_row(conn, "alice").rate_pct == 8


def test_reused_token_is_refused_and_the_rate_changes_once(conn, service):
    token = gate.issue_token(conn, stage(conn), "alice", "s1")
    service.apply_change("alice", 8, token)
    with pytest.raises(gate.GateRefusal) as refused:
        service.apply_change("alice", 9, token)
    assert refused.value.reason == "already_handled"
    assert service.current_rate("alice") == 8


def test_token_for_another_participant_is_refused(conn, service):
    token = gate.issue_token(conn, stage(conn, user="alice"), "alice", "s1")
    with pytest.raises(gate.GateRefusal) as refused:
        service.apply_change("bob", 8, token)
    assert refused.value.reason == "token_invalid"
    assert rate_row(conn, "bob") is None
    assert rate_row(conn, "alice") is None


def test_a_wrong_token_is_refused(conn, service):
    pending_id = stage(conn)
    gate.issue_token(conn, pending_id, "alice", "s1")
    forged = gate.ConfirmationToken("forged", pending_id, "alice", "s1")
    with pytest.raises(gate.GateRefusal) as refused:
        service.apply_change("alice", 8, forged)
    assert refused.value.reason == "token_invalid"
    assert rate_row(conn, "alice") is None


def test_only_the_hash_of_the_token_is_stored(conn):
    pending_id = stage(conn)
    token = gate.issue_token(conn, pending_id, "alice", "s1")
    row = conn.execute(select(store.pending_actions).where(store.pending_actions.c.id == pending_id)).one()
    assert row.token_hash == hashlib.sha256(token.raw.encode()).hexdigest()
    assert token.raw not in {str(v) for v in row}
    assert len(token.raw) >= 32


def test_each_participants_rate_is_their_own(conn, service):
    service.apply_change("alice", 8, gate.issue_token(conn, stage(conn, "alice", "s1"), "alice", "s1"))
    assert service.current_rate("alice") == 8
    assert service.current_rate("bob") == 5


def test_a_rate_that_is_not_whole_is_refused_before_the_token_is_used(conn, service):
    token = gate.issue_token(conn, stage(conn), "alice", "s1")
    with pytest.raises(ValueError):
        service.apply_change("alice", 8.5, token)
    assert service.apply_change("alice", 8, token) == 8  # the token was still unused
