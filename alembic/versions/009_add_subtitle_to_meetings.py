"""add subtitle column to meetings

Revision ID: 009_add_subtitle_to_meetings
Revises: 008_add_admin_password
Create Date: 2026-03-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_add_subtitle_to_meetings'
down_revision: Union[str, None] = '008_add_admin_password'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add subtitle column to meetings table
    op.add_column('meetings', sa.Column('subtitle', sa.Text(), nullable=True))


def downgrade() -> None:
    # Drop subtitle column from meetings table
    op.drop_column('meetings', 'subtitle')

