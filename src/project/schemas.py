from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ProjectBase(BaseModel):
    name: str
    created_by: int

class ProjectCreate(ProjectBase):
    pass

class ProjectRead(ProjectBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True

class ProjectMembershipBase(BaseModel):
    user_id: int
    project_id: int

class ProjectMembershipCreate(ProjectMembershipBase):
    pass

class ProjectMembershipRead(ProjectMembershipBase):
    id: int
    joined_at: datetime
    class Config:
        orm_mode = True 