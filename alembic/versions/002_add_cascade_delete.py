"""Add CASCADE DELETE constraints to foreign keys

Revision ID: 002
Revises: 001
Create Date: 2025-10-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old foreign key constraints and recreate with CASCADE
    
    # ProjectAccess.project_id
    op.drop_constraint('project_access_project_id_fkey', 'project_access', type_='foreignkey')
    op.create_foreign_key(
        'project_access_project_id_fkey',
        'project_access',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Meeting.project_id
    op.drop_constraint('meetings_project_id_fkey', 'meetings', type_='foreignkey')
    op.create_foreign_key(
        'meetings_project_id_fkey',
        'meetings',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # MeetingProcessing.meeting_id
    op.drop_constraint('meeting_processing_meeting_id_fkey', 'meeting_processing', type_='foreignkey')
    op.create_foreign_key(
        'meeting_processing_meeting_id_fkey',
        'meeting_processing',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Transcript.meeting_id
    op.drop_constraint('transcripts_meeting_id_fkey', 'transcripts', type_='foreignkey')
    op.create_foreign_key(
        'transcripts_meeting_id_fkey',
        'transcripts',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Summary.meeting_id
    op.drop_constraint('summaries_meeting_id_fkey', 'summaries', type_='foreignkey')
    op.create_foreign_key(
        'summaries_meeting_id_fkey',
        'summaries',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Note.meeting_id
    op.drop_constraint('notes_meeting_id_fkey', 'notes', type_='foreignkey')
    op.create_foreign_key(
        'notes_meeting_id_fkey',
        'notes',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # ActionItem.meeting_id
    op.drop_constraint('action_items_meeting_id_fkey', 'action_items', type_='foreignkey')
    op.create_foreign_key(
        'action_items_meeting_id_fkey',
        'action_items',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE'
    )
    
    # Notification.meeting_id
    op.drop_constraint('notifications_meeting_id_fkey', 'notifications', type_='foreignkey')
    op.create_foreign_key(
        'notifications_meeting_id_fkey',
        'notifications',
        'meetings',
        ['meeting_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Revert CASCADE DELETE to previous constraints (without CASCADE)
    
    op.drop_constraint('project_access_project_id_fkey', 'project_access', type_='foreignkey')
    op.create_foreign_key(
        'project_access_project_id_fkey',
        'project_access',
        'projects',
        ['project_id'],
        ['id']
    )
    
    op.drop_constraint('meetings_project_id_fkey', 'meetings', type_='foreignkey')
    op.create_foreign_key(
        'meetings_project_id_fkey',
        'meetings',
        'projects',
        ['project_id'],
        ['id']
    )
    
    op.drop_constraint('meeting_processing_meeting_id_fkey', 'meeting_processing', type_='foreignkey')
    op.create_foreign_key(
        'meeting_processing_meeting_id_fkey',
        'meeting_processing',
        'meetings',
        ['meeting_id'],
        ['id']
    )
    
    op.drop_constraint('transcripts_meeting_id_fkey', 'transcripts', type_='foreignkey')
    op.create_foreign_key(
        'transcripts_meeting_id_fkey',
        'transcripts',
        'meetings',
        ['meeting_id'],
        ['id']
    )
    
    op.drop_constraint('summaries_meeting_id_fkey', 'summaries', type_='foreignkey')
    op.create_foreign_key(
        'summaries_meeting_id_fkey',
        'summaries',
        'meetings',
        ['meeting_id'],
        ['id']
    )
    
    op.drop_constraint('notes_meeting_id_fkey', 'notes', type_='foreignkey')
    op.create_foreign_key(
        'notes_meeting_id_fkey',
        'notes',
        'meetings',
        ['meeting_id'],
        ['id']
    )
    
    op.drop_constraint('action_items_meeting_id_fkey', 'action_items', type_='foreignkey')
    op.create_foreign_key(
        'action_items_meeting_id_fkey',
        'action_items',
        'meetings',
        ['meeting_id'],
        ['id']
    )
    
    op.drop_constraint('notifications_meeting_id_fkey', 'notifications', type_='foreignkey')
    op.create_foreign_key(
        'notifications_meeting_id_fkey',
        'notifications',
        'meetings',
        ['meeting_id'],
        ['id']
    )
