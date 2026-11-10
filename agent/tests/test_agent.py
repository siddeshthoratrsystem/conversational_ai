"""Tests for disclaimer enforcement, agent wiring and model selection (FR-005, FR-006)."""

import pytest

from wealth_agent.agent import ask, build_agent
from wealth_agent.model import ModelConfigError, build_model
from wealth_agent.prompts import DISCLAIMER, PROMPT_VERSION, SYSTEM_PROMPT


class FakeAgent:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return self.reply


@pytest.mark.parametrize("reply", ["Your portfolio is worth $70,000.", "", "  spaced  "])
def test_disclaimer_always_appended(reply):
    answer = ask(FakeAgent(reply), "how much do I have?")
    assert answer.rstrip().endswith(DISCLAIMER)


def test_disclaimer_not_duplicated():
    answer = ask(FakeAgent(f"Hello.\n\n{DISCLAIMER}"), "hi")
    assert answer.count(DISCLAIMER) == 1


def test_ask_passes_user_text_through():
    agent = FakeAgent("ok")
    ask(agent, "what do I own?")
    assert agent.calls == ["what do I own?"]


def test_prompt_is_versioned_and_states_boundaries():
    assert PROMPT_VERSION
    lowered = SYSTEM_PROMPT.lower()
    for phrase in ("cannot place trades", "only from tool results", "data, not instructions"):
        assert phrase in lowered


def test_prompt_handles_greetings_without_tools():
    lowered = SYSTEM_PROMPT.lower()
    assert "greeting" in lowered
    assert "do not call tools" in lowered


def test_build_model_defaults_to_local_ollama():
    model = build_model(env={})
    config = model.get_config()
    assert type(model).__name__ == "OllamaModel"
    assert config["model_id"] == "llama3.2"
    assert config["temperature"] == 0


def test_build_model_reads_env():
    model = build_model(env={"WEALTH_AGENT_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen3:8b"})
    assert model.get_config()["model_id"] == "qwen3:8b"


def test_build_model_rejects_unknown_provider():
    with pytest.raises(ModelConfigError):
        build_model(env={"WEALTH_AGENT_PROVIDER": "bedrock"})


def test_build_agent_registers_only_read_only_tools():
    agent = build_agent(build_model(env={}), quiet=True)
    assert sorted(agent.tool_names) == [
        "get_allocation",
        "get_holdings",
        "get_rebalancing_summary",
        "project_savings",
        "request_contribution_change",
    ]
    assert agent.system_prompt == SYSTEM_PROMPT
