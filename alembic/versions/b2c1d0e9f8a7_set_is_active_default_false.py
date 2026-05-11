"""set_is_active_default_false

Revision ID: b2c1d0e9f8a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09 00:00:00.000000

Changes:
- ALTER COLUMN is_active  SET DEFAULT false  (was true)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c1d0e9f8a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "is_active",
        server_default=sa.text("false"),
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "is_active",
        server_default=sa.text("true"),
    )
