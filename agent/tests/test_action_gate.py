"""The action gate through `run_turn`, with signed tokens, a real store and a scripted model.

Ported from the revision 1 back-end tests (spec 011, revision 3). Each turn goes through
`wealth_agent.actions.turn.run_turn` exactly as the AgentCore entrypoint calls it.
"""

import json

import pytest
from conftest import ScriptedModel
from sqlalchemy import select
from strands.models.model import Model

from wealth_agent import action_tools
from wealth_agent.actions import config, contribution_service, policies, store
from wealth_agent.actions.gate import ActionGate
from wealth_agent.actions.turn import run_turn
from wealth_agent.agent import ask, build_agent

SESSION = "s1"
FOOTER = "Demo data: no real account was changed."
TOOL8 = ("tool", "request_contribution_change", {"new_rate_pct": 8})


def tool(rate):
    return ("tool", "request_contribution_change", {"new_rate_pct": rate})


class Rig:
    """Everything `run_turn` needs: a gate over the store, stored agents and a scripted model."""

    def __init__(self, engine, gate_store, clock, monotonic, bearer, contributions_for=None):
        self.engine, self.clock, self.monotonic, self.bearer = engine, clock, monotonic, bearer
        self.gate = ActionGate(gate_store, config.load_settings({}), contributions_for=contributions_for, clock=clock)
        self.status = config.ActionsStatus(True, ())
        self.model = ScriptedModel([])
        self.agents = {}
        rig = self

        class Delegate(Model):  # every agent talks to whichever scripted model the current turn set
            def update_config(self, **kw):
                pass

            def get_config(self):
                return {"model_id": "delegate"}

            async def structured_output(self, *a, **kw):
                raise NotImplementedError
                yield  # pragma: no cover

            async def stream(self, *a, **kw):
                async for event in rig.model.stream(*a, **kw):
                    yield event

        self._delegate = Delegate()

    def agent_for(self, participant_id, session_id):
        if participant_id is None:
            return build_agent(self._delegate, quiet=True)
        key = (participant_id, session_id)
        if key not in self.agents:
            self.agents[key] = build_agent(self._delegate, quiet=True)
        return self.agents[key]

    def turn(self, message, steps=(), user="alice", session=SESSION, authorization="default", **payload):
        self.model = ScriptedModel(steps)
        if authorization == "default":
            authorization = self.bearer(user)
        body = {"prompt": message, "session_id": session, **payload}
        return run_turn(
            body,
            authorization,
            agent_for=self.agent_for,
            ask=ask,
            gate=self.gate,
            status=self.status,
            monotonic=self.monotonic,
        )

    def propose(self, rate, user="alice", session=SESSION, text="I've asked the system to confirm that."):
        return self.turn(f"please change my 401(k) to {rate}%", [tool(rate), ("text", text)], user, session)

    def messages_of(self, user="alice", session=SESSION):
        return self.agents[(user, session)].messages


@pytest.fixture(autouse=True)
def fresh_seed(monkeypatch):
    contribution_service.get_seed.cache_clear()
    monkeypatch.setattr(action_tools, "ACTION_TYPE", "contribution_change")
    yield
    contribution_service.get_seed.cache_clear()
    action_tools.bind_gate(None)


@pytest.fixture
def rig(engine, verifier, clock, monotonic, gate_store, session_row, bearer):
    session_row(SESSION)
    session_row("s2")
    return Rig(engine, gate_store, clock, monotonic, bearer)


def rate_of(engine, user="alice"):
    with engine.connect() as conn:
        row = conn.execute(select(store.contributions).where(store.contributions.c.user_id == user)).first()
    return row.rate_pct if row else 5


def pending_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(store.pending_actions).order_by(store.pending_actions.c.id)).all()


def audit(engine, user="alice"):
    with engine.connect() as conn:
        rows = conn.execute(
            select(store.action_audit).where(store.action_audit.c.user_id == user).order_by(store.action_audit.c.id)
        ).all()
    return [(r.step, r.reason) for r in rows]


def audit_rows(engine):
    with engine.connect() as conn:
        return conn.execute(select(store.action_audit).order_by(store.action_audit.c.id)).all()


# --- propose -----------------------------------------------------------------------------------------------


def test_proposal_shows_the_summary_and_changes_nothing(rig, engine):
    result = rig.propose(8)
    reply = result["reply"]
    assert result["source"] == "gate"
    assert "Nothing has changed yet" in reply
    assert "5% → 8%" in reply
    assert "+$250.00" in reply
    assert "Employer match: $416.67 a month (no change)" in reply
    assert "**confirm**" in reply and "**cancel**" in reply
    assert reply.rstrip().endswith(FOOTER)
    assert "I've asked the system" not in reply  # the gate's message replaces the model's wording
    assert rate_of(engine) == 5
    [row] = pending_rows(engine)
    assert (row.user_id, row.session_id, row.status) == ("alice", SESSION, "pending")
    assert row.params == {"new_rate_pct": 8}
    assert audit(engine) == [("staged", None)]


