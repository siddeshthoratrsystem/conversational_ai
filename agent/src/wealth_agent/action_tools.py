"""The agent's one action tool (spec 011).

The tool changes nothing. It records what the participant asked for on the agent's state, and the
AgentCore entrypoint passes that to the back end as `action`. The back end's action gate applies
every rule, asks the participant to confirm, and is the only thing that can make the change. The
tool applies no range or business rules and has no confirm counterpart.
"""

from __future__ import annotations

import math
from typing import Any

from strands import tool
from strands.types.tools import ToolContext

from wealth_agent.tools import ToolInputError, _check_args

STATE_KEY = "pending_action_request"
ACTION_TYPE = "contribution_change"

NOTE = (
    "Do not say the change has been made. The system will now ask the participant to confirm "
    "it. Tell them to read the summary and reply confirm or cancel."
)


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


def handle_request_contribution_change(args: Any, state: Any) -> dict:
    """Record the request for the gate. Never raises; a bad call records nothing."""
    try:
        rate = _rate(args)
        state.set(STATE_KEY, {"type": ACTION_TYPE, "params": {"new_rate_pct": rate}})
        return {"ok": True, "status": "sent_for_confirmation", "note": NOTE}
    except ToolInputError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:  # noqa: BLE001 - tools must never raise to the agent
        return {"ok": False, "error": "internal error"}


@tool(context=True)
def request_contribution_change(new_rate_pct: float, tool_context: ToolContext) -> dict:
    """Ask to change the user's 401(k) contribution rate. This only sends a request: the system
    shows the user a summary and the user must reply confirm. Nothing changes until they do.

    Args:
        new_rate_pct: The new contribution rate as a number of percent of pay, for example 8 for 8%.
    """
    return handle_request_contribution_change(
        {"new_rate_pct": new_rate_pct}, tool_context.agent.state
    )


ACTION_TOOLS = [request_contribution_change]
