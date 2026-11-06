from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Integer, Text, func
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
        CheckConstraint("source IN ('agent', 'mock')", name="ck_messages_source"),
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
    source: Mapped[str | None] = mapped_column(Text)  # 'agent' | 'mock'; null on user rows
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
