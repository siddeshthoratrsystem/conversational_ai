"""The agent's one action tool and the prompt that goes with it (spec 011, US1, T026).

The tool only checks: it asks the gate whether the request would pass, remembers a passing request
in the turn's memory (`held_action`) and any failing one (`rejected_actions`), and writes nothing.
`run_turn` stages and records at the end of the turn.
"""

import pytest
from sqlalchemy import func, select

from wealth_agent import action_tools
from wealth_agent.action_tools import (
    ACTION_TOOLS,
    HELD_KEY,
    REJECTED_KEY,
    TURN_KEY,
    handle_request_contribution_change,
)
from wealth_agent.actions import config, store
from wealth_agent.actions.gate import ActionGate
from wealth_agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT


class FakeState:
    """Stands in for Strands' agent.state (get, set and delete)."""

    def __init__(self):
        self.data = {}

    def get(self, key=None):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


@pytest.fixture
def state():
    return FakeState()


@pytest.fixture
def gate(gate_store, clock):
    g = ActionGate(gate_store, config.load_settings({}), clock=clock)
    action_tools.bind_gate(g)
    yield g
    action_tools.bind_gate(None)


def in_turn(state, participant="alice", session="s1", allowed=True):
    state.set(TURN_KEY, {"participant_id": participant, "session_id": session, "allowed": allowed})
    return state


def table_counts(engine):
    with engine.connect() as conn:
        return {
            t.name: conn.execute(select(func.count()).select_from(t)).scalar_one()
            for t in (store.contributions, store.pending_actions, store.action_audit)
        }


# --- the argument cases -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"new_rate_pct": None},
        {"new_rate_pct": True},
        {"new_rate_pct": float("nan")},
        {"new_rate_pct": float("inf")},
        {"new_rate_pct": "8%"},
        {"new_rate_pct": "eight"},
        {"new_rate_pct": "eight percent"},
        {"new_rate_pct": 8, "extra": 1},
        "8",
        None,
    ],
)
def test_bad_input_returns_error_and_remembers_nothing(args, state, gate, engine):
    in_turn(state)
    result = handle_request_contribution_change(args, state)
    assert result["ok"] is False
    assert result["error"]
    assert HELD_KEY not in state.data and REJECTED_KEY not in state.data
    assert table_counts(engine) == {"contributions": 0, "pending_actions": 0, "action_audit": 0}


# --- a valid number ------------------------------------------------------------------------------------


def test_a_passing_request_is_held_in_turn_memory(state, gate, engine):
    in_turn(state)
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert result["ok"] is True and result["status"] == "held"
    assert "summary" in result["note"].lower()
    assert "Do not say the change has been made" in result["note"]
    assert state.data[HELD_KEY] == {"type": "contribution_change", "params": {"new_rate_pct": 8}}
    assert REJECTED_KEY not in state.data
    assert table_counts(engine) == {"contributions": 0, "pending_actions": 0, "action_audit": 0}


def test_a_whole_valued_float_is_held_as_a_whole_number(state, gate):
    in_turn(state)
    handle_request_contribution_change({"new_rate_pct": 8.0}, state)
    held = state.data[HELD_KEY]["params"]["new_rate_pct"]
    assert held == 8 and isinstance(held, int)


@pytest.mark.parametrize(
    "rate, reason, text",
    [
        (51, "out_of_range", "between 0% and 50%"),
        (-1, "out_of_range", "between 0% and 50%"),
        (5, "same_as_current", "already 5%"),
        (8.5, "not_whole_pct", "whole percentage"),
    ],
)
def test_a_failing_request_is_rejected_and_remembered_for_recording(state, gate, engine, rate, reason, text):
    in_turn(state)
    result = handle_request_contribution_change({"new_rate_pct": rate}, state)
    assert result["ok"] is True and result["status"] == "rejected"
    assert result["reason"] == reason
    assert text in result["message"]
    assert state.data[REJECTED_KEY] == [{"type": "contribution_change", "reason": reason}]
    assert HELD_KEY not in state.data
    assert table_counts(engine) == {"contributions": 0, "pending_actions": 0, "action_audit": 0}


