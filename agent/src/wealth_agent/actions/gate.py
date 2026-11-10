"""The action gate: check, stage, confirm, run, record (spec 011, revision 3).

Generic flow only. What each action means lives in a policy under `policies/`; where the data
comes from lives in `contribution_service.py`. Nothing here talks to the model: the gate trusts
only the verified participant ID and the participant's own message text.

Every statement, reads included, runs inside `Store.transaction()`.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import and_, insert, select, update

from wealth_agent.actions import store
from wealth_agent.actions.config import GateSettings
from wealth_agent.actions.identity import Participant

if TYPE_CHECKING:
    from wealth_agent.actions.contribution_service import ContributionService

FOOTER = "Demo data: no real account was changed."


# --- types shared by every action ------------------------------------------------------------------


class GateRefusal(Exception):
    """A rule said no. `reason` is a reason code from data-model.md; `message` is the plain sentence
    for the model or the participant when the policy has its own wording (e.g. the allowed range)."""

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
class CheckResult:
    """The outcome of the read-only check: `held` (the policy passed) or `rejected` with a reason."""

    status: str  # "held" | "rejected"
    reason: str | None = None
    message: str | None = None  # the plain sentence the tool returns to the model
    action: dict | None = None  # held: {"type", "params"} with the parsed params
    action_type: str = "unknown"


@dataclass(frozen=True)
class GateResult:
    step: str  # the audit step this decision ended on
    reason: str | None
    reply_text: str  # the reply for the participant; already has the footer
    pending_action_id: int | None = None


@dataclass(frozen=True)
class PendingRef:
    id: int
    session_id: str
    action_type: str
    params: dict
    snapshot: dict


@dataclass(frozen=True)
class Reply:
    kind: str  # "confirm" | "cancel"
    exact: bool  # the whole message was the accepted word, not just its first word


@dataclass(frozen=True)
class PolicyContext:
    """What a policy may use while it is built for one transaction."""

    conn: Any
    settings: GateSettings
    contributions: ContributionService


class ActionPolicy(Protocol):
    """One kind of write action. Each supplies its own rules, summary and executor (FR-002)."""

    name: str

    def parse(self, params: dict) -> dict:
        """Return clean params, or raise GateRefusal("invalid_params")."""

    def check(self, participant_id: str, params: dict) -> dict:
        """Raise GateRefusal(reason, message) or return the snapshot the summary is based on. Reads only."""

    def summary(self, params: dict, snapshot: dict, expiry_minutes: int) -> str: ...

    def execute(self, participant_id: str, params: dict, snapshot: dict, token: ConfirmationToken) -> str:
        """Run the change through its service and return the result message."""


PolicyFactory = Callable[[PolicyContext], ActionPolicy]


class StepUpCheck(Protocol):
    """Hook for step-up authentication, method still to be decided (FR-012)."""

    def verify(self, participant_id: str, action_type: str, claims: dict) -> bool: ...


class AlwaysPass:
    def verify(self, participant_id: str, action_type: str, claims: dict) -> bool:
        return True


# --- helpers ---------------------------------------------------------------------------------------


def with_footer(text: str) -> str:
    """End a gate message with the footer line, once (FR-031)."""
    body = text.rstrip()
    if body.endswith(FOOTER):
        return body
    return f"{body}\n\n{FOOTER}"


def without_footer(text: str) -> str:
    """The text as it goes into the agent's conversation: the footer is for the participant only."""
    return text.removesuffix(f"\n\n{FOOTER}").removesuffix(FOOTER).rstrip()


