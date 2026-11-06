"""add session access result (spec 009)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: chats stored before this have no recorded access result.
    op.add_column("sessions", sa.Column("access", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("access_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "access_checked_at")
    op.drop_column("sessions", "access")
