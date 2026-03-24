from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    confluence_data: Optional[dict] = None
    jira_data: Optional[dict] = None
    cover: Optional[str] = None


class ProjectUserCreate(BaseModel):
    """Пользователь для добавления в проект при создании"""
    id: int
    role: Optional[str] = None


class ProjectCreate(ProjectBase):
    users: Optional[list[ProjectUserCreate]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    confluence_data: Optional[dict] = None
    jira_data: Optional[dict] = None
    cover: Optional[str] = None


class ProjectOut(ProjectBase):
    id: int
    is_archived: bool
    created_by: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    members_count: Optional[int] = 0
    meetings_count: Optional[int] = 0

    class Config:
        from_attributes = True


class ProjectAccessBase(BaseModel):
    user_id: int
    role: Optional[str] = None


class ProjectAccessCreate(ProjectAccessBase):
    pass


class ProjectAccessOut(ProjectAccessBase):
    id: int
    project_id: int
    granted_at: Optional[datetime]

    class Config:
        from_attributes = True


class UserAccessInfo(BaseModel):
    """Информация о пользователе для доступа к проекту"""
    id: int
    ad_account: str  # username
    first_name: str
    last_name: str
    role: str

    class Config:
        from_attributes = True
    
    @property
    def full_name(self) -> str:
        """Полное имя пользователя"""
        return f"{self.first_name} {self.last_name}".strip()


class ProjectAccessOutWithUser(ProjectAccessBase):
    """Доступ к проекту с информацией о пользователе"""
    id: int
    project_id: int
    user: Optional[UserAccessInfo] = None
    granted_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectListOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    cover: Optional[str] = None
    is_archived: bool
    members_count: Optional[int] = 0
    meetings_count: Optional[int] = 0
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectCoverUploadResponse(BaseModel):
    """Ответ при загрузке обложки"""
    id: int
    cover: Optional[str]
    message: str

    class Config:
        from_attributes = True


class ProjectCoverUrlResponse(BaseModel):
    """Ответ с URL обложки проекта"""
    id: int
    cover_url: Optional[str]

    class Config:
        from_attributes = True


