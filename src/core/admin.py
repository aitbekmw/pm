from datetime import datetime

from sqladmin import Admin, ModelView, BaseView, expose
from fastapi import Request
from sqlalchemy import select, func
from src.db.session import async_engine, AsyncSessionLocal

from src.companies.models import Company
from src.users.models import User
from src.projects.models import Project
from src.meetings.models import Meeting
from src.faq.models import FAQ
from src.core.admin_auth import AdminAuthenticationBackend
from starlette.middleware.sessions import SessionMiddleware
from wtforms import SelectField


USER_ROLE_CHOICES = [
    ("Manager", "Manager"),
    ("Member", "Member"),
    ("Admin", "Admin"),
    ("Backend Dev", "Backend Dev"),
    ("Frontend Dev", "Frontend Dev"),
    ("Designer", "Designer"),
    ("QA", "QA"),
]


class BaseAdmin(ModelView):
    column_type_formatters = {
        datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if v else "",
        bool: lambda v: "✅" if v else "❌"
    }


class RestrictedModelView(BaseAdmin):
    def is_visible(self, request: Request) -> bool:
        return request.session.get("company_name") == "MDigital"

    def is_accessible(self, request: Request) -> bool:
        return request.session.get("company_name") == "MDigital"


class CompanyFilteredAdmin(BaseAdmin):
    def is_visible(self, request: Request) -> bool:
        return True

    def is_accessible(self, request: Request) -> bool:
        return True

    def list_query(self, request: Request) -> select:
        stmt = super().list_query(request)
        company_name = request.session.get("company_name")
        if company_name and company_name != "MDigital":
            stmt = stmt.where(self.model.company.has(Company.name == company_name))
        return stmt

    def count_query(self, request: Request) -> select:
        stmt = super().count_query(request)
        company_name = request.session.get("company_name")
        if company_name and company_name != "MDigital":
            stmt = stmt.where(self.model.company.has(Company.name == company_name))
        return stmt


