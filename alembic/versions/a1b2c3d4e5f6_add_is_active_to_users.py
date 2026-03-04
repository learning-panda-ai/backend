"""add_is_active_to_users

Revision ID: a1b2c3d4e5f6
Revises: f7a6b5c4d3e2
Create Date: 2026-03-04 21:30:00.000000

Changes:
- ADD COLUMN is_active  BOOLEAN  NOT NULL DEFAULT true
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f7a6b5c4d3e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
