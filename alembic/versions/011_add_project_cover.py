"""add cover field to projects table

Revision ID: 011_add_project_cover
Revises: 010_add_push_tokens
Create Date: 2026-03-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011_add_project_cover'
down_revision: Union[str, None] = '010_add_push_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('cover', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'cover')

