"""agent/agent.py, the AgentCore entrypoint, runs the action gate for each request (spec 011, T027).

A real Strands agent runs with a scripted stub model, so the tool call, the agent state and the
response all go through the real code. No Ollama and no server are needed.
"""

import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import ScriptedModel

from wealth_agent.actions import config
from wealth_agent.actions.gate import ActionGate

ENTRYPOINT = Path(__file__).resolve().parents[1] / "agent.py"
TOOL = ("tool", "request_contribution_change", {"new_rate_pct": 8})
FOOTER = "Demo data: no real account was changed."


def load_entrypoint():
    spec = importlib.util.spec_from_file_location("agent_entrypoint", ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def context_for(authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    return SimpleNamespace(request_headers=headers)


@pytest.fixture
def entry(monkeypatch, engine, verifier, clock, gate_store, session_row):
    def use(steps):
        module = load_entrypoint()
        model = ScriptedModel(steps)
        monkeypatch.setattr(module, "build_model", lambda: model)
        module._sessions.clear()
        gate = ActionGate(gate_store, config.load_settings({}), clock=clock)
        monkeypatch.setattr(module, "get_gate", lambda: gate)
        monkeypatch.setattr(module, "ACTIONS_STATUS", config.ActionsStatus(True, ()))
        session_row("s1")
        session_row("s2")
        return module, model

    return use


def test_invoke_passes_the_authorization_header_to_run_turn(monkeypatch):
    module = load_entrypoint()
    seen = {}

    def fake_run_turn(payload, authorization, **kwargs):
        seen.update(payload=payload, authorization=authorization, kwargs=kwargs)
        return {"reply": "ok", "intent": None}

    monkeypatch.setattr(module, "run_turn", fake_run_turn)
    monkeypatch.setattr(module, "get_gate", lambda: "the-gate")
    payload = {"prompt": "hi", "session_id": "s1"}
    result = module.invoke(payload, context_for("Bearer abc"))

    assert result == {"reply": "ok", "intent": None}
    assert seen["payload"] == payload
    assert seen["authorization"] == "Bearer abc"
    assert seen["kwargs"]["gate"] == "the-gate"
    assert callable(seen["kwargs"]["agent_for"]) and callable(seen["kwargs"]["ask"])


def test_invoke_without_a_header_passes_none(monkeypatch):
    module = load_entrypoint()
    seen = {}
    monkeypatch.setattr(module, "run_turn", lambda payload, authorization, **kw: seen.update(a=authorization) or {"reply": "ok", "intent": None})
    monkeypatch.setattr(module, "get_gate", lambda: None)
    module.invoke({"prompt": "hi", "session_id": "s1"}, context_for(None))
    module.invoke({"prompt": "hi", "session_id": "s1"}, None)
    assert seen["a"] is None


def test_a_staged_turn_returns_source_gate_and_no_action(entry, bearer):
    module, _ = entry([TOOL, ("text", "I've asked for confirmation.")])
    result = module.invoke({"prompt": "change my 401(k) contribution to 8%", "session_id": "s1"}, context_for(bearer()))
    assert result["source"] == "gate"
    assert "action" not in result
    assert "Nothing has changed yet" in result["reply"] and result["reply"].endswith(FOOTER)
    assert result["intent"] is None


def test_an_ordinary_turn_returns_reply_and_intent_only(entry, bearer):
    module, _ = entry([("text", "Diversification spreads risk.")])
    result = module.invoke({"prompt": "what is diversification?", "session_id": "s1"}, context_for(bearer()))
    assert set(result) == {"reply", "intent"}
    assert "Diversification spreads risk." in result["reply"]


def test_agent_for_gives_a_distinct_agent_for_each_participant_and_chat(entry):
    module, _ = entry([])
    a1 = module._agent_for("alice", "s1")
    assert module._agent_for("alice", "s1") is a1
    assert module._agent_for("alice", "s2") is not a1
    assert module._agent_for("bob", "s1") is not a1
    assert set(module._sessions) == {("alice", "s1"), ("alice", "s2"), ("bob", "s1")}


def test_with_no_participant_agent_for_returns_a_fresh_empty_agent_each_time(entry):
    module, _ = entry([])
    first = module._agent_for(None, "s1")
    second = module._agent_for(None, "s1")
    assert first is not second
    assert first.messages == [] and second.messages == []
    assert module._sessions == {}


def test_startup_check_runs_once_at_import(monkeypatch):
    calls = []
    real = config.startup_check
    monkeypatch.setattr(config, "startup_check", lambda *a, **kw: calls.append(1) or real(*a, **kw))
    module = load_entrypoint()
    assert len(calls) == 1
    monkeypatch.setattr(module, "run_turn", lambda *a, **kw: {"reply": "ok", "intent": None})
    monkeypatch.setattr(module, "get_gate", lambda: None)
    module.invoke({"prompt": "hi", "session_id": "s1"}, context_for(None))
    module.invoke({"prompt": "hi", "session_id": "s1"}, context_for(None))
    assert len(calls) == 1


def test_the_import_logs_the_timeout_values(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        load_entrypoint()
    assert any("AGENT_TIMEOUT_SECONDS" in r.getMessage() for r in caplog.records)
