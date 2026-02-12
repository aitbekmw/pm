"""add project_id to notifications

Revision ID: e152f4d2c963
Revises: 005_add_company_entity
Create Date: 2026-02-12 15:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e152f4d2c963'
down_revision: Union[str, None] = '005_add_company_entity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('project_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'notifications', 'projects', ['project_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint(None, 'notifications', type_='foreignkey')
    op.drop_column('notifications', 'project_id')
