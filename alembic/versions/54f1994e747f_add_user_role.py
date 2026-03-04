"""add_user_role

Revision ID: 54f1994e747f
Revises: 
Create Date: 2026-03-04 16:39:36.642059

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '54f1994e747f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=20), server_default='user', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'role')
