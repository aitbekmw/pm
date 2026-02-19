"""add importance to meetings

Revision ID: 007_add_importance_to_meetings
Revises: 006_add_project_id_to_notifications
Create Date: 2026-02-12 16:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007_add_importance_to_meetings'
down_revision: Union[str, None] = '006_add_project_id_to_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add importance column with default value 'low'
    op.add_column('meetings', sa.Column('importance', sa.String(), server_default='low', nullable=False))


def downgrade() -> None:
    op.drop_column('meetings', 'importance')
