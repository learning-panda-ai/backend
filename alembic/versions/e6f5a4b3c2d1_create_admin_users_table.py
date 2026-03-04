"""create_admin_users_table

Revision ID: e6f5a4b3c2d1
Revises: d5e4f3a2b1c0
Create Date: 2026-03-04 00:00:00.000000

Changes:
- CREATE TABLE admin_users  (separate admin accounts with email + OTP auth only)
- DROP COLUMN role FROM users  (role is no longer stored on the regular users table)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e6f5a4b3c2d1"
down_revision: Union[str, Sequence[str], None] = "d5e4f3a2b1c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create admin_users table ──────────────────────────────────────────────
    op.create_table(
        "admin_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("email", name="uq_admin_users_email"),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"])

    # ── Drop role column from users ───────────────────────────────────────────
    op.drop_column("users", "role")


def downgrade() -> None:
    # Restore role column (existing rows get the 'user' default)
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            server_default="user",
            nullable=False,
        ),
    )

    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
