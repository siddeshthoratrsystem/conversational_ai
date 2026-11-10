"""The action gate: propose, check, stage, confirm, run, record (spec 011).

Nothing here talks to the model. The gate only trusts the participant ID from the verified
sign-in token and the participant's own message text.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app import models

FOOTER = "Demo data: no real account was changed."


# --- settings (demo defaults, not Principal policy; FR-026) -----------------------------------

@dataclass(frozen=True)
class GateSettings:
    expiry_seconds: int = 300
    confirm_replies: tuple[str, ...] = ("confirm",)
    cancel_replies: tuple[str, ...] = ("cancel",)
    min_pct: int = 0
    max_pct: int = 50
    whole_pct_only: bool = True


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
    defaults = GateSettings()
    whole = _text(env, "CONTRIBUTION_WHOLE_PCT_ONLY")
    return GateSettings(
        expiry_seconds=_int(env, "ACTION_EXPIRY_SECONDS", defaults.expiry_seconds),
        confirm_replies=_replies(env, "ACTION_CONFIRM_REPLIES", defaults.confirm_replies),
        cancel_replies=_replies(env, "ACTION_CANCEL_REPLIES", defaults.cancel_replies),
        min_pct=_int(env, "CONTRIBUTION_MIN_PCT", defaults.min_pct),
        max_pct=_int(env, "CONTRIBUTION_MAX_PCT", defaults.max_pct),
        whole_pct_only=defaults.whole_pct_only
        if whole is None
        else whole.lower() in {"1", "true", "yes", "on"},
    )


# --- types shared by every action type ---------------------------------------------------------

class GateRefusal(Exception):
    """A rule said no. `reason` is one of the reason codes in data-model.md. `message` is the plain
    sentence for the participant when the action type has its own wording (e.g. the allowed range)."""

    def __init__(self, reason: str, message: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class ConfirmationToken:
    """Issued once at confirm. `raw` is never stored, only its SHA-256 hash."""

    raw: str
    pending_action_id: int
    user_id: str
    session_id: str


@dataclass(frozen=True)
class GateResult:
    step: str  # the audit step this decision ended on
    reason: str | None
    reply_text: str  # becomes the assistant message (FR-013); already has the footer
    pending_action_id: int | None = None


class ActionType(Protocol):
    """One kind of write action. Each supplies its own rules, summary and executor (FR-002)."""

    name: str

    def parse(self, params: dict) -> dict:
        """Return clean params, or raise GateRefusal("invalid_params")."""

    def check(self, participant_id: str, params: dict) -> dict:
        """Raise GateRefusal(<reason>) or return the snapshot the summary is based on."""

    def summary(self, params: dict, snapshot: dict, expiry_minutes: int) -> str: ...

    def execute(
        self, participant_id: str, params: dict, snapshot: dict, token: ConfirmationToken
    ) -> str:
        """Run the change through its service and return the result message."""


class ContributionService(Protocol):
    """The only way the gate reads or changes contributions (FR-021)."""

    def current_rate(self, participant_id: str) -> int: ...

    def apply_change(self, participant_id: str, new_rate_pct: int, token: ConfirmationToken) -> int:
        """Redeem the token (single use), apply the change and return the new rate."""


class StepUpCheck(Protocol):
    """Hook for step-up authentication, method still to be decided (FR-012)."""

    def verify(self, participant_id: str, action_type: str, claims: dict) -> bool: ...


@dataclass(frozen=True)
class ActionContext:
    """What an action type may use while it is built for one request."""

    db: DbSession
    settings: GateSettings
    contributions: ContributionService


# Registry: name -> builder. Adding an action type means adding an entry; the flow below is unchanged.
ActionFactory = Callable[[ActionContext], ActionType]
ACTION_TYPES: dict[str, ActionFactory] = {}


# --- helpers ------------------------------------------------------------------------------------

def with_footer(text: str) -> str:
    """End a gate message with the footer line, once (FR-031)."""
    body = text.rstrip()
    if body.endswith(FOOTER):
        return body
    return f"{body}\n\n{FOOTER}"


def record_audit(
    db: DbSession,
    user_id: str,
    action_type: str,
    step: str,
    reason: str | None = None,
    pending_action_id: int | None = None,
) -> models.ActionAudit:
    """Add one audit row in the caller's transaction. Insert only: nothing updates or deletes
    audit rows. It holds the participant ID and codes, never chat text, rates or names (FR-025)."""
    row = models.ActionAudit(
        user_id=user_id,
        action_type=action_type,
        step=step,
        reason=reason,
        pending_action_id=pending_action_id,
    )
    db.add(row)
    db.flush()
    return row


# --- confirmation token (research R5) -------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(db: DbSession, pending: models.PendingAction) -> ConfirmationToken:
    """Make the one-time token for a confirmed change. Only its SHA-256 hash is stored."""
    raw = secrets.token_urlsafe(32)  # 32 random bytes
    pending.token_hash = _hash(raw)
    db.flush()
    return ConfirmationToken(raw, pending.id, pending.user_id, pending.session_id)


def redeem_token(db: DbSession, token: ConfirmationToken, now: datetime | None = None) -> None:
    """Use the token once. One conditional update decides, so two callers can't both win.

    Raises GateRefusal("already_handled") for a token that was used, and GateRefusal("token_invalid")
    for one that doesn't belong to this participant and change.
    """
    match = (
        models.PendingAction.id == token.pending_action_id,
        models.PendingAction.user_id == token.user_id,
        models.PendingAction.token_hash == _hash(token.raw),
    )
    won = db.execute(
        update(models.PendingAction)
        .where(*match, models.PendingAction.token_used_at.is_(None))
        .values(token_used_at=now or _now())
        .execution_options(synchronize_session="fetch")
    )
    if won.rowcount == 1:
        return
    used = db.execute(select(models.PendingAction.token_used_at).where(*match)).first()
    raise GateRefusal("already_handled" if used is not None else "token_invalid")


# --- the flow --------------------------------------------------------------------------------------

UNAVAILABLE = "Contribution changes aren't available right now."
NOTHING_TO_CONFIRM = "There's no pending change to confirm."
NOTHING_TO_CANCEL = "There's no pending change to cancel."
CANCELLED = "Cancelled. Nothing was changed."
REFUSAL_TEXT = {
    "invalid_params": "I couldn't read that change request, so nothing was changed.",
    "already_handled": "That change has already been handled.",
}

CONFIRM = "confirm"
CANCEL = "cancel"
_IGNORED_MARKS = " \t\r\n.,!?;:\"'\u2018\u2019\u201c\u201d"


class ActionGate:
    """Propose, check, stage, confirm, run, record. One instance per request.

    The `handle_*` methods write state and audit rows in the caller's transaction and never commit.
    They know nothing about any one action type; each type comes from the registry.
    """

    def __init__(
        self,
        db: DbSession,
        settings: GateSettings,
        contributions: ContributionService,
        registry: Mapping[str, ActionFactory] | None = None,
        clock: Callable[[], datetime] = _now,
    ):
        self.db = db
        self.settings = settings
        self.registry = ACTION_TYPES if registry is None else registry
        self.clock = clock
        self.context = ActionContext(db, settings, contributions)

    # -- reading the participant's own message ----------------------------------------------------

    def classify_reply(self, message: str) -> str | None:
        """CONFIRM or CANCEL when the whole message is one of the accepted words (ignoring case,
        surrounding spaces and the marks . , ! ? ; : and quotes); otherwise None. Read-only."""
        word = message.strip(_IGNORED_MARKS).lower()
        if word in self.settings.confirm_replies:
            return CONFIRM
        if word in self.settings.cancel_replies:
            return CANCEL
        return None

    # -- propose ----------------------------------------------------------------------------------

    def handle_proposal(self, user_id: str, session_id: str, action: dict) -> GateResult:
        requested = action["type"]
        action_type = requested if requested in self.registry else "unknown"
        record_audit(self.db, user_id, action_type, "proposed")
        try:
            if requested not in self.registry:
                raise GateRefusal("unknown_action")
            impl = self.registry[requested](self.context)
            params = impl.parse(action["params"])
            snapshot = impl.check(user_id, params)
        except GateRefusal as refusal:
            return self._reject(user_id, action_type, refusal)

        now = self.clock()
        pending = models.PendingAction(
            user_id=user_id,
            session_id=session_id,
            action_type=action_type,
            params=params,
            snapshot=snapshot,
            status="pending",
            staged_at=now,
            expires_at=now + timedelta(seconds=self.settings.expiry_seconds),
        )
        self.db.add(pending)
        self.db.flush()
        record_audit(self.db, user_id, action_type, "staged", pending_action_id=pending.id)
        minutes = max(1, round(self.settings.expiry_seconds / 60))
        return GateResult("staged", None, with_footer(impl.summary(params, snapshot, minutes)), pending.id)

    # -- confirm or cancel ---------------------------------------------------------------------------

    def handle_reply(self, user_id: str, session_id: str, kind: str) -> GateResult:
        pending = self.db.scalars(
            select(models.PendingAction)
            .where(
                models.PendingAction.user_id == user_id,
                models.PendingAction.session_id == session_id,
                models.PendingAction.status == "pending",
            )
            .order_by(models.PendingAction.id.desc())
        ).first()
        if pending is None:
            text = NOTHING_TO_CONFIRM if kind == CONFIRM else NOTHING_TO_CANCEL
            return self._reject(user_id, "unknown", GateRefusal("nothing_pending", text))
        if kind == CANCEL:
            return self._cancel(pending)
        return self._confirm(pending)

    def _cancel(self, pending: models.PendingAction) -> GateResult:
        self._close(pending, "cancelled")
        record_audit(
            self.db, pending.user_id, pending.action_type, "cancelled",
            reason="participant_cancelled", pending_action_id=pending.id,
        )
        text = CANCELLED
        factory = self.registry.get(pending.action_type)
        if factory is not None:
            try:
                impl = factory(self.context)
                text = getattr(impl, "cancel_message", lambda snapshot: CANCELLED)(pending.snapshot)
            except GateRefusal:
                pass  # the action type can't be built now; the generic wording is enough
        return GateResult("cancelled", "participant_cancelled", with_footer(text), pending.id)

    def _confirm(self, pending: models.PendingAction) -> GateResult:
        user_id, action_type = pending.user_id, pending.action_type
        try:
            factory = self.registry.get(action_type)
            if factory is None:
                raise GateRefusal("unknown_action")
            impl = factory(self.context)  # built first, so a failure leaves the change pending
        except GateRefusal as refusal:
            return self._reject(user_id, action_type, refusal, pending.id)

        won = self.db.execute(
            update(models.PendingAction)
            .where(models.PendingAction.id == pending.id, models.PendingAction.status == "pending")
            .values(status="confirmed")
            .execution_options(synchronize_session="fetch")
        )
        if won.rowcount != 1:
            return self._reject(user_id, action_type, GateRefusal("already_handled"), pending.id)
        record_audit(self.db, user_id, action_type, "confirmed", pending_action_id=pending.id)

        token = issue_token(self.db, pending)
        message = impl.execute(user_id, pending.params, pending.snapshot, token)
        self._close(pending, "executed")
        record_audit(self.db, user_id, action_type, "executed", pending_action_id=pending.id)
        return GateResult("executed", None, with_footer(message), pending.id)

    # -- helpers --------------------------------------------------------------------------------------

    def _close(self, pending: models.PendingAction, status: str) -> None:
        pending.status = status
        pending.closed_at = self.clock()
        self.db.flush()

    def _reject(
        self, user_id: str, action_type: str, refusal: GateRefusal, pending_id: int | None = None
    ) -> GateResult:
        record_audit(
            self.db, user_id, action_type, "rejected", reason=refusal.reason, pending_action_id=pending_id
        )
        text = refusal.message or REFUSAL_TEXT.get(refusal.reason, UNAVAILABLE)
        return GateResult("rejected", refusal.reason, with_footer(text), pending_id)
