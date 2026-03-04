"""create_uploaded_files_table

Revision ID: b3c2d1e4f5a6
Revises: 54f1994e747f
Create Date: 2026-03-04 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "b3c2d1e4f5a6"
down_revision: Union[str, Sequence[str], None] = "54f1994e747f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("s3_url", sa.String(2048), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("board", sa.String(50), nullable=False),
        sa.Column("standard", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column(
            "uploaded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_uploaded_files_board", "uploaded_files", ["board"])
    op.create_index("ix_uploaded_files_standard", "uploaded_files", ["standard"])
    op.create_index("ix_uploaded_files_subject", "uploaded_files", ["subject"])
    op.create_index("ix_uploaded_files_uploaded_by", "uploaded_files", ["uploaded_by"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_uploaded_by", "uploaded_files")
    op.drop_index("ix_uploaded_files_subject", "uploaded_files")
    op.drop_index("ix_uploaded_files_standard", "uploaded_files")
    op.drop_index("ix_uploaded_files_board", "uploaded_files")
    op.drop_table("uploaded_files")
