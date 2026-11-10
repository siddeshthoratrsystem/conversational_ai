"""Gate settings and the start-up check (spec 011, FR-016a, FR-026, FR-033).

Demo defaults, not Principal policy. `AGENT_TIMEOUT_SECONDS` is read from the same variable, with
the same default (60), as the back end; both processes get it from their own environment (the
shared `.env`, exported in each shell). The values each process uses are logged once at start-up.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger("wealth_agent.actions.config")
logger.setLevel(logging.INFO)  # the start-up line is informational but must be visible

AGENT_TIMEOUT_ENV = "AGENT_TIMEOUT_SECONDS"
DEFAULT_AGENT_TIMEOUT_SECONDS = 60
REQUIRED_SETTINGS = ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL", "DATABASE_URL")


@dataclass(frozen=True)
class GateSettings:
    expiry_seconds: int = 300
    confirm_replies: tuple[str, ...] = ("confirm",)
    cancel_replies: tuple[str, ...] = ("cancel",)
    min_pct: int = 0
    max_pct: int = 50
    stage_deadline_seconds: int = 50
    db_timeout_seconds: int = 3
    agent_timeout_seconds: int = DEFAULT_AGENT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ActionsStatus:
    enabled: bool
    problems: tuple[str, ...]


def _text(env: Mapping[str, str], key: str) -> str | None:
    value = (env.get(key) or "").strip()
    return value or None


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    value = _text(env, key)
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _replies(env: Mapping[str, str], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _text(env, key)
    if value is None:
        return default
    replies = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    return replies or default


def load_settings(env: Mapping[str, str] | None = None) -> GateSettings:
    env = os.environ if env is None else env
    d = GateSettings()
    return GateSettings(
        expiry_seconds=_int(env, "ACTION_EXPIRY_SECONDS", d.expiry_seconds),
        confirm_replies=_replies(env, "ACTION_CONFIRM_REPLIES", d.confirm_replies),
        cancel_replies=_replies(env, "ACTION_CANCEL_REPLIES", d.cancel_replies),
        min_pct=_int(env, "CONTRIBUTION_MIN_PCT", d.min_pct),
        max_pct=_int(env, "CONTRIBUTION_MAX_PCT", d.max_pct),
        stage_deadline_seconds=_int(env, "ACTION_STAGE_DEADLINE_SECONDS", d.stage_deadline_seconds),
        db_timeout_seconds=_int(env, "ACTION_DB_TIMEOUT_SECONDS", d.db_timeout_seconds),
        agent_timeout_seconds=_int(env, AGENT_TIMEOUT_ENV, d.agent_timeout_seconds),
    )


def startup_check(env: Mapping[str, str] | None = None) -> ActionsStatus:
    """Decide whether actions can run. Logs the timeout values in use and, if actions are off,
    one warning listing every problem. Never logs a secret (only setting names and numbers)."""
    env = os.environ if env is None else env
    settings = load_settings(env)
    problems = [f"{name} is not set" for name in REQUIRED_SETTINGS if not _text(env, name)]
    if settings.stage_deadline_seconds >= settings.agent_timeout_seconds:
        problems.append(
            f"ACTION_STAGE_DEADLINE_SECONDS ({settings.stage_deadline_seconds}) must be lower than "
            f"{AGENT_TIMEOUT_ENV} ({settings.agent_timeout_seconds})"
        )
    logger.info(
        "%s=%s ACTION_STAGE_DEADLINE_SECONDS=%s (actions %s)",
        AGENT_TIMEOUT_ENV,
        settings.agent_timeout_seconds,
        settings.stage_deadline_seconds,
        "disabled" if problems else "enabled",
    )
    if problems:
        logger.warning("Contribution changes are disabled: %s", "; ".join(problems))
    return ActionsStatus(enabled=not problems, problems=tuple(problems))