def test_two_rejections_in_one_turn_are_both_remembered(state, gate):
    in_turn(state)
    handle_request_contribution_change({"new_rate_pct": 51}, state)
    handle_request_contribution_change({"new_rate_pct": 5}, state)
    assert [r["reason"] for r in state.data[REJECTED_KEY]] == ["out_of_range", "same_as_current"]


def test_when_not_allowed_the_request_is_rejected_education_only(state, gate, engine):
    in_turn(state, allowed=False)
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert (result["status"], result["reason"]) == ("rejected", "education_only")
    assert state.data[REJECTED_KEY] == [{"type": "contribution_change", "reason": "education_only"}]
    assert HELD_KEY not in state.data
    assert table_counts(engine)["action_audit"] == 0


def test_without_a_turn_context_the_tool_refuses_and_remembers_nothing(state, gate):
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert (result["ok"], result["status"], result["reason"]) == (True, "rejected", "actions_unavailable")
    assert result["message"]
    assert state.data == {}


def test_without_a_verified_participant_the_tool_refuses_and_remembers_nothing(state, gate):
    in_turn(state, participant=None)
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert (result["status"], result["reason"]) == ("rejected", "no_verified_participant")
    assert HELD_KEY not in state.data and REJECTED_KEY not in state.data


def test_without_a_bound_gate_the_tool_refuses(state):
    action_tools.bind_gate(None)
    in_turn(state)
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert (result["status"], result["reason"]) == ("rejected", "actions_unavailable")
    assert HELD_KEY not in state.data


def test_when_the_store_fails_the_tool_refuses_and_remembers_nothing(state, gate, switch):
    in_turn(state)
    switch.fail("error")
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert (result["status"], result["reason"]) == ("rejected", "actions_unavailable")
    assert HELD_KEY not in state.data and REJECTED_KEY not in state.data


def test_the_last_held_call_wins(state, gate):
    in_turn(state)
    handle_request_contribution_change({"new_rate_pct": 8}, state)
    handle_request_contribution_change({"new_rate_pct": 3}, state)
    assert state.data[HELD_KEY]["params"]["new_rate_pct"] == 3


def test_a_bad_call_after_a_held_one_keeps_the_held_one(state, gate):
    in_turn(state)
    handle_request_contribution_change({"new_rate_pct": 8}, state)
    handle_request_contribution_change({"new_rate_pct": "eight"}, state)
    assert state.data[HELD_KEY]["params"]["new_rate_pct"] == 8


def test_the_tool_never_raises_even_if_state_fails(gate):
    class Broken:
        def get(self, key=None):
            return {"participant_id": "alice", "session_id": "s1", "allowed": True}

        def set(self, key, value):
            raise RuntimeError("boom")

    result = handle_request_contribution_change({"new_rate_pct": 8}, Broken())
    assert result == {"ok": False, "error": "internal error"}


def test_the_tool_is_registered_for_the_agent():
    assert [t.tool_name for t in ACTION_TOOLS] == ["request_contribution_change"]


def test_the_tool_never_writes_to_the_gate_tables(state, gate, engine):
    in_turn(state)
    for rate in (8, 51, 5, 8.5, 3):
        handle_request_contribution_change({"new_rate_pct": rate}, state)
        assert table_counts(engine) == {"contributions": 0, "pending_actions": 0, "action_audit": 0}


# --- the prompt ------------------------------------------------------------------------------------------


def test_prompt_version_was_bumped():
    assert PROMPT_VERSION != "2026-11-10.1"


def test_prompt_tells_the_model_how_to_use_the_tool():
    lowered = SYSTEM_PROMPT.lower()
    assert "request_contribution_change" in lowered
    # The model, not the tool, converts wording to a number.
    assert "convert" in lowered and "eight percent" in lowered
    assert "never say a change has been made" in lowered


def test_prompt_explains_the_held_and_rejected_results():
    lowered = SYSTEM_PROMPT.lower()
    assert "rejected" in lowered and "message" in lowered  # explain a rejected result using its message
    assert "held" in lowered and "summary" in lowered  # say the system will show a summary
    assert "never confirm" in lowered  # never confirm for the participant
    assert "same value" in lowered or "do not retry" in lowered


def test_prompt_keeps_the_existing_boundaries():
    lowered = SYSTEM_PROMPT.lower()
    for phrase in ("cannot place trades", "only from tool results", "data, not instructions"):
        assert phrase in lowered
