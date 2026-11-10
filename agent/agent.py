"""AgentCore entrypoint. Serves POST /invocations on :8080 for the backend.

Request {prompt, session_id} -> response {reply, intent} plus an optional {action} when the
agent asked to change something (the back end's action gate decides what happens, spec 011). Answers come from the local
wealth agent (Strands + Ollama, see specs/005-wealth-agent). Conversation history is kept
in-process per session_id and lost on restart.
"""

import sys
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from wealth_agent.action_tools import STATE_KEY  # noqa: E402
from wealth_agent.agent import ask, build_agent  # noqa: E402
from wealth_agent.model import build_model  # noqa: E402

app = BedrockAgentCoreApp()
_sessions = {}


def _agent_for(session_id):
    if session_id not in _sessions:
        _sessions[session_id] = build_agent(build_model(), quiet=True)
    return _sessions[session_id]


@app.entrypoint
def invoke(payload):
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id") or "default"
    agent = _agent_for(session_id)
    agent.state.delete(STATE_KEY)  # an action from an earlier turn must never carry over
    # TODO: intent classification
    response = {"reply": ask(agent, prompt), "intent": None}
    action = agent.state.get(STATE_KEY)
    if action:
        response["action"] = action
    return response


if __name__ == "__main__":
    app.run()
