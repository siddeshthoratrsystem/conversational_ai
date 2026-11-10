"""AgentCore entrypoint. Serves POST /invocations on :8080 for the backend.

Request {prompt, session_id} -> response {reply, intent}, plus "source": "gate" when the action gate
wrote the reply (spec 011). The request's `Authorization: Bearer` header carries the participant's own
token; the agent verifies it and runs the gate in `wealth_agent.actions.turn.run_turn`. Answers come
from the local wealth agent (Strands + Ollama, see specs/005-wealth-agent). Conversation history is
kept in-process per (participant, session_id) and lost on restart.
"""

import logging
import sys
from functools import lru_cache
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from wealth_agent.actions import config  # noqa: E402
from wealth_agent.actions.turn import run_turn  # noqa: E402
from wealth_agent.agent import ask, build_agent  # noqa: E402
from wealth_agent.model import build_model  # noqa: E402

logging.basicConfig(format="%(levelname)s [%(name)s] %(message)s")  # no-op if logging is already set up

app = BedrockAgentCoreApp()
_sessions = {}
ACTIONS_STATUS = config.startup_check()  # once, at import: logs the timeout values and any problem


@lru_cache
def get_gate():
    """The action gate, or None when actions are off (settings missing). Built on first use."""
    if not ACTIONS_STATUS.enabled:
        return None
    from wealth_agent.actions.gate import ActionGate
    from wealth_agent.actions.store import get_store

    return ActionGate(get_store(), config.load_settings())


def _agent_for(participant_id, session_id):
    """One stored agent per (participant, chat). With no participant, a fresh empty agent each time,
    never stored, so two token-less callers can't share a conversation."""
    if participant_id is None:
        return build_agent(build_model(), quiet=True)
    key = (participant_id, session_id)
    if key not in _sessions:
        _sessions[key] = build_agent(build_model(), quiet=True)
    return _sessions[key]


def _authorization(context):
    headers = getattr(context, "request_headers", None) or {}
    for name, value in headers.items():
        if name.lower() == "authorization":
            return value
    return None


@app.entrypoint
def invoke(payload, context=None):
    # TODO: intent classification
    return run_turn(
        payload,
        _authorization(context),
        agent_for=_agent_for,
        ask=ask,
        gate=get_gate(),
        status=ACTIONS_STATUS,
    )


if __name__ == "__main__":
    app.run()
