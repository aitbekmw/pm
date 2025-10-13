from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    confluence_data: Optional[dict] = None
    jira_data: Optional[dict] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    confluence_data: Optional[dict] = None
    jira_data: Optional[dict] = None


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


class ProjectListOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_archived: bool
    members_count: Optional[int] = 0
    meetings_count: Optional[int] = 0
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

