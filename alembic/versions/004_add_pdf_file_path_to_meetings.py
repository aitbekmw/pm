"""Add pdf_file_path field to meetings table

Revision ID: 004
Revises: 003
Create Date: 2025-01-27 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поле pdf_file_path в таблицу meetings
    op.add_column('meetings', sa.Column('pdf_file_path', sa.String(), nullable=True))


def downgrade() -> None:
    # Удаляем поле pdf_file_path из таблицы meetings
    op.drop_column('meetings', 'pdf_file_path')

