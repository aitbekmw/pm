"""Add notes field to meetings table

Revision ID: 003
Revises: 002
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поле notes в таблицу meetings
    op.add_column('meetings', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    # Удаляем поле notes из таблицы meetings
    op.drop_column('meetings', 'notes')

