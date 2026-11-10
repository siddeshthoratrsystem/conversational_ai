"""agent/agent.py (the AgentCore entrypoint) returns the optional `action` (spec 011).

A real Strands agent runs with a scripted stub model, so the tool call, the agent state and the
response all go through the real code. No Ollama and no server are needed.
"""

import importlib.util
import json
from pathlib import Path

import pytest
from strands.models.model import Model

ENTRYPOINT = Path(__file__).resolve().parents[1] / "agent.py"


class ScriptedModel(Model):
    """Replays a list of steps, one per model call: ("tool", name, args) or ("text", text)."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = 0

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {"model_id": "scripted"}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError
        yield  # pragma: no cover

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        step = self.steps[self.calls]
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        if step[0] == "tool":
            _, name, args = step
            yield {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": f"t{self.calls}"}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": step[1]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        }


@pytest.fixture
def entry(monkeypatch):
    spec = importlib.util.spec_from_file_location("agent_entrypoint", ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def use(steps):
        model = ScriptedModel(steps)
        monkeypatch.setattr(module, "build_model", lambda: model)
        module._sessions.clear()
        return module

    return use


TOOL = ("tool", "request_contribution_change", {"new_rate_pct": 8})


def test_turn_with_the_tool_returns_the_action(entry):
    module = entry([TOOL, ("text", "I've asked for confirmation.")])
    result = module.invoke({"prompt": "change my 401(k) contribution to 8%", "session_id": "s1"})
    assert result["action"] == {"type": "contribution_change", "params": {"new_rate_pct": 8}}
    assert result["intent"] is None
    assert "asked for confirmation" in result["reply"]


def test_turn_without_the_tool_has_no_action(entry):
    module = entry([("text", "Diversification spreads risk.")])
    result = module.invoke({"prompt": "what is diversification?", "session_id": "s1"})
    assert result.get("action") is None
    assert set(result) <= {"reply", "intent", "action"}


def test_action_from_an_earlier_turn_is_cleared(entry):
    module = entry([TOOL, ("text", "Asked."), ("text", "Hello!")])
    first = module.invoke({"prompt": "change it to 8%", "session_id": "s1"})
    second = module.invoke({"prompt": "thanks", "session_id": "s1"})
    assert first["action"]["params"] == {"new_rate_pct": 8}
    assert second.get("action") is None


def test_sessions_do_not_share_actions(entry):
    module = entry([TOOL, ("text", "Asked."), ("text", "Hello!")])
    module.invoke({"prompt": "change it to 8%", "session_id": "a"})
    other = module.invoke({"prompt": "hi", "session_id": "b"})
    assert other.get("action") is None
