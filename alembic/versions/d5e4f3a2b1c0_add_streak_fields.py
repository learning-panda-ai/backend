"""add_streak_fields

Revision ID: d5e4f3a2b1c0
Revises: c4d3e2f1a0b9
Create Date: 2026-03-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e4f3a2b1c0"
down_revision: Union[str, Sequence[str], None] = "c4d3e2f1a0b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("last_activity_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_activity_date")
    op.drop_column("users", "longest_streak")
    op.drop_column("users", "current_streak")
