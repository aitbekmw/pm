"""add audio_content_type to meetings

Revision ID: f1a2b3c4d5e6
Revises: e1b2c3d4e5f7
Create Date: 2026-03-27 07:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('meetings', sa.Column('audio_content_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('meetings', 'audio_content_type')
