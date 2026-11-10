"""Tables added for the action gate: constraints and the one-pending-change index (spec 011)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def _chat(db, session_id="s1", user_id="alice"):
    db.add(models.Session(id=session_id, user_id=user_id))
    db.flush()


def _pending(session_id="s1", user_id="alice", status="pending", action_type="contribution_change"):
    return models.PendingAction(
        user_id=user_id,
        session_id=session_id,
        action_type=action_type,
        params={"new_rate_pct": 8},
        snapshot={"current_rate_pct": 5},
        status=status,
        staged_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


@pytest.mark.parametrize("rate", [-1, 101])
def test_contribution_rate_outside_bounds_is_refused(engine, rate):
    with Session(engine) as db:
        db.add(models.Contribution(user_id="alice", rate_pct=rate, updated_at=NOW))
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize("rate", [0, 50, 100])
def test_contribution_rate_in_bounds_is_stored(engine, rate):
    with Session(engine) as db:
        db.add(models.Contribution(user_id="alice", rate_pct=rate, updated_at=NOW))
        db.commit()


@pytest.mark.parametrize(
    "status", ["pending", "confirmed", "executed", "cancelled", "expired", "failed"]
)
def test_pending_action_accepts_each_status(engine, status):
    with Session(engine) as db:
        _chat(db)
        db.add(_pending(status=status))
        db.commit()


def test_pending_action_rejects_unknown_status(engine):
    with Session(engine) as db:
        _chat(db)
        db.add(_pending(status="approved"))
        with pytest.raises(IntegrityError):
            db.commit()


STEPS = ["rejected", "staged", "confirmed", "cancelled", "expired", "executed", "failed"]


@pytest.mark.parametrize("step", STEPS)
def test_audit_accepts_each_step(engine, step):
    with Session(engine) as db:
        db.add(models.ActionAudit(user_id="alice", action_type="contribution_change", step=step))
        db.commit()


def test_audit_refuses_the_removed_proposed_step(engine):
    with Session(engine) as db:
        db.add(models.ActionAudit(user_id="alice", action_type="contribution_change", step="proposed"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_audit_accepts_a_rejected_row_without_a_pending_change(engine):
    with Session(engine) as db:
        db.add(models.ActionAudit(user_id="alice", action_type="contribution_change", step="rejected", reason="out_of_range"))
        db.commit()
        assert db.scalars(select(models.ActionAudit)).one().pending_action_id is None


def test_audit_rejects_unknown_step(engine):
    with Session(engine) as db:
        db.add(models.ActionAudit(user_id="alice", action_type="contribution_change", step="ran"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_audit_gets_a_time_by_default(engine):
    with Session(engine) as db:
        row = models.ActionAudit(user_id="alice", action_type="contribution_change", step="staged")
        db.add(row)
        db.commit()
        assert row.created_at is not None


def test_second_pending_change_for_same_user_and_type_is_refused(engine):
    with Session(engine) as db:
        _chat(db)
        db.add(_pending())
        db.commit()
        db.add(_pending())
        with pytest.raises(IntegrityError):
            db.commit()


def test_closed_changes_do_not_block_a_new_pending_one(engine):
    with Session(engine) as db:
        _chat(db)
        db.add(_pending(status="cancelled"))
        db.add(_pending(status="expired"))
        db.add(_pending(status="pending"))
        db.commit()


def test_pending_changes_of_different_users_or_types_coexist(engine):
    with Session(engine) as db:
        _chat(db, "s1", "alice")
        _chat(db, "s2", "bob")
        db.add(_pending(session_id="s1", user_id="alice"))
        db.add(_pending(session_id="s2", user_id="bob"))
        db.add(_pending(session_id="s1", user_id="alice", action_type="other_action"))
        db.commit()


def test_gate_is_an_allowed_message_source(engine):
    with Session(engine) as db:
        _chat(db)
        db.add(models.Message(session_id="s1", role="assistant", content="x", source="gate"))
        db.commit()


def test_other_message_sources_still_checked(engine):
    with Session(engine) as db:
        _chat(db)
        db.add(models.Message(session_id="s1", role="assistant", content="x", source="robot"))
        with pytest.raises(IntegrityError):
            db.commit()
