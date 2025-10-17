from sqladmin import Admin, ModelView
from src.db.session import async_engine
from src.users.models import User
from src.projects.models import Project
from src.meetings.models import Meeting


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
    """Setup admin panel for the FastAPI application"""
    admin = Admin(app, async_engine, authentication_backend=None, title="PM Assistant Admin")
    admin.register_model(UserAdmin)
    admin.register_model(ProjectAdmin)
    admin.register_model(MeetingAdmin)
    
    return admin
