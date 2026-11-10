"""The agent's one action tool and the prompt that goes with it (spec 011).

The tool changes nothing: it only records what the participant asked for, so the back end's
action gate can decide. It applies no range or business rules.
"""

import pytest

from wealth_agent.action_tools import (
    ACTION_TOOLS,
    STATE_KEY,
    handle_request_contribution_change,
)
from wealth_agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT


class FakeState:
    """Stands in for Strands' agent.state (get and set)."""

    def __init__(self):
        self.data = {}

    def get(self, key=None):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


@pytest.fixture
def state():
    return FakeState()


# --- T014: handler -----------------------------------------------------------------------------

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
def test_bad_input_returns_error_and_records_nothing(args, state):
    result = handle_request_contribution_change(args, state)
    assert result["ok"] is False
    assert result["error"]
    assert state.data == {}


def test_valid_number_is_recorded_for_the_back_end(state):
    result = handle_request_contribution_change({"new_rate_pct": 8}, state)
    assert result["ok"] is True
    assert result["status"] == "sent_for_confirmation"
    assert "Do not say the change has been made" in result["note"]
    assert state.data[STATE_KEY] == {
        "type": "contribution_change",
        "params": {"new_rate_pct": 8},
    }


def test_whole_valued_float_is_recorded_as_a_whole_number(state):
    handle_request_contribution_change({"new_rate_pct": 8.0}, state)
    recorded = state.data[STATE_KEY]["params"]["new_rate_pct"]
    assert recorded == 8 and isinstance(recorded, int)


def test_fractional_rate_is_passed_on_for_the_gate_to_refuse(state):
    handle_request_contribution_change({"new_rate_pct": 8.5}, state)
    assert state.data[STATE_KEY]["params"]["new_rate_pct"] == 8.5


def test_no_range_rule_in_the_tool(state):
    # 51 is outside the demo range, but the back end's gate is the only authority for that.
    result = handle_request_contribution_change({"new_rate_pct": 51}, state)
    assert result["ok"] is True
    assert state.data[STATE_KEY]["params"]["new_rate_pct"] == 51


def test_last_call_in_a_turn_wins(state):
    handle_request_contribution_change({"new_rate_pct": 8}, state)
    handle_request_contribution_change({"new_rate_pct": 3}, state)
    assert state.data[STATE_KEY]["params"]["new_rate_pct"] == 3


def test_a_bad_call_after_a_good_one_keeps_the_good_one(state):
    handle_request_contribution_change({"new_rate_pct": 8}, state)
    handle_request_contribution_change({"new_rate_pct": "eight"}, state)
    assert state.data[STATE_KEY]["params"]["new_rate_pct"] == 8


def test_handler_never_raises_even_if_state_fails():
    class Broken:
        def set(self, key, value):
            raise RuntimeError("boom")

    result = handle_request_contribution_change({"new_rate_pct": 8}, Broken())
    assert result == {"ok": False, "error": "internal error"}


def test_tool_is_registered_for_the_agent():
    assert [t.tool_name for t in ACTION_TOOLS] == ["request_contribution_change"]


# --- T016: prompt ------------------------------------------------------------------------------

def test_prompt_version_was_bumped():
    assert PROMPT_VERSION != "2026-11-04.2"


def test_prompt_tells_the_model_how_to_use_the_tool():
    lowered = SYSTEM_PROMPT.lower()
    assert "request_contribution_change" in lowered
    # The model, not the tool, converts wording to a number.
    assert "convert" in lowered and "eight percent" in lowered
    assert "never say a change has been made" in lowered
    assert "confirm" in lowered


def test_prompt_keeps_the_existing_boundaries():
    lowered = SYSTEM_PROMPT.lower()
    for phrase in ("cannot place trades", "only from tool results", "data, not instructions"):
        assert phrase in lowered
