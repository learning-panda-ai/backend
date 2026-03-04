"""add_ingest_tracking_to_uploaded_files

Revision ID: f7a6b5c4d3e2
Revises: e6f5a4b3c2d1
Create Date: 2026-03-04 00:00:00.000000

Changes:
- DROP old FK constraint on uploaded_files.uploaded_by (was → users.id)
- ADD new FK constraint on uploaded_files.uploaded_by (→ admin_users.id)
- ADD COLUMN ingest_status  VARCHAR(20)  NOT NULL DEFAULT 'pending'
- ADD COLUMN celery_task_id VARCHAR(255) NULL
- ADD COLUMN ingested_at    TIMESTAMPTZ  NULL
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f7a6b5c4d3e2"
down_revision: Union[str, Sequence[str], None] = "e6f5a4b3c2d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Fix uploaded_by FK: users → admin_users ───────────────────────────────
    op.drop_constraint(
        "uploaded_files_uploaded_by_fkey",
        "uploaded_files",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_uploaded_files_admin_users",
        "uploaded_files",
        "admin_users",
        ["uploaded_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Add ingest tracking columns ───────────────────────────────────────────
    op.add_column(
        "uploaded_files",
        sa.Column(
            "ingest_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("celery_task_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("uploaded_files", "ingested_at")
    op.drop_column("uploaded_files", "celery_task_id")
    op.drop_column("uploaded_files", "ingest_status")

    op.drop_constraint(
        "fk_uploaded_files_admin_users",
        "uploaded_files",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "uploaded_files_uploaded_by_fkey",
        "uploaded_files",
        "users",
        ["uploaded_by"],
        ["id"],
        ondelete="SET NULL",
    )