class CompanyAdmin(RestrictedModelView, model=Company):
    name = "Компания"
    name_plural = "Компании"
    icon = "fa-solid fa-building"

    column_list = [Company.name, Company.slug, Company.created_at]
    column_details_list = [Company.name, Company.slug, Company.created_at, Company.updated_at]
    column_searchable_list = [Company.name, Company.slug]
    column_sortable_list = [Company.name, Company.created_at]

    column_labels = {
        Company.name: "Название",
        Company.slug: "Slug",
        Company.created_at: "Дата создания",
        Company.updated_at: "Дата обновления",
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 25

    form_columns = [Company.name, Company.slug]


class UserAdmin(CompanyFilteredAdmin, model=User):
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"

    column_list = [User.company, User.first_name, User.last_name, User.ad_account, User.role, User.is_active, User.created_at]
    column_details_list = [
        User.company, User.first_name, User.last_name,
        User.ad_account, User.role, User.is_active, User.created_at, User.updated_at,
    ]
    column_select_related = [User.company]
    column_searchable_list = ["company.name", User.ad_account, User.first_name, User.last_name]
    column_sortable_list = [User.first_name, User.last_name, User.role, User.is_active, User.created_at]

    column_labels = {
        User.company: "Компания",
        "company.name": "Компания",
        User.ad_account: "Логин (AD)",
        User.first_name: "Имя",
        User.last_name: "Фамилия",
        User.role: "Роль",
        User.is_active: "Активен",
        User.created_at: "Дата создания",
        User.updated_at: "Дата обновления",
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 25

    form_columns = [User.company, User.ad_account, User.first_name, User.last_name, User.role, User.is_active]

    form_overrides = {
        "role": SelectField,
    }

    form_args = {
        "role": {
            "choices": USER_ROLE_CHOICES,
            "coerce": str,
        }
    }


class ProjectAdmin(RestrictedModelView, model=Project):
    name = "Проект"
    name_plural = "Проекты"
    icon = "fa-solid fa-diagram-project"

    column_list = [Project.company, Project.name, Project.is_archived, Project.created_at]
    column_details_list = [
        Project.company, Project.name, Project.description,
        Project.is_archived, Project.created_at, Project.updated_at,
    ]
    column_searchable_list = [Project.name, Project.description, "company.name"]
    column_sortable_list = [Project.company, Project.name, Project.is_archived, Project.created_at]

    column_labels = {
        "company.name": "Компания",
        Project.company: "Компания",
        Project.name: "Название",
        Project.description: "Описание",
        Project.is_archived: "Архивирован",
        Project.created_by: "Создал",
        Project.created_at: "Дата создания",
        Project.updated_at: "Дата обновления",
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 25

    form_columns = [
        Project.company,
        Project.name,
        Project.description,
        Project.is_archived,
    ]


class MeetingAdmin(RestrictedModelView, model=Meeting):
    name = "Встреча"
    name_plural = "Встречи"
    icon = "fa-solid fa-calendar-days"

    column_list = [
        Meeting.company, Meeting.title, Meeting.organizer,
        Meeting.meeting_date, Meeting.duration, Meeting.importance, Meeting.created_at,
    ]
    column_details_list = [
        Meeting.company, Meeting.title, Meeting.organizer,
        Meeting.project_id, Meeting.meeting_date, Meeting.duration,
        Meeting.importance, Meeting.comments, Meeting.notes,
        Meeting.audio_file_path, Meeting.audio_file_size, Meeting.created_at, Meeting.updated_at,
    ]
    column_searchable_list = [Meeting.title, Meeting.comments, "company.name"]
    column_sortable_list = [Meeting.company, Meeting.title, Meeting.meeting_date, Meeting.importance, Meeting.created_at]

    column_labels = {
        "company.name": "Компания",
        Meeting.company: "Компания",
        Meeting.title: "Название",
        Meeting.organizer: "Организатор",
        Meeting.meeting_date: "Дата встречи",
        Meeting.duration: "Длительность",
        Meeting.importance: "Важность",
        Meeting.comments: "Комментарии",
        Meeting.notes: "Заметки",
        Meeting.audio_file_path: "Аудио путь",
        Meeting.audio_file_size: "Размер аудио",
        Meeting.created_at: "Дата создания",
        Meeting.updated_at: "Дата обновления",
    }

    column_formatters = {
        Meeting.duration: lambda m, a: f"{getattr(m, a, 0) // 60}:{getattr(m, a, 0) % 60:02d}" if getattr(m, a) else "0:00"
    }

    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 25

    form_columns = [
        Meeting.title,
        Meeting.importance,
        Meeting.comments,
        Meeting.notes,
    ]


class FAQAdmin(RestrictedModelView, model=FAQ):
    name = "FAQ (Ответы на вопросы)"
    name_plural = "FAQ"
    icon = "fa-solid fa-circle-question"

    column_list = [FAQ.question, FAQ.order, FAQ.is_active, FAQ.created_at]
    column_details_list = [
        FAQ.question, FAQ.answer, FAQ.order, FAQ.is_active, 
        FAQ.created_at, FAQ.updated_at
    ]
    column_searchable_list = [FAQ.question, FAQ.answer]
    column_sortable_list = [FAQ.order, FAQ.is_active, FAQ.created_at]

    column_labels = {
        FAQ.question: "Вопрос",
        FAQ.answer: "Ответ",
        FAQ.order: "Порядок",
        FAQ.is_active: "Активен",
        FAQ.created_at: "Дата создания",
        FAQ.updated_at: "Дата обновления",
    }

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    page_size = 25

    form_columns = [
        FAQ.question,
        FAQ.answer,
        FAQ.order,
        FAQ.is_active,
    ]


class AnalyticsView(BaseView):
    name = "Аналитика"
    icon = "fa-solid fa-chart-pie"

    def is_visible(self, request: Request) -> bool:
        return request.session.get("company_name") == "MDigital"

    def is_accessible(self, request: Request) -> bool:
        return request.session.get("company_name") == "MDigital"

    @expose("/analytics", methods=["GET"])
    async def analytics_page(self, request: Request):
        from datetime import datetime
        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        
        start_date = None
        end_date = None
        
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            if end_date_str:
                # Set end_date to end of the day
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

        def apply_date_filter(stmt, model):
            if start_date:
                stmt = stmt.where(model.created_at >= start_date)
            if end_date:
                stmt = stmt.where(model.created_at <= end_date)
            return stmt

        # For Meeting duration sum, we might want to filter by meeting_date or created_at. Let's stick to created_at for consistency.
        # But wait, User, Project, Meeting all have created_at. Company also has created_at.
        
        async with AsyncSessionLocal() as session:
            # === Global Stats ===
            users_count = await session.scalar(apply_date_filter(select(func.count()).select_from(User), User))
            projects_count = await session.scalar(apply_date_filter(select(func.count()).select_from(Project), Project))
            meetings_count = await session.scalar(apply_date_filter(select(func.count()).select_from(Meeting), Meeting))
            companies_count = await session.scalar(apply_date_filter(select(func.count()).select_from(Company), Company))
            
            total_duration_sec = await session.scalar(apply_date_filter(select(func.sum(Meeting.duration)).select_from(Meeting), Meeting))
            total_duration_hours = (total_duration_sec or 0) / 3600.0

            # === Grouped Stats (by Company) ===
            users_by_company = (await session.execute(
                apply_date_filter(select(Company.name, func.count(User.id)).outerjoin(User, Company.id == User.company_id), User)
                .group_by(Company.name)
            )).all()

            projects_by_company = (await session.execute(
                apply_date_filter(select(Company.name, func.count(Project.id)).outerjoin(Project, Company.id == Project.company_id), Project)
                .group_by(Company.name)
            )).all()

            meetings_by_company = (await session.execute(
                apply_date_filter(select(Company.name, func.count(Meeting.id)).outerjoin(Meeting, Company.id == Meeting.company_id), Meeting)
                .group_by(Company.name)
            )).all()

            duration_by_company = (await session.execute(
                apply_date_filter(select(Company.name, func.sum(Meeting.duration)).outerjoin(Meeting, Company.id == Meeting.company_id), Meeting)
                .group_by(Company.name)
            )).all()

        context = {
            "request": request,
            "start_date": start_date_str or "",
            "end_date": end_date_str or "",
            # Global
            "users_count": users_count,
            "projects_count": projects_count,
            "meetings_count": meetings_count,
            "companies_count": companies_count,
            "total_duration_hours": round(total_duration_hours, 1),
            # Grouped (for charts)
            "users_by_company": {row[0]: row[1] for row in users_by_company},
            "projects_by_company": {row[0]: row[1] for row in projects_by_company},
            "meetings_by_company": {row[0]: row[1] for row in meetings_by_company},
            "duration_by_company": {row[0]: round(float(row[1] or 0) / 3600.0, 1) for row in duration_by_company},
        }
        return await self.templates.TemplateResponse(request, "admin/analytics.html", context=context)


def setup_admin(app):
    """Setup admin panel for the FastAPI application."""
    app.add_middleware(SessionMiddleware, secret_key="admin-secret-key-change-in-production")

    authentication_backend = AdminAuthenticationBackend(secret_key="admin-secret-key-change-in-production")

    admin = Admin(
        app,
        async_engine,
        authentication_backend=authentication_backend,
        title="PM Assistant Admin",
        templates_dir="templates",
    )
    admin.add_view(AnalyticsView)
    admin.add_view(CompanyAdmin)
    admin.add_view(UserAdmin)
    admin.add_view(ProjectAdmin)
    admin.add_view(MeetingAdmin)
    admin.add_view(FAQAdmin)
    # admin.add_view(MeetingProcessingAdmin)
    # admin.add_view(TranscriptAdmin)
    
    return admin
