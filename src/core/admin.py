from crudadmin import CRUDAdmin
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.session import engine, get_session
from src.users.models import User
from src.projects.models import Project
from src.meetings.models import Meeting, MeetingProcessing, Transcript, Summary, Note, ActionItem


class CRUDAdminConfig:
    """Configuration for CRUDAdmin panel"""
    
    # Admin title and base configuration
    title = "PM Assistant Admin"
    logo_url = None
    
    # Models to manage
    models = [
        User,
        Project,
        Meeting,
        MeetingProcessing,
        Transcript,
        Summary,
        Note,
        ActionItem,
    ]


def setup_admin(app):
    """
    Setup CRUDAdmin panel for FastAPI application
    
    CRUDAdmin provides:
    - Automatic CRUD operations for models
    - User authentication and authorization
    - Database initialization
    - Admin interface
    """
    admin = CRUDAdmin(
        app=app,
        engine=engine,
        title=CRUDAdminConfig.title,
        models=CRUDAdminConfig.models,
    )
    
    return admin
