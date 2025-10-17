from sqladmin import Admin, ModelView
from src.db.session import async_engine
from src.users.models import User
from src.projects.models import Project
from src.meetings.models import Meeting
from src.core.admin_auth import AdminAuthenticationBackend
from starlette.middleware.sessions import SessionMiddleware

USER_ROLE_CHOICES = [
    ("PM", "PM"),
    ("Member", "Member"),
    ("Manager", "Manager"),
    ("Backend Dev", "Backend Dev"),
    ("Frontend Dev", "Frontend Dev"),
    ("Designer", "Designer"),
    ("QA", "QA"),
]

class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [User.id, User.ad_account, User.first_name, User.last_name, User.role, User.is_active]
    column_searchable_list = [User.ad_account, User.first_name, User.last_name]
    column_sortable_list = [User.id, User.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 20

    form_choices = {
        "role": USER_ROLE_CHOICES
    }

class ProjectAdmin(ModelView, model=Project):
    name = "Project"
    name_plural = "Projects"
    icon = "fa-solid fa-project-diagram"
    column_list = [Project.id, Project.name, Project.description, Project.created_by, Project.is_archived, Project.created_at]
    column_searchable_list = [Project.name, Project.description]
    column_sortable_list = [Project.id, Project.created_at]
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 20


class MeetingAdmin(ModelView, model=Meeting):
    name = "Meeting"
    name_plural = "Meetings"
    icon = "fa-solid fa-calendar"
    column_list = [Meeting.id, Meeting.title, Meeting.project_id, Meeting.organizer_id, Meeting.meeting_date, Meeting.duration]
    column_searchable_list = [Meeting.title, Meeting.comments]
    column_sortable_list = [Meeting.id, Meeting.meeting_date]
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 20


def setup_admin(app):
    """Setup admin panel for the FastAPI application with AD authentication"""
    app.add_middleware(SessionMiddleware, secret_key="admin-secret-key-change-in-production")
    
    authentication_backend = AdminAuthenticationBackend(secret_key="admin-secret-key-change-in-production")
    
    admin = Admin(
        app, 
        async_engine, 
        authentication_backend=authentication_backend, 
        title="PM Assistant Admin"
    )
    admin.add_view(UserAdmin)
    admin.add_view(ProjectAdmin)
    admin.add_view(MeetingAdmin)
    
    return admin
