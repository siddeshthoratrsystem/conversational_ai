"""Gate settings, the message footer and the audit helper (spec 011)."""

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import models
from app.actions import gate

FOOTER = "Demo data: no real account was changed."


# --- settings --------------------------------------------------------------------------------

def test_settings_defaults():
    s = gate.load_settings({})
    assert s.expiry_seconds == 300
    assert s.confirm_replies == ("confirm",)
    assert s.cancel_replies == ("cancel",)
    assert (s.min_pct, s.max_pct) == (0, 50)
    assert s.whole_pct_only is True


def test_settings_read_the_environment():
    s = gate.load_settings(
        {
            "ACTION_EXPIRY_SECONDS": "10",
            "ACTION_CONFIRM_REPLIES": "confirm, yes",
            "ACTION_CANCEL_REPLIES": "cancel,stop",
            "CONTRIBUTION_MIN_PCT": "1",
            "CONTRIBUTION_MAX_PCT": "30",
            "CONTRIBUTION_WHOLE_PCT_ONLY": "false",
        }
    )
    assert s.expiry_seconds == 10
    assert s.confirm_replies == ("confirm", "yes")
    assert s.cancel_replies == ("cancel", "stop")
    assert (s.min_pct, s.max_pct) == (1, 30)
    assert s.whole_pct_only is False


def test_settings_ignore_blank_values():
    s = gate.load_settings({"ACTION_EXPIRY_SECONDS": "", "ACTION_CONFIRM_REPLIES": " "})
    assert s.expiry_seconds == 300
    assert s.confirm_replies == ("confirm",)


# --- footer ----------------------------------------------------------------------------------

def test_footer_is_the_last_line_after_a_blank_line():
    out = gate.with_footer("Done.")
    assert out == f"Done.\n\n{FOOTER}"
    assert out.splitlines()[-1] == FOOTER


def test_footer_added_once_even_if_applied_twice():
    out = gate.with_footer(gate.with_footer("Done."))
    assert out.count(FOOTER) == 1
    assert out.endswith(FOOTER)


# --- audit helper ----------------------------------------------------------------------------

def test_audit_helper_inserts_one_row_with_only_permitted_columns(engine):
    with Session(engine) as db:
        gate.record_audit(db, "alice", "contribution_change", "rejected", reason="out_of_range")
        db.commit()
        rows = db.scalars(select(models.ActionAudit)).all()
        assert len(rows) == 1
        row = rows[0]
        assert (row.user_id, row.action_type, row.step, row.reason) == (
            "alice",
            "contribution_change",
            "rejected",
            "out_of_range",
        )
        assert row.pending_action_id is None
        assert row.created_at is not None
    columns = {c["name"] for c in inspect(engine).get_columns("action_audit")}
    assert columns == {"id", "user_id", "action_type", "pending_action_id", "step", "reason", "created_at"}