def test_an_ordinary_model_reply_has_no_footer_and_no_source(rig):
    result = rig.turn("what is diversification?", [("text", "Diversification spreads risk.")])
    assert "Diversification spreads risk." in result["reply"]
    assert FOOTER not in result["reply"]
    assert "source" not in result
    assert result["intent"] is None


@pytest.mark.parametrize(
    "rate, reason, text",
    [
        (51, "out_of_range", "between 0% and 50%"),
        (5, "same_as_current", "already 5%"),
        (8.5, "not_whole_pct", "whole percentage"),
    ],
)
def test_a_rejected_rate_goes_back_to_the_model_and_is_recorded_at_the_end_of_the_turn(rig, engine, rate, reason, text):
    result = rig.turn("change it", [tool(rate), ("text", "That rate isn't allowed.")])
    assert "That rate isn't allowed." in result["reply"]
    assert FOOTER not in result["reply"] and "source" not in result
    # the reason reached the model as a tool result
    assert text in json.dumps(rig.model.seen_messages[-1])
    assert pending_rows(engine) == []
    assert audit(engine) == [("rejected", reason)]
    assert [r.pending_action_id for r in audit_rows(engine)] == [None]
    assert rate_of(engine) == 5


# --- confirm and cancel -----------------------------------------------------------------------------------------


def test_confirm_makes_the_change_without_calling_the_model(rig, engine):
    rig.propose(8)
    result = rig.turn("confirm")
    reply = result["reply"]
    assert "now 8%" in reply and "was 5%" in reply
    assert reply.rstrip().endswith(FOOTER)
    assert result["source"] == "gate"
    assert rig.model.called is False  # the model never sees "confirm"
    assert rate_of(engine) == 8
    assert [step for step, _ in audit(engine)] == ["staged", "confirmed", "executed"]
    [row] = pending_rows(engine)
    assert row.status == "executed" and row.token_used_at is not None


def test_cancel_keeps_the_rate(rig, engine):
    rig.propose(8)
    result = rig.turn("cancel")
    assert "Cancelled" in result["reply"] and "stays at 5%" in result["reply"]
    assert result["reply"].rstrip().endswith(FOOTER)
    assert result["source"] == "gate"
    assert rig.model.called is False
    assert rate_of(engine) == 5
    assert pending_rows(engine)[0].status == "cancelled"
    assert audit(engine)[-1] == ("cancelled", "participant_cancelled")


@pytest.mark.parametrize("word", ["Confirm!", "  CONFIRM.  ", '"confirm"', "confirm?", "Confirm;"])
def test_confirm_ignores_case_whitespace_and_marks(rig, engine, word):
    rig.propose(8)
    rig.turn(word)
    assert rate_of(engine) == 8


@pytest.mark.parametrize("word", [" cancel. ", "CANCEL", "'cancel'"])
def test_cancel_ignores_case_whitespace_and_marks(rig, engine, word):
    rig.propose(8)
    rig.turn(word)
    assert pending_rows(engine)[0].status == "cancelled"
    assert rate_of(engine) == 5


@pytest.mark.parametrize("word", ["confirm", "cancel"])
def test_confirm_and_cancel_with_nothing_pending(rig, engine, word):
    result = rig.turn(word)
    assert result["reply"] == f"There is no change waiting for confirmation.\n\n{FOOTER}"
    assert result["source"] == "gate"
    assert rig.model.called is False
    assert rate_of(engine) == 5
    assert audit(engine) == [("rejected", "nothing_pending")]
    assert [r.pending_action_id for r in audit_rows(engine)] == [None]


# --- unavailable policies --------------------------------------------------------------------------------------


def test_an_unknown_policy_name_reaches_the_model_as_rejected_and_is_recorded(rig, engine, monkeypatch):
    monkeypatch.setattr(action_tools, "ACTION_TYPE", "account_opening")
    result = rig.turn("open an account", [tool(8), ("text", "I can't do that.")])
    assert "I can't do that." in result["reply"] and "source" not in result
    assert "aren't available" in json.dumps(rig.model.seen_messages[-1])
    assert pending_rows(engine) == []
    assert audit(engine) == [("rejected", "unknown_action")]


def test_a_missing_seed_file_reaches_the_model_as_rejected_and_is_recorded(rig, engine, monkeypatch, tmp_path):
    monkeypatch.setattr(contribution_service, "SEED_PATH", tmp_path / "missing.json")
    contribution_service.get_seed.cache_clear()
    result = rig.turn("change it", [tool(8), ("text", "Sorry, not available.")])
    assert "Sorry, not available." in result["reply"] and "source" not in result
    assert "aren't available" in json.dumps(rig.model.seen_messages[-1])
    assert pending_rows(engine) == []
    assert audit(engine) == [("rejected", "seed_unavailable")]


# --- restart ---------------------------------------------------------------------------------------------------


def test_state_survives_a_restart(rig, engine, gate_store, clock, monotonic, bearer):
    rig.propose(8)
    contribution_service.get_seed.cache_clear()
    restarted = Rig(engine, gate_store, clock, monotonic, bearer)  # a new gate and new agents; same database
    assert "now 8%" in restarted.turn("confirm")["reply"]
    assert rate_of(engine) == 8
    assert [step for step, _ in audit(engine)] == ["staged", "confirmed", "executed"]
    assert "8% → 3%" in restarted.propose(3)["reply"]


