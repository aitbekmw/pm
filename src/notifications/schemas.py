from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NotificationOut(BaseModel):
    id: int
    user_id: Optional[int]
    meeting_id: Optional[int]
    type: Optional[str]
    title: Optional[str]
    message: Optional[str]
    is_read: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    user_id: int
    meeting_id: Optional[int] = None
    type: str
    title: str
    message: Optional[str] = None


class NotificationUpdate(BaseModel):
    is_read: bool

