"""add company entity

Revision ID: 005_add_company_entity
Revises: 004_add_pdf_file_path_to_meetings
Create Date: 2026-02-09 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_add_company_entity'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create companies table
    op.create_table('companies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_companies_id'), 'companies', ['id'], unique=False)
    op.create_index(op.f('ix_companies_slug'), 'companies', ['slug'], unique=True)

    # 2. Add company_id to users
    op.add_column('users', sa.Column('company_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'users', 'companies', ['company_id'], ['id'])
    # TODO: make company_id NOT NULL after backfill

    # 3. Add company_id to projects
    op.add_column('projects', sa.Column('company_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'projects', 'companies', ['company_id'], ['id'])
    # TODO: make company_id NOT NULL after backfill

    # 4. Add company_id to meetings
    op.add_column('meetings', sa.Column('company_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'meetings', 'companies', ['company_id'], ['id'])
    # TODO: make company_id NOT NULL after backfill


def downgrade() -> None:
    # 1. Remove company_id from meetings
    op.drop_constraint(None, 'meetings', type_='foreignkey')
    op.drop_column('meetings', 'company_id')

    # 2. Remove company_id from projects
    op.drop_constraint(None, 'projects', type_='foreignkey')
    op.drop_column('projects', 'company_id')

    # 3. Remove company_id from users
    op.drop_constraint(None, 'users', type_='foreignkey')
    op.drop_column('users', 'company_id')

    # 4. Drop companies table
    op.drop_index(op.f('ix_companies_slug'), table_name='companies')
    op.drop_index(op.f('ix_companies_id'), table_name='companies')
    op.drop_table('companies')