# --- the gate is generic (FR-002, FR-021) ---------------------------------------------------------------------------


class DummyPolicy:
    name = "dummy_action"

    def __init__(self, log):
        self.log = log

    def parse(self, params):
        return params

    def check(self, participant_id, params):
        return {"seen": True}

    def summary(self, params, snapshot, expiry_minutes):
        return f"Dummy summary for {params['new_rate_pct']}"

    def execute(self, participant_id, params, snapshot, token):
        self.log.append((participant_id, params, snapshot))
        return "Dummy done"


def test_a_new_policy_runs_through_the_unchanged_gate(rig, engine, monkeypatch):
    log = []
    monkeypatch.setitem(policies.POLICIES, "dummy_action", lambda ctx: DummyPolicy(log))
    monkeypatch.setattr(action_tools, "ACTION_TYPE", "dummy_action")

    staged = rig.turn("do the dummy thing", [tool(1), ("text", "Asked.")])["reply"]
    assert "Dummy summary for 1" in staged and staged.rstrip().endswith(FOOTER)
    assert pending_rows(engine)[0].action_type == "dummy_action"
    assert log == []

    done = rig.turn("confirm")["reply"]
    assert "Dummy done" in done and done.rstrip().endswith(FOOTER)
    assert log == [("alice", {"new_rate_pct": 1}, {"seen": True})]

    rig.turn("again", [tool(2), ("text", "Asked.")])
    assert "Cancelled" in rig.turn("cancel")["reply"]
    assert len(log) == 1
    assert [step for step, _ in audit(engine)] == ["staged", "confirmed", "executed", "staged", "cancelled"]


def test_the_contribution_policy_works_with_another_contribution_source(
    engine, gate_store, clock, monotonic, bearer, verifier, session_row
):
    class FakeService:
        def __init__(self):
            self.applied = []

        def current_rate(self, participant_id):
            return 20

        def apply_change(self, participant_id, new_rate_pct, token):
            self.applied.append((participant_id, new_rate_pct, bool(token.raw)))
            return new_rate_pct

    fake = FakeService()
    session_row(SESSION)
    rig = Rig(engine, gate_store, clock, monotonic, bearer, contributions_for=lambda conn: fake)
    assert "20% → 8%" in rig.propose(8)["reply"]
    assert "now 8%" in rig.turn("confirm")["reply"]
    assert fake.applied == [("alice", 8, True)]
    assert rate_of(engine) == 5  # the demo table was never touched


# --- the conversation (FR-013, research R19) -----------------------------------------------------------------


def text_of(message):
    return " ".join(block.get("text", "") for block in message["content"] if "text" in block)


def test_after_a_staged_turn_the_final_assistant_message_is_the_summary_without_the_footer(rig):
    reply = rig.propose(8)["reply"]
    last = rig.messages_of()[-1]
    assert last["role"] == "assistant"
    assert "Nothing has changed yet" in text_of(last)
    assert FOOTER not in text_of(last)
    assert text_of(last) == reply.removesuffix(f"\n\n{FOOTER}")
    assert "I've asked the system" not in text_of(last)


@pytest.mark.parametrize("word, expected", [("confirm", "now 8%"), ("cancel", "stays at 5%")])
def test_after_confirm_or_cancel_the_conversation_ends_with_the_message_and_the_result(rig, word, expected):
    rig.propose(8)
    rig.turn(word)
    user, assistant = rig.messages_of()[-2:]
    assert (user["role"], text_of(user)) == ("user", word)
    assert assistant["role"] == "assistant"
    assert expected in text_of(assistant)
    assert FOOTER not in text_of(assistant)


def test_after_the_nothing_pending_reply_the_conversation_has_the_message_and_the_reply(rig):
    rig.turn("confirm")
    user, assistant = rig.messages_of()[-2:]
    assert text_of(user) == "confirm"
    assert text_of(assistant) == "There is no change waiting for confirmation."


def test_neither_the_token_nor_the_footer_is_in_the_conversation(rig, bearer, monkeypatch):
    header = bearer("alice")
    rig.turn("please change my 401(k) to 8%", [TOOL8, ("text", "Asked.")], authorization=header)
    rig.turn("confirm", authorization=header)
    dumped = json.dumps(rig.messages_of())
    assert FOOTER not in dumped
    assert header.removeprefix("Bearer ") not in dumped
    # nor the one-time confirmation token
    with rig.engine.connect() as conn:
        token_hash = conn.execute(select(store.pending_actions.c.token_hash)).scalar_one()
    assert token_hash and token_hash not in dumped


def test_a_later_question_reaches_the_model_with_the_confirmed_result_and_no_pending(rig):
    rig.propose(8)
    rig.turn("confirm")
    rig.turn("what's my contribution now?", [("text", "It's 8%.")])
    seen = json.dumps(rig.model.seen_messages[0])
    assert "now 8%" in seen
    assert "pending" not in seen.lower()
    assert "Nothing has changed yet" in seen  # the summary the participant saw is the record too