def record_audit(
    conn,
    user_id: str,
    action_type: str,
    step: str,
    reason: str | None = None,
    pending_action_id: int | None = None,
) -> None:
    """Insert one audit row in the caller's transaction. Insert only: nothing updates or deletes
    audit rows. It holds the participant ID and codes, never chat text, rates or names (FR-025)."""
    conn.execute(
        insert(store.action_audit).values(
            user_id=user_id,
            action_type=action_type,
            step=step,
            reason=reason,
            pending_action_id=pending_action_id,
        )
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- confirmation token (research R5) ----------------------------------------------------------------


def issue_token(conn, pending_action_id: int, user_id: str, session_id: str) -> ConfirmationToken:
    """Make the one-time token for a confirmed change. Only its SHA-256 hash is stored."""
    raw = secrets.token_urlsafe(32)  # 32 random bytes
    conn.execute(
        update(store.pending_actions)
        .where(store.pending_actions.c.id == pending_action_id)
        .values(token_hash=_hash(raw))
    )
    return ConfirmationToken(raw, pending_action_id, user_id, session_id)


def redeem_token(conn, token: ConfirmationToken, now: datetime | None = None) -> None:
    """Use the token once. One conditional update decides, so two callers can't both win.

    Raises GateRefusal("already_handled") for a token that was used, and GateRefusal("token_invalid")
    for one that doesn't belong to this participant and change.
    """
    pa = store.pending_actions
    match = and_(pa.c.id == token.pending_action_id, pa.c.user_id == token.user_id, pa.c.token_hash == _hash(token.raw))
    won = conn.execute(update(pa).where(match, pa.c.token_used_at.is_(None)).values(token_used_at=now or _now()))
    if won.rowcount == 1:
        return
    matched = conn.execute(select(pa.c.id).where(match)).first()
    raise GateRefusal("already_handled" if matched is not None else "token_invalid")


# --- texts ---------------------------------------------------------------------------------------------

UNAVAILABLE = "Contribution changes aren't available right now."
NOT_ALLOWED_NOW = "Changes to the account can't be made right now."
CANCELLED = "Cancelled. Nothing was changed."
REFUSAL_TEXT = {
    "invalid_params": "That change request couldn't be read.",
    "education_only": NOT_ALLOWED_NOW,
    "no_verified_participant": NOT_ALLOWED_NOW,
    "actions_unavailable": NOT_ALLOWED_NOW,
    "seed_unavailable": UNAVAILABLE,
    "unknown_action": UNAVAILABLE,
    "already_handled": "That change has already been handled.",
}
# Fixed replies written by the gate for a confirm or cancel message (FR-005).
FIXED_REPLIES = {
    "nothing_pending": "There is no change waiting for confirmation.",
}

CONFIRM = "confirm"
CANCEL = "cancel"
_IGNORED_MARKS = " \t\r\n.,!?;:\"'\u2018\u2019\u201c\u201d"
REPLACED_NOTE = "I've replaced your earlier pending change."


# --- the flow ---------------------------------------------------------------------------------------------


class ActionGate:
    """Check, stage, confirm, cancel, record. One instance serves every request; it holds no
    per-request state (the store, the settings, how to reach the contribution source, the clock)."""

    def __init__(
        self,
        store_: store.Store,
        settings: GateSettings,
        contributions_for: Callable[[Any], ContributionService] | None = None,
        step_up: StepUpCheck | None = None,
        clock: Callable[[], datetime] = _now,
        policies: Mapping[str, PolicyFactory] | None = None,
    ):
        self.store = store_
        self.settings = settings
        self._contributions_for = contributions_for
        self.step_up = step_up or AlwaysPass()
        self.clock = clock
        self._policies = policies

    # -- building blocks -------------------------------------------------------------------------------

    @property
    def policies(self) -> Mapping[str, PolicyFactory]:
        if self._policies is not None:
            return self._policies
        from wealth_agent.actions import policies  # resolved on use, so tests can register policies

        return policies.POLICIES

    def _contributions(self, conn) -> ContributionService:
        if self._contributions_for is not None:
            return self._contributions_for(conn)
        from wealth_agent.actions.contribution_service import DemoContributionService

        return DemoContributionService(conn)

    def _policy(self, conn, name: str) -> ActionPolicy:
        factory = self.policies.get(name)
        if factory is None:
            raise GateRefusal("unknown_action")
        return factory(PolicyContext(conn, self.settings, self._contributions(conn)))

    def _known(self, name: str) -> str:
        return name if name in self.policies else "unknown"

    # -- reading the participant's own message -------------------------------------------------------------

    def classify(self, message: str) -> Reply | None:
        """`Reply(kind, exact)` when the message is, or starts with, an accepted confirm or cancel
        word (ignoring case, surrounding spaces and the marks . , ! ? ; : and quotes); else None."""
        text = message.strip(_IGNORED_MARKS).lower()
        words = text.split()
        first = words[0].strip(_IGNORED_MARKS) if words else ""
        for kind, accepted in ((CONFIRM, self.settings.confirm_replies), (CANCEL, self.settings.cancel_replies)):
            if text in accepted:
                return Reply(kind, True)
            if first in accepted:
                return Reply(kind, False)
        return None

    # -- check (read-only) -----------------------------------------------------------------------------------

    def check_proposal(self, participant_id: str, session_id: str, action: dict, allowed: bool) -> CheckResult:
        """Apply the policy's rules without writing anything. Raises GateStoreError if the read fails."""
        name = action.get("type") if isinstance(action, dict) else None
        action_type = self._known(name) if isinstance(name, str) else "unknown"
        if not allowed:
            return self._rejected(GateRefusal("education_only"), action_type)
        try:
            with self.store.transaction() as conn:
                policy = self._policy(conn, name)
                params = policy.parse(action.get("params"))
                policy.check(participant_id, params)
        except GateRefusal as refusal:
            return self._rejected(refusal, action_type)
        return CheckResult("held", action={"type": name, "params": params}, action_type=action_type)

    @staticmethod
    def _rejected(refusal: GateRefusal, action_type: str) -> CheckResult:
        message = refusal.message or REFUSAL_TEXT.get(refusal.reason, UNAVAILABLE)
        return CheckResult("rejected", refusal.reason, message, action_type=action_type)

    # -- end-of-turn writes -----------------------------------------------------------------------------------

    def record_rejections(self, participant_id: str, rejected: list[dict]) -> None:
        """One `rejected` row per rejected request, with no pending_action_id."""
        with self.store.transaction() as conn:
            self._write_rejections(conn, participant_id, rejected)

    def _write_rejections(self, conn, participant_id: str, rejected) -> None:
        for item in rejected:
            record_audit(conn, participant_id, self._known(item.get("type", "")), "rejected", reason=item["reason"])

    def stage(self, participant_id: str, session_id: str, action: dict, rejected=()) -> GateResult:
        """One transaction: write the turn's rejections, re-check the held request, replace an older
        pending change, insert the new one and audit `staged`."""
        name = action["type"]
        action_type = self._known(name)
        with self.store.transaction() as conn:
            self._write_rejections(conn, participant_id, rejected)
            try:
                policy = self._policy(conn, name)
                params = policy.parse(action["params"])
                snapshot = policy.check(participant_id, params)
            except GateRefusal as refusal:
                record_audit(conn, participant_id, action_type, "rejected", reason=refusal.reason)
                text = refusal.message or REFUSAL_TEXT.get(refusal.reason, UNAVAILABLE)
                return GateResult("rejected", refusal.reason, with_footer(text))

            pa = store.pending_actions
            replaced = False
            for old in conn.execute(
                select(pa.c.id).where(pa.c.user_id == participant_id, pa.c.action_type == action_type, pa.c.status == "pending")
            ).all():
                conn.execute(update(pa).where(pa.c.id == old.id).values(status="cancelled", closed_at=self.clock()))
                record_audit(conn, participant_id, action_type, "cancelled", reason="replaced", pending_action_id=old.id)
                replaced = True

            now = self.clock()
            pending_id = conn.execute(
                insert(pa)
                .values(
                    user_id=participant_id,
                    session_id=session_id,
                    action_type=action_type,
                    params=params,
                    snapshot=snapshot,
                    status="pending",
                    staged_at=now,
                    expires_at=now + timedelta(seconds=self.settings.expiry_seconds),
                )
                .returning(pa.c.id)
            ).scalar_one()
            record_audit(conn, participant_id, action_type, "staged", pending_action_id=pending_id)
            minutes = max(1, round(self.settings.expiry_seconds / 60))
            text = policy.summary(params, snapshot, minutes)
        if replaced:
            text = f"{REPLACED_NOTE}\n\n{text}"
        return GateResult("staged", None, with_footer(text), pending_id)

    # -- the participant's pending change ---------------------------------------------------------------------------

    def find_pending(self, participant_id: str, session_id: str) -> PendingRef | None:
        """This participant's unexpired pending change in this chat."""
        pa = store.pending_actions
        with self.store.transaction() as conn:
            row = conn.execute(
                select(pa)
                .where(
                    pa.c.user_id == participant_id,
                    pa.c.session_id == session_id,
                    pa.c.status == "pending",
                    pa.c.expires_at > self.clock(),
                )
                .order_by(pa.c.id.desc())
            ).first()
        if row is None:
            return None
        return PendingRef(row.id, row.session_id, row.action_type, row.params, row.snapshot)

    def confirm(self, participant: Participant, pending: PendingRef) -> GateResult:
        """Confirm and run the change in one transaction."""
        user_id = participant.id
        pa = store.pending_actions
        with self.store.transaction() as conn:
            try:
                policy = self._policy(conn, pending.action_type)  # built first: a failure leaves it pending
            except GateRefusal as refusal:
                return self._refuse(conn, user_id, pending.action_type, refusal, pending.id)
            won = conn.execute(
                update(pa).where(pa.c.id == pending.id, pa.c.status == "pending").values(status="confirmed")
            )
            if won.rowcount != 1:
                return self._refuse(conn, user_id, pending.action_type, GateRefusal("already_handled"), pending.id)
            record_audit(conn, user_id, pending.action_type, "confirmed", pending_action_id=pending.id)
            token = issue_token(conn, pending.id, user_id, pending.session_id)
            message = policy.execute(user_id, pending.params, pending.snapshot, token)
            conn.execute(update(pa).where(pa.c.id == pending.id).values(status="executed", closed_at=self.clock()))
            record_audit(conn, user_id, pending.action_type, "executed", pending_action_id=pending.id)
        return GateResult("executed", None, with_footer(message), pending.id)

    def cancel(self, participant: Participant, pending: PendingRef) -> GateResult:
        user_id = participant.id
        pa = store.pending_actions
        with self.store.transaction() as conn:
            conn.execute(update(pa).where(pa.c.id == pending.id).values(status="cancelled", closed_at=self.clock()))
            record_audit(
                conn, user_id, pending.action_type, "cancelled", reason="participant_cancelled", pending_action_id=pending.id
            )
            text = CANCELLED
            try:
                policy = self._policy(conn, pending.action_type)
                text = getattr(policy, "cancel_message", lambda snapshot: CANCELLED)(pending.snapshot)
            except GateRefusal:
                pass  # the policy can't be built now; the generic wording is enough
        return GateResult("cancelled", "participant_cancelled", with_footer(text), pending.id)

    def refuse_reply(self, participant_id: str, reason: str, pending: PendingRef | None = None) -> GateResult:
        """A fixed reply for a confirm or cancel message, recorded as `rejected`."""
        action_type = pending.action_type if pending else "unknown"
        with self.store.transaction() as conn:
            record_audit(
                conn, participant_id, action_type, "rejected", reason=reason,
                pending_action_id=pending.id if pending else None,
            )
        return GateResult("rejected", reason, with_footer(FIXED_REPLIES[reason]), pending.id if pending else None)

    def _refuse(self, conn, user_id: str, action_type: str, refusal: GateRefusal, pending_id: int | None) -> GateResult:
        record_audit(conn, user_id, action_type, "rejected", reason=refusal.reason, pending_action_id=pending_id)
        text = refusal.message or REFUSAL_TEXT.get(refusal.reason, UNAVAILABLE)
        return GateResult("rejected", refusal.reason, with_footer(text), pending_id)
