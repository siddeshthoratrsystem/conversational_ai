import logging
import os
import time
from dataclasses import dataclass

import httpx

DEFAULT_AGENT_TIMEOUT_SECONDS = 60
logger = logging.getLogger("app.agent")
logger.setLevel(logging.INFO)  # the start-up line below is informational but must be visible


def agent_timeout_seconds() -> float:
    """Seconds to wait for the agent: `AGENT_TIMEOUT_SECONDS` (shared with the agent), default 60."""
    raw = os.getenv("AGENT_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_AGENT_TIMEOUT_SECONDS
    try:
        value = float(raw)
        if value > 0:
            return int(value) if value == int(value) else value
    except ValueError:
        pass
    if raw.strip():
        logger.warning(
            "Ignoring unusable AGENT_TIMEOUT_SECONDS=%r; using %s", raw, DEFAULT_AGENT_TIMEOUT_SECONDS
        )
    return DEFAULT_AGENT_TIMEOUT_SECONDS


def log_timeout_at_start_up() -> None:
    """One line saying which timeout this process uses, so a mismatch with the agent is visible."""
    logger.info("AGENT_TIMEOUT_SECONDS=%s (back end wait for the agent)", agent_timeout_seconds())


class AgentError(Exception):
    """The agent call failed or returned something unusable."""


@dataclass
class AgentReply:
    reply: str
    intent: str | None
    latency_ms: int
    # Spec 011: "gate" when the agent wrote the text in code (the action gate); otherwise None.
    source: str | None = None


def call_agent(
    url: str,
    session_id: str,
    message: str,
    education_only: bool = False,
    token: str | None = None,
) -> AgentReply:
    """POST {prompt, session_id} to the agent and parse {reply, intent, source}. Raises AgentError on any failure.

    With education_only (spec 009), the body also carries "education_only": true; otherwise it is unchanged.
    With a token (spec 011), the participant's own bearer token is forwarded as `Authorization: Bearer`.
    The token is never logged.
    """
    body = {"prompt": message, "session_id": session_id}
    if education_only:
        body["education_only"] = True
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=agent_timeout_seconds()) as client:
            r = client.post(url, json=body, headers=headers)
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
    return AgentReply(reply=reply, intent=intent, latency_ms=latency_ms, source=_parse_source(data.get("source")))


def _parse_source(source) -> str | None:
    """'gate', or None when absent or null. Anything else is ignored (logged) and the reply is kept."""
    if source is None or source == "gate":
        return source
    logger.warning("Ignoring unrecognised 'source' in agent response")
    return None
