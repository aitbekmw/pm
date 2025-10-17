from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class MeetingBase(BaseModel):
    title: str
    project_id: Optional[int] = None
    meeting_date: datetime
    duration: Optional[int] = None
    comments: Optional[str] = None


class MeetingCreate(BaseModel):
    title: str
    project_id: Optional[int] = None
    meeting_date: Optional[datetime] = None
    comments: Optional[str] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[int] = None
    meeting_date: Optional[datetime] = None
    duration: Optional[int] = None
    comments: Optional[str] = None


class MeetingOut(BaseModel):
    id: int
    title: str
    project_id: Optional[int]
    organizer_id: Optional[int]
    meeting_date: datetime
    duration: Optional[int]
    audio_file_path: Optional[str]
    audio_file_size: Optional[int]
    comments: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class MeetingListOut(BaseModel):
    id: int
    title: str
    project_id: Optional[int]
    organizer_id: Optional[int]
    meeting_date: datetime
    duration: Optional[int]
    comments: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class TranscriptOut(BaseModel):
    id: int
    meeting_id: int
    content: Optional[str]
    timestamps: Optional[dict]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class SummaryOut(BaseModel):
    id: int
    meeting_id: int
    content: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class NoteCreate(BaseModel):
    content: str


class NoteUpdate(BaseModel):
    content: str


class NoteOut(BaseModel):
    id: int
    meeting_id: int
    content: Optional[str]
    created_by: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ActionItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    due_date: Optional[datetime] = None


class ActionItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None


class ActionItemOut(BaseModel):
    id: int
    meeting_id: int
    title: Optional[str]
    description: Optional[str]
    assignee_id: Optional[int]
    status: Optional[str]
    due_date: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class MeetingDetailsOut(BaseModel):
    meeting: MeetingOut
    transcript: Optional[TranscriptOut] = None
    summary: Optional[SummaryOut] = None
    notes: list[NoteOut] = []
    action_items: list[ActionItemOut] = []

    class Config:
        from_attributes = True


class MeetingsFilterParams(BaseModel):
    """Параметры для фильтрации встреч"""
    organizer_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_duration: Optional[int] = None
    max_duration: Optional[int] = None
    sort_by: str = "date_desc"  # date_asc, date_desc, duration_asc, duration_desc
    
    class Config:
        json_schema_extra = {
            "example": {
                "organizer_id": 1,
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
                "min_duration": 30,
                "max_duration": 120,
                "sort_by": "date_desc"
            }
        }

