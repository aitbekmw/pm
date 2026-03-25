"""add push_tokens table

Revision ID: 010_add_push_tokens
Revises: 009_add_subtitle_to_meetings
Create Date: 2026-03-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_add_push_tokens'
down_revision: Union[str, None] = '009_add_subtitle_to_meetings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'push_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('device_type', sa.String(16), nullable=True),  # 'ios' | 'android'
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_push_tokens_user_id', 'push_tokens', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_push_tokens_user_id', table_name='push_tokens')
    op.drop_table('push_tokens')

