import time
from dataclasses import dataclass

import httpx

AGENT_TIMEOUT_SECONDS = 10


class AgentError(Exception):
    """The agent call failed or returned something unusable."""


@dataclass
class AgentReply:
    reply: str
    intent: str | None
    latency_ms: int


def call_agent(url: str, session_id: str, message: str, education_only: bool = False) -> AgentReply:
    """POST {prompt, session_id} to the agent and parse {reply, intent}. Raises AgentError on any failure.

    With education_only (spec 009), the body also carries "education_only": true; otherwise it is unchanged.
    """
    body = {"prompt": message, "session_id": session_id}
    if education_only:
        body["education_only"] = True
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=AGENT_TIMEOUT_SECONDS) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:  # timeouts, connection errors, non-2xx
        raise AgentError(f"{type(e).__name__}: {e}") from e
    except ValueError as e:  # body is not JSON
        raise AgentError(f"invalid JSON from agent: {e}") from e
    latency_ms = int((time.perf_counter() - started) * 1000)

    if not isinstance(data, dict):
        raise AgentError("malformed agent response: not a JSON object")
    reply, intent = data.get("reply"), data.get("intent")
    if not isinstance(reply, str) or not reply:
        raise AgentError("malformed agent response: missing 'reply'")
    if intent is not None and not isinstance(intent, str):
        raise AgentError("malformed agent response: 'intent' is not a string")
    return AgentReply(reply=reply, intent=intent, latency_ms=latency_ms)
