from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MeetingTypeBase(BaseModel):
    type_name: str
    description: Optional[str] = None

class MeetingTypeCreate(MeetingTypeBase):
    pass

class MeetingTypeRead(MeetingTypeBase):
    id: int
    class Config:
        orm_mode = True

class MeetingBase(BaseModel):
    project_id: int
    started_by: int
    meeting_type_id: int
    notes: Optional[str] = None

class MeetingCreate(MeetingBase):
    pass

class MeetingRead(MeetingBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True


class AudioFileBase(BaseModel):
    meeting_id: int
    s3_key: str
    duration: Optional[int] = None

class AudioFileCreate(AudioFileBase):
    pass

class AudioFileRead(AudioFileBase):
    id: int
    uploaded_at: datetime
    class Config:
        orm_mode = True

class TranscriptBase(BaseModel):
    meeting_id: int
    text: Optional[str] = None

class TranscriptCreate(TranscriptBase):
    pass

class TranscriptRead(TranscriptBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True

class SummaryBase(BaseModel):
    meeting_id: int
    summary_text: Optional[str] = None

class SummaryCreate(SummaryBase):
    pass

class SummaryRead(SummaryBase):
    id: int
    created_at: datetime
    class Config:
        orm_mode = True 