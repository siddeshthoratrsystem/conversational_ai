"""The gate's database access (spec 011, research R21, R22).

The tables mirror `backend/app/models.py`, which owns them through Alembic; the agent never
creates tables outside tests (`tests/test_agent_store_schema.py` in the back end compares the two).
This module imports only SQLAlchemy, so that test can load it by file path.

Every gate statement, reads included, runs inside `Store.transaction()`, which sets a statement
timeout on Postgres. Any database error or timeout becomes `GateStoreError`, after a rollback.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.exc import SQLAlchemyError

# The same naming convention as the back end, so constraint names match the migration.
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s",
    }
)

_ID = BigInteger().with_variant(Integer, "sqlite")  # SQLite (tests) only autoincrements INTEGER keys

# A minimal copy: the agent only needs the row to exist for the foreign key.
sessions = Table("sessions", metadata, Column("id", Text, primary_key=True))

contributions = Table(
    "contributions",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("rate_pct", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("rate_pct BETWEEN 0 AND 100", name="ck_contributions_rate_pct"),
)

pending_actions = Table(
    "pending_actions",
    metadata,
    Column("id", _ID, Identity(), primary_key=True),
    Column("user_id", Text, nullable=False, index=True),
    Column("session_id", Text, ForeignKey("sessions.id"), nullable=False),
    Column("action_type", Text, nullable=False),
    Column("params", JSON, nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("status", Text, nullable=False),
    Column("staged_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("token_hash", Text),
    Column("token_used_at", DateTime(timezone=True)),
    Column("closed_at", DateTime(timezone=True)),
    CheckConstraint(
        "status IN ('pending', 'confirmed', 'executed', 'cancelled', 'expired', 'failed')",
        name="ck_pending_actions_status",
    ),
    # At most one pending change per participant and action type.
    Index(
        "uq_pending_actions_one_pending",
        "user_id",
        "action_type",
        unique=True,
        postgresql_where=text("status = 'pending'"),
        sqlite_where=text("status = 'pending'"),
    ),
)

action_audit = Table(
    "action_audit",
    metadata,
    Column("id", _ID, Identity(), primary_key=True),
    Column("user_id", Text, nullable=False, index=True),
    Column("action_type", Text, nullable=False),
    Column("pending_action_id", _ID, ForeignKey("pending_actions.id")),
    Column("step", Text, nullable=False),
    Column("reason", Text),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    CheckConstraint(
        "step IN ('rejected', 'staged', 'confirmed', 'cancelled', 'expired', 'executed', 'failed')",
        name="ck_action_audit_step",
    ),
)


class GateStoreError(Exception):
    """A gate statement failed or timed out. The transaction was rolled back; nothing was written."""

    def __init__(self, message: str, timed_out: bool = False):
        super().__init__(message)
        self.timed_out = timed_out


class Store:
    """One engine and the statement timeout every transaction uses."""

    def __init__(self, engine, timeout_ms: int = 3000):
        self.engine = engine
        self.timeout_ms = int(timeout_ms)

    @classmethod
    def from_settings(cls, engine, settings) -> Store:
        return cls(engine, timeout_ms=settings.db_timeout_seconds * 1000)

    @contextmanager
    def transaction(self) -> Iterator:
        """A connection inside one transaction: commit on success, roll back and raise
        `GateStoreError` on any database error or timeout."""
        try:
            with self.engine.begin() as conn:
                if self.engine.dialect.name == "postgresql":
                    conn.execute(text(f"SET LOCAL statement_timeout = {self.timeout_ms}"))
                yield conn
        except SQLAlchemyError as exc:
            detail = str(getattr(exc, "orig", None) or exc)
            raise GateStoreError(f"{type(exc).__name__}: {detail}", "timeout" in detail.lower()) from exc


def _normalize_database_url(url: str) -> str:
    """Force the psycopg (v3) driver so a plain postgresql:// URL works with SQLAlchemy."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_store() -> Store:
    """The process's store, built from DATABASE_URL on first use (no connection is made here)."""
    from wealth_agent.actions.config import load_settings

    url = os.getenv("DATABASE_URL")
    if not url:
        raise GateStoreError("DATABASE_URL is not set")
    engine = create_engine(_normalize_database_url(url), pool_pre_ping=True)
    return Store.from_settings(engine, load_settings())
