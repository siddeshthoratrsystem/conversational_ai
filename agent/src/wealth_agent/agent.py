"""Agent construction and the single entry point used by the CLI, evals and (later) AgentCore."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from strands import Agent
from strands.models.model import Model

from wealth_agent.action_tools import ACTION_TOOLS
from wealth_agent.prompts import DISCLAIMER, SYSTEM_PROMPT
from wealth_agent.tools import STRANDS_TOOLS


def build_agent(model: Model, quiet: bool = False) -> Agent:
    """Create the agent. `quiet=True` disables Strands' default streaming to stdout."""
    kwargs: dict[str, Any] = {"callback_handler": None} if quiet else {}
    return Agent(model=model, tools=[*STRANDS_TOOLS, *ACTION_TOOLS], system_prompt=SYSTEM_PROMPT, **kwargs)


def ask(agent: Callable[[str], Any], text: str) -> str:
    """Run one turn and append the disclaimer in code (FR-005)."""
    answer = str(agent(text)).strip()
    if answer.endswith(DISCLAIMER):
        return answer
    return f"{answer}\n\n{DISCLAIMER}" if answer else DISCLAIMER
