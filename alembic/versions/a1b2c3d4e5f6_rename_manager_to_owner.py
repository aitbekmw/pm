"""rename project access manager to owner

Revision ID: a1b2c3d4e5f6
Revises: d720bdf2d2a5
Create Date: 2026-03-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'd720bdf2d2a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename 'Manager' to 'Owner' in project_access table
    op.execute(
        "UPDATE project_access SET role = 'Owner' WHERE role = 'Manager'"
    )


def downgrade() -> None:
    # Revert 'Owner' to 'Manager'
    # Note: this will also revert any legitimately created 'Owner' roles back to 'Manager'
    op.execute(
        "UPDATE project_access SET role = 'Manager' WHERE role = 'Owner'"
    )
