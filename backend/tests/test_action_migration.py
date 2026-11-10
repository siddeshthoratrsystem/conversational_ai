"""Migration 0005 rendered as offline Postgres SQL matches data-model.md (spec 011).

No database is needed: alembic writes the statements to a buffer instead of running them.
"""

import importlib.util
import io
import re
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0005_add_action_gate.py"


def _render(direction: str) -> str:
    spec = importlib.util.spec_from_file_location("migration_0005", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buf = io.StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf}
    )
    with Operations.context(ctx):
        getattr(module, direction)()
    return re.sub(r"\s+", " ", buf.getvalue())


@pytest.fixture(scope="module")
def upgrade_sql():
    return _render("upgrade")


@pytest.fixture(scope="module")
def downgrade_sql():
    return _render("downgrade")


def test_revision_chain():
    text = MIGRATION.read_text()
    assert 'revision: str = "0005"' in text
    assert '"0004"' in text


@pytest.mark.parametrize("table", ["contributions", "pending_actions", "action_audit"])
def test_creates_each_table(upgrade_sql, table):
    assert f"CREATE TABLE {table} (" in upgrade_sql


@pytest.mark.parametrize(
    "fragment",
    [
        # contributions
        "user_id TEXT NOT NULL",
        "rate_pct INTEGER NOT NULL",
        "CONSTRAINT ck_contributions_rate_pct CHECK (rate_pct BETWEEN 0 AND 100)",
        "CONSTRAINT pk_contributions PRIMARY KEY (user_id)",
        # pending_actions
        "session_id TEXT NOT NULL",
        "action_type TEXT NOT NULL",
        "params JSON NOT NULL",
        "snapshot JSON NOT NULL",
        "status TEXT NOT NULL",
        "staged_at TIMESTAMP WITH TIME ZONE NOT NULL",
        "expires_at TIMESTAMP WITH TIME ZONE NOT NULL",
        "token_hash TEXT",
        "token_used_at TIMESTAMP WITH TIME ZONE",
        "closed_at TIMESTAMP WITH TIME ZONE",
        "CONSTRAINT ck_pending_actions_status CHECK (status IN ('pending', 'confirmed', 'executed', "
        "'cancelled', 'expired', 'failed'))",
        "CONSTRAINT fk_pending_actions_session_id FOREIGN KEY(session_id) REFERENCES sessions (id)",
        "CONSTRAINT pk_pending_actions PRIMARY KEY (id)",
        # action_audit
        "pending_action_id BIGINT",
        "step TEXT NOT NULL",
        "reason TEXT",
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL",
        "CONSTRAINT ck_action_audit_step CHECK (step IN ('proposed', 'rejected', 'staged', "
        "'confirmed', 'cancelled', 'expired', 'executed', 'failed'))",
        "CONSTRAINT fk_action_audit_pending_action_id FOREIGN KEY(pending_action_id) "
        "REFERENCES pending_actions (id)",
        "CONSTRAINT pk_action_audit PRIMARY KEY (id)",
    ],
)
def test_upgrade_has(upgrade_sql, fragment):
    assert fragment in upgrade_sql


def test_partial_unique_index_keeps_one_pending_change(upgrade_sql):
    assert (
        "CREATE UNIQUE INDEX uq_pending_actions_one_pending ON pending_actions "
        "(user_id, action_type) WHERE status = 'pending'"
    ) in upgrade_sql


@pytest.mark.parametrize(
    "index", ["ix_pending_actions_user_id", "ix_action_audit_user_id"]
)
def test_creates_lookup_indexes(upgrade_sql, index):
    assert f"CREATE INDEX {index} ON" in upgrade_sql


def test_message_source_constraint_is_widened(upgrade_sql):
    assert "ALTER TABLE messages DROP CONSTRAINT ck_messages_source" in upgrade_sql
    assert (
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_source "
        "CHECK (source IN ('agent', 'mock', 'gate'))"
    ) in upgrade_sql


def test_downgrade_reverses_everything(downgrade_sql):
    for table in ("action_audit", "pending_actions", "contributions"):
        assert f"DROP TABLE {table}" in downgrade_sql
    assert "DROP INDEX uq_pending_actions_one_pending" in downgrade_sql
    assert "ALTER TABLE messages DROP CONSTRAINT ck_messages_source" in downgrade_sql
    assert (
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_source "
        "CHECK (source IN ('agent', 'mock'))"
    ) in downgrade_sql
