"""One request through the agent, with the action gate around it (spec 011, plan "Agent: one turn").

`run_turn` is called by `agent/agent.py`. It verifies the participant's own token, answers a
confirm or cancel message in code (the model never sees it), and otherwise runs the model with a
turn context so the tool can check a request. At the end of the turn it records rejected requests
and stages a held one in a single transaction, and puts the outcome into the agent's conversation.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from wealth_agent import action_tools
from wealth_agent.action_tools import HELD_KEY, REJECTED_KEY, TURN_KEY, TURN_KEYS
from wealth_agent.actions import config
from wealth_agent.actions.gate import ActionGate, GateResult, without_footer
from wealth_agent.actions.identity import verify_participant

logger = logging.getLogger("wealth_agent.actions.turn")


def _text_block(role: str, text: str) -> dict:
    return {"role": role, "content": [{"text": text}]}


def _append_exchange(agent, message: str, reply_text: str) -> None:
    """The participant's message and the gate's text (no footer) join the conversation."""
    agent.messages.append(_text_block("user", message))
    agent.messages.append(_text_block("assistant", without_footer(reply_text)))


def _replace_final_assistant_text(agent, reply_text: str) -> None:
    """The model's last text is replaced by the gate's text (no footer): that is what the participant saw."""
    block = _text_block("assistant", without_footer(reply_text))
    if agent.messages and agent.messages[-1].get("role") == "assistant":
        agent.messages[-1] = block
    else:
        agent.messages.append(block)


def _clear_turn_memory(agent) -> None:
    for key in TURN_KEYS:
        agent.state.delete(key)


def _gate_reply(result: GateResult) -> dict:
    return {"reply": result.reply_text, "intent": None, "source": "gate"}


def run_turn(
    payload: dict,
    authorization: str | None,
    *,
    agent_for: Callable[[str | None, str], Any],
    ask: Callable[[Any, str], str],
    gate: ActionGate | None = None,
    status: config.ActionsStatus | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict:
    """Return `{"reply", "intent"}`, plus `"source": "gate"` when the gate wrote the reply."""
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id") or "default"
    verification = verify_participant(authorization)
    participant = verification.participant
    enabled = gate is not None and (status.enabled if status is not None else True)
    allowed = bool(
        enabled
        and participant is not None
        and participant.claims.get("ai_planning") is True
        and not payload.get("education_only")
    )
    # One stored agent per (participant, chat). With no verified participant: a fresh, empty agent
    # that is not stored, so no conversation is kept and two such callers can never share one.
    agent = agent_for(participant.id if participant else None, session_id)

    if enabled and participant is not None:
        reply = gate.classify(prompt)
        if reply is not None and reply.exact:
            pending = gate.find_pending(participant.id, session_id)
            if pending is None:
                result = gate.refuse_reply(participant.id, "nothing_pending", None)
            elif reply.kind == "confirm":
                result = gate.confirm(participant, pending)
            else:
                result = gate.cancel(participant, pending)
            _append_exchange(agent, prompt, result.reply_text)
            return _gate_reply(result)

    # The model turn, with the turn context the tool reads. Nothing from an earlier turn carries over.
    action_tools.bind_gate(gate if enabled else None)
    _clear_turn_memory(agent)
    agent.state.set(
        TURN_KEY,
        {"participant_id": participant.id if participant else None, "session_id": session_id, "allowed": allowed},
    )
    try:
        model_reply = ask(agent, prompt)
        held = agent.state.get(HELD_KEY)
        rejected = agent.state.get(REJECTED_KEY) or []
    finally:
        _clear_turn_memory(agent)

    if enabled and participant is not None and (held or rejected):
        if held:
            result = gate.stage(participant.id, session_id, held, rejected)
            _replace_final_assistant_text(agent, result.reply_text)
            return _gate_reply(result)
        gate.record_rejections(participant.id, rejected)
    return {"reply": model_reply, "intent": None}
