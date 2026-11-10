"""add action gate tables (spec 011)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("rate_pct", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rate_pct BETWEEN 0 AND 100", name="ck_contributions_rate_pct"),
        sa.PrimaryKeyConstraint("user_id", name="pk_contributions"),
    )
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=True),
        sa.Column("token_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'executed', 'cancelled', 'expired', 'failed')",
            name="ck_pending_actions_status",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_pending_actions_session_id"),
        sa.PrimaryKeyConstraint("id", name="pk_pending_actions"),
    )
    op.create_index("ix_pending_actions_user_id", "pending_actions", ["user_id"])
    op.create_index(
        "uq_pending_actions_one_pending",
        "pending_actions",
        ["user_id", "action_type"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "action_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("pending_action_id", sa.BigInteger(), nullable=True),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "step IN ('proposed', 'rejected', 'staged', 'confirmed', 'cancelled', 'expired', "
            "'executed', 'failed')",
            name="ck_action_audit_step",
        ),
        sa.ForeignKeyConstraint(
            ["pending_action_id"], ["pending_actions.id"], name="fk_action_audit_pending_action_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_action_audit"),
    )
    op.create_index("ix_action_audit_user_id", "action_audit", ["user_id"])

    # Gate-written messages get their own source value (approved deviation from Principle II).
    op.drop_constraint("ck_messages_source", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_source", "messages", "source IN ('agent', 'mock', 'gate')"
    )


def downgrade() -> None:
    # Gate messages can't satisfy the old constraint, so remove them (and any rating of them) first.
    op.execute(
        "DELETE FROM feedback WHERE message_id IN (SELECT id FROM messages WHERE source = 'gate')"
    )
    op.execute("DELETE FROM messages WHERE source = 'gate'")
    op.drop_constraint("ck_messages_source", "messages", type_="check")
    op.create_check_constraint("ck_messages_source", "messages", "source IN ('agent', 'mock')")

    op.drop_index("ix_action_audit_user_id", table_name="action_audit")
    op.drop_table("action_audit")
    op.drop_index("uq_pending_actions_one_pending", table_name="pending_actions")
    op.drop_index("ix_pending_actions_user_id", table_name="pending_actions")
    op.drop_table("pending_actions")
    op.drop_table("contributions")
