"""add admin_password column

Revision ID: 008_add_admin_password
Revises: 007_add_importance
Create Date: 2026-02-27 09:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008_add_admin_password'
down_revision: Union[str, None] = '007_add_importance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add admin_password column
    op.add_column('users', sa.Column('admin_password', sa.String(), nullable=True))


def downgrade() -> None:
    # Drop admin_password column
    op.drop_column('users', 'admin_password')
