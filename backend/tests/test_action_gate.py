"""The action gate over HTTP, with a scripted agent (spec 011, US1)."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import main, models
from app.actions import contribution as c
from app.actions import gate
from app.agent import AgentReply
from tests.conftest import bearer

SESSION = "s1"
FOOTER = "Demo data: no real account was changed."


@pytest.fixture(autouse=True)
def fresh_seed():
    c.get_seed.cache_clear()
    yield
    c.get_seed.cache_clear()


@pytest.fixture
def agent(monkeypatch):
    """A scripted agent. Set `agent.action` to make the next replies carry that action."""
    monkeypatch.setenv("AGENT_URL", "http://agent.test/invocations")
    state = SimpleNamespace(
        action=None, reply="Sure, I have asked the system to confirm that.", calls=[]
    )

    def fake_call_agent(url, session_id, message, **kwargs):
        state.calls.append((session_id, message))
        return AgentReply(reply=state.reply, intent=None, latency_ms=5, action=state.action)

    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    return state


def say(client, message, session=SESSION, headers=None):
    response = client.post(
        "/api/chat", json={"session_id": session, "message": message}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["reply"]


def propose(client, agent, rate, session=SESSION):
    agent.action = {"type": "contribution_change", "params": {"new_rate_pct": rate}}
    reply = say(client, f"please change my 401(k) to {rate}%", session)
    agent.action = None
    return reply


def rate_of(engine, user="alice"):
    with Session(engine) as db:
        row = db.get(models.Contribution, user)
        return row.rate_pct if row else 5


def pending_rows(engine):
    with Session(engine) as db:
        return list(db.scalars(select(models.PendingAction)))


def audit(engine, user="alice"):
    with Session(engine) as db:
        rows = db.scalars(
            select(models.ActionAudit).where(models.ActionAudit.user_id == user).order_by(models.ActionAudit.id)
        )
        return [(r.step, r.reason) for r in rows]


# --- propose ------------------------------------------------------------------------------------

def test_proposal_shows_the_summary_and_changes_nothing(client, agent, engine):
    reply = propose(client, agent, 8)
    assert "Nothing has changed yet" in reply
    assert "5% → 8%" in reply
    assert "+$250.00" in reply
    assert "Employer match: $416.67 a month (no change)" in reply
    assert "**confirm**" in reply and "**cancel**" in reply
    assert reply.rstrip().endswith(FOOTER)
    assert "Sure, I have asked" not in reply  # the gate's message replaces the model's wording
    assert rate_of(engine) == 5
    [row] = pending_rows(engine)
    assert (row.user_id, row.session_id, row.status) == ("alice", SESSION, "pending")
    assert row.params == {"new_rate_pct": 8}
    assert audit(engine) == [("proposed", None), ("staged", None)]


def test_gate_replies_are_stored_with_source_gate_and_in_history(client, agent):
    reply = propose(client, agent, 8)
    last = client.get(f"/api/chat/{SESSION}/history").json()["messages"][-1]
    assert (last["role"], last["source"], last["content"]) == ("assistant", "gate", reply)


def test_an_ordinary_model_reply_has_no_footer_and_source_agent(client, agent):
    agent.reply = "Diversification spreads risk."
    reply = say(client, "what is diversification?")
    assert reply == "Diversification spreads risk."
    assert FOOTER not in reply
    assert client.get(f"/api/chat/{SESSION}/history").json()["messages"][-1]["source"] == "agent"


@pytest.mark.parametrize(
    "rate, text",
    [
        (51, "between 0% and 50%"),
        (5, "already 5%"),
        (8.5, "whole percentage"),
    ],
)
def test_refused_proposals_give_the_plain_reason_and_stage_nothing(client, agent, engine, rate, text):
    reply = propose(client, agent, rate)
    assert text in reply
    assert reply.rstrip().endswith(FOOTER)
    assert pending_rows(engine) == []
    assert audit(engine)[0] == ("proposed", None)
    assert audit(engine)[-1][0] == "rejected"


# --- confirm and cancel ---------------------------------------------------------------------------

def test_confirm_makes_the_change_without_calling_the_agent(client, agent, engine):
    propose(client, agent, 8)
    calls = len(agent.calls)
    reply = say(client, "confirm")
    assert "now 8%" in reply and "was 5%" in reply
    assert reply.rstrip().endswith(FOOTER)
    assert rate_of(engine) == 8
    assert len(agent.calls) == calls  # the model never sees "confirm"
    assert [step for step, _ in audit(engine)] == ["proposed", "staged", "confirmed", "executed"]
    [row] = pending_rows(engine)
    assert row.status == "executed" and row.token_used_at is not None
    assert client.get(f"/api/chat/{SESSION}/history").json()["messages"][-1]["source"] == "gate"


def test_cancel_keeps_the_rate(client, agent, engine):
    propose(client, agent, 8)
    reply = say(client, "cancel")
    assert "Cancelled" in reply and "stays at 5%" in reply
    assert reply.rstrip().endswith(FOOTER)
    assert rate_of(engine) == 5
    assert pending_rows(engine)[0].status == "cancelled"
    assert audit(engine)[-1] == ("cancelled", "participant_cancelled")


@pytest.mark.parametrize("word", ["Confirm!", "  CONFIRM.  ", '"confirm"', "confirm?", "Confirm;"])
def test_confirm_ignores_case_whitespace_and_marks(client, agent, engine, word):
    propose(client, agent, 8)
    say(client, word)
    assert rate_of(engine) == 8


@pytest.mark.parametrize("word", [" cancel. ", "CANCEL", "'cancel'"])
def test_cancel_ignores_case_whitespace_and_marks(client, agent, engine, word):
    propose(client, agent, 8)
    say(client, word)
    assert pending_rows(engine)[0].status == "cancelled"


def test_confirm_and_cancel_with_nothing_pending(client, agent, engine):
    assert "no pending change to confirm" in say(client, "confirm")
    assert "no pending change to cancel" in say(client, "cancel")
    assert agent.calls == []
    assert rate_of(engine) == 5
    assert audit(engine) == [("rejected", "nothing_pending")] * 2


# --- fallbacks ---------------------------------------------------------------------------------------

def test_mock_reply_stages_nothing_but_confirm_and_cancel_still_answer(client, engine, monkeypatch):
    monkeypatch.delenv("AGENT_URL", raising=False)
    assert say(client, "change my contribution to 8%").startswith("(mock)")
    assert pending_rows(engine) == []
    assert "no pending change to confirm" in say(client, "confirm")
    assert "no pending change to cancel" in say(client, "cancel")


def test_a_pending_change_can_be_confirmed_when_the_agent_is_down(client, agent, engine, monkeypatch):
    propose(client, agent, 8)
    monkeypatch.delenv("AGENT_URL")
    assert "now 8%" in say(client, "confirm")
    assert rate_of(engine) == 8


def test_unknown_action_type_is_refused(client, agent, engine):
    agent.action = {"type": "account_opening", "params": {}}
    reply = say(client, "open an account")
    assert "aren't available" in reply and reply.rstrip().endswith(FOOTER)
    assert pending_rows(engine) == []
    assert audit(engine) == [("proposed", None), ("rejected", "unknown_action")]


def test_missing_seed_file_is_refused(client, agent, engine, monkeypatch, tmp_path):
    monkeypatch.setattr(c, "SEED_PATH", tmp_path / "missing.json")
    c.get_seed.cache_clear()
    reply = propose(client, agent, 8)
    assert "aren't available" in reply and reply.rstrip().endswith(FOOTER)
    assert pending_rows(engine) == []
    assert audit(engine) == [("proposed", None), ("rejected", "seed_unavailable")]


# --- restart -------------------------------------------------------------------------------------------

def test_state_survives_a_restart(client, agent, engine, make_token):
    from fastapi.testclient import TestClient

    propose(client, agent, 8)
    c.get_seed.cache_clear()
    restarted = TestClient(main.app, headers=bearer(make_token()))  # same engine, nothing in memory
    assert "now 8%" in say(restarted, "confirm")
    assert rate_of(engine) == 8
    assert [step for step, _ in audit(engine)] == ["proposed", "staged", "confirmed", "executed"]
    assert "8% → 3%" in propose(restarted, agent, 3)


# --- T020: the gate is generic -----------------------------------------------------------------------

class DummyAction:
    name = "dummy_action"

    def __init__(self, log):
        self.log = log

    def parse(self, params):
        return params

    def check(self, participant_id, params):
        return {"seen": True}

    def summary(self, params, snapshot, expiry_minutes):
        return f"Dummy summary for {params['x']}"

    def execute(self, participant_id, params, snapshot, token):
        self.log.append((participant_id, params, snapshot))
        return "Dummy done"


def test_a_new_action_type_runs_through_the_unchanged_gate(client, agent, engine, monkeypatch):
    log = []
    monkeypatch.setitem(gate.ACTION_TYPES, "dummy_action", lambda ctx: DummyAction(log))

    agent.action = {"type": "dummy_action", "params": {"x": 1}}
    staged = say(client, "do the dummy thing")
    agent.action = None
    assert "Dummy summary for 1" in staged and staged.rstrip().endswith(FOOTER)
    assert pending_rows(engine)[0].action_type == "dummy_action"
    assert log == []

    done = say(client, "confirm")
    assert "Dummy done" in done and done.rstrip().endswith(FOOTER)
    assert log == [("alice", {"x": 1}, {"seen": True})]

    agent.action = {"type": "dummy_action", "params": {"x": 2}}
    say(client, "again")
    agent.action = None
    assert "Cancelled" in say(client, "cancel")
    assert len(log) == 1
    assert [step for step, _ in audit(engine)] == [
        "proposed", "staged", "confirmed", "executed", "proposed", "staged", "cancelled",
    ]


def test_the_contribution_action_works_with_another_contribution_source(client, agent, engine):
    class FakeService:
        def __init__(self):
            self.applied = []

        def current_rate(self, participant_id):
            return 20

        def apply_change(self, participant_id, new_rate_pct, token):
            self.applied.append((participant_id, new_rate_pct, bool(token.raw)))
            return new_rate_pct

    fake = FakeService()
    main.app.dependency_overrides[c.get_contribution_service] = lambda: fake
    try:
        assert "20% → 8%" in propose(client, agent, 8)
        assert "now 8%" in say(client, "confirm")
    finally:
        main.app.dependency_overrides.pop(c.get_contribution_service, None)
    assert fake.applied == [("alice", 8, True)]
    assert rate_of(engine) == 5  # the demo table was never touched
