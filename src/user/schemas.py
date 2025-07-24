from pydantic import BaseModel, EmailStr
from typing import Optional

class RoleBase(BaseModel):
    role_name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    pass

class RoleRead(RoleBase):
    class Config:
        orm_mode = True

class UserBase(BaseModel):
    name: str
    email: EmailStr
    ad_id: str
    role_name: str

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: int
    role: Optional[RoleRead]
    class Config:
        orm_mode = True 