from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # client-supplied session_id
    # The token's `sub` for whoever sent the first message; never changed. NULL = nobody owns it
    # (every chat stored before spec 008), so the API treats it as not found for everyone.
    user_id: Mapped[str | None] = mapped_column(Text)
    # Spec 009: the access result of the latest turn ('granted' | 'unavailable') and when it was decided.
    access: Mapped[str | None] = mapped_column(Text)
    access_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        # 'gate' marks text written by the action gate (spec 011, approved deviation from Principle II).
        CheckConstraint("source IN ('agent', 'mock', 'gate')", name="ck_messages_source"),
    )

    # The Integer variant only matters for the SQLite DB used in tests (BigInteger PKs don't autoincrement there).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True
    )
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(Text)  # 'agent' | 'mock' | 'gate'; null on user rows
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Feedback(Base):
    """A user's rating of one assistant message. At most one row per message."""

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating IN ('up', 'down')", name="ck_feedback_rating"),
        # Only the stable rules are in the database. The provisional reason list and the comment
        # length limit are enforced in app/feedback.py (research R3).
        CheckConstraint("reason IS NULL OR rating = 'down'", name="ck_feedback_reason_requires_down"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("messages.id"),
        unique=True,
        nullable=False,
    )
    # NOT NULL today because every row is a user rating. Relaxing it later (for escalation records)
    # is one ALTER COLUMN ... DROP NOT NULL; both check constraints already accept a NULL rating.
    rating: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(Text)  # filled in once agent tracing exists
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Contribution(Base):
    """A participant's current 401(k) contribution rate (spec 011). No row = the seed's starting rate."""

    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint("rate_pct BETWEEN 0 AND 100", name="ck_contributions_rate_pct"),
    )

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)  # the token's `sub`
    rate_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PendingAction(Base):
    """A staged change waiting for the participant's confirmation (spec 011)."""

    __tablename__ = "pending_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'executed', 'cancelled', 'expired', 'failed')",
            name="ck_pending_actions_status",
        ),
        # At most one pending change per participant and action type (FR-010).
        Index(
            "uq_pending_actions_one_pending",
            "user_id",
            "action_type",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, ForeignKey("sessions.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)  # exact values that will run
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)  # values the summary was based on
    status: Mapped[str] = mapped_column(Text, nullable=False)
    staged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_hash: Mapped[str | None] = mapped_column(Text)  # SHA-256 of the confirmation token
    token_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionAudit(Base):
    """The business record of every gate step. Append-only; the participant ID is the only personal data."""

    __tablename__ = "action_audit"
    __table_args__ = (
        CheckConstraint(
            "step IN ('rejected', 'staged', 'confirmed', 'cancelled', 'expired', "
            "'executed', 'failed')",
            name="ck_action_audit_step",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    pending_action_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), ForeignKey("pending_actions.id")
    )
    step: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)  # a reason code, never free text
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
