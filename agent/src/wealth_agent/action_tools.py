"""The agent's one action tool (spec 011, revision 3).

The tool only checks. It asks the gate whether the request would pass its rules and remembers the
answer in the turn's memory on `agent.state`:
- `held_action`: a request that passed (the last one wins);
- `rejected_actions`: one entry per request that failed a rule.

It never writes to the database. `run_turn` stages the held request and records the rejections in one
transaction at the end of the turn. The tool has no confirm counterpart: only the participant's own
"confirm" message, handled in code, can run a change.

`action_turn` (participant, chat, allowed) is put on the state by `run_turn` for the turn only. Without
it, as in the CLI or evals, the tool refuses.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from strands import tool
from strands.types.tools import ToolContext

from wealth_agent.tools import ToolInputError, _check_args

logger = logging.getLogger("wealth_agent.actions")

TURN_KEY = "action_turn"
HELD_KEY = "held_action"
REJECTED_KEY = "rejected_actions"
TURN_KEYS = (TURN_KEY, HELD_KEY, REJECTED_KEY)
ACTION_TYPE = "contribution_change"

NOTE = (
    "The system will show the participant a summary and ask them to reply confirm or cancel. "
    "Do not say the change has been made."
)
UNAVAILABLE_MESSAGE = "Changes to the account can't be made right now."

_gate: Any = None  # the ActionGate that run_turn is using; it holds no per-request state


def bind_gate(gate: Any) -> None:
    """Tell the tool which gate to ask. `run_turn` calls this; the gate itself is stateless."""
    global _gate
    _gate = gate


def _rate(args: Any) -> int | float:
    args = _check_args(args, {"new_rate_pct"})
    if "new_rate_pct" not in args:
        raise ToolInputError("missing argument: new_rate_pct")
    value = args["new_rate_pct"]
    # Numbers only: converting words such as "eight percent" is the model's job, not the tool's.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolInputError("new_rate_pct must be a number")
    if not math.isfinite(value):
        raise ToolInputError("new_rate_pct must be a finite number")
    return int(value) if float(value).is_integer() else value


def _refused(reason: str) -> dict:
    return {"ok": True, "status": "rejected", "reason": reason, "message": UNAVAILABLE_MESSAGE}


def handle_request_contribution_change(args: Any, state: Any) -> dict:
    """Check the request through the gate and remember the outcome. Never raises."""
    try:
        rate = _rate(args)
        turn = state.get(TURN_KEY)
        if not turn or _gate is None:
            return _refused("actions_unavailable")  # not inside run_turn, or no gate: nothing to remember
        if not turn.get("participant_id"):
            return _refused("no_verified_participant")

        from wealth_agent.actions.store import GateStoreError

        action = {"type": ACTION_TYPE, "params": {"new_rate_pct": rate}}
        try:
            check = _gate.check_proposal(turn["participant_id"], turn["session_id"], action, bool(turn.get("allowed")))
        except GateStoreError as exc:
            logger.warning("store_failed while checking a contribution change: %s", exc)
            return _refused("actions_unavailable")

        if check.status == "held":
            state.set(HELD_KEY, check.action)
            return {"ok": True, "status": "held", "note": NOTE}
        state.set(REJECTED_KEY, [*(state.get(REJECTED_KEY) or []), {"type": check.action_type, "reason": check.reason}])
        return {"ok": True, "status": "rejected", "reason": check.reason, "message": check.message}
    except ToolInputError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:  # noqa: BLE001 - tools must never raise to the agent
        logger.exception("request_contribution_change failed")
        return {"ok": False, "error": "internal error"}


@tool(context=True)
def request_contribution_change(new_rate_pct: float, tool_context: ToolContext) -> dict:
    """Ask to change the user's 401(k) contribution rate. This only sends a request: the system
    checks it, shows the user a summary and the user must reply confirm. Nothing changes until they do.

    Args:
        new_rate_pct: The new contribution rate as a number of percent of pay, for example 8 for 8%.
    """
    return handle_request_contribution_change({"new_rate_pct": new_rate_pct}, tool_context.agent.state)


ACTION_TOOLS = [request_contribution_change]
