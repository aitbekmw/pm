from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool


class UserOut(BaseModel):
    id: int
    ad_account: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    company_id: Optional[int] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class UserUpdateRole(BaseModel):
    role: str  # Member | Manager | Admin | Backend Dev | Frontend Dev | Designer | QA


class UserList(BaseModel):
    users: List[UserOut]
    total: int
