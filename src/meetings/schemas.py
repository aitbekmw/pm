from pydantic import BaseModel, field_serializer, ConfigDict, model_validator
from typing import Optional
from datetime import datetime
from src.core.storage import storage


class OrganizerInfo(BaseModel):
    """Информация об организаторе встречи"""
    id: int
    ad_account: str
    first_name: str
    last_name: str
    
    model_config = ConfigDict(from_attributes=True)
    
    @property
    def full_name(self) -> str:
        """Полное имя организатора"""
        return f"{self.first_name} {self.last_name}".strip()


class MeetingBase(BaseModel):
    title: str
    project_id: Optional[int] = None
    meeting_date: datetime
    duration: Optional[int] = None
    comments: Optional[str] = None
    importance: str = "low"  # low | middle | high


class MeetingCreate(BaseModel):
    title: str
    subtitle: Optional[str] = None
    project_id: Optional[int] = None
    meeting_date: Optional[datetime] = None
    comments: Optional[str] = None
    notes: Optional[str] = None
    duration: Optional[int] = None  # Длительность в секундах
    importance: str = "low"


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[int] = None
    meeting_date: Optional[datetime] = None
    duration: Optional[int] = None  # Длительность в секундах
    comments: Optional[str] = None
    notes: Optional[str] = None
    importance: Optional[str] = None


class MeetingOut(BaseModel):
    id: int
    title: str
    subtitle: Optional[str] = None
    project_id: Optional[int]
    organizer_name: Optional[str] = None
    meeting_date: datetime
    duration: Optional[int] = None  # Длительность в секундах
    importance: str
    audio_file_path: Optional[str]
    audio_file_size: Optional[int]
    pdf_file_path: Optional[str] = None
    comments: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
    
    @model_validator(mode='before')
    @classmethod
    def convert_fields(cls, data):
        """Получает имя организатора"""
        if isinstance(data, dict):
            # Получаем имя организатора
            organizer_name = None
            if 'organizer' in data and data['organizer']:
                organizer = data['organizer']
                if hasattr(organizer, 'first_name') and hasattr(organizer, 'last_name'):
                    organizer_name = f"{organizer.first_name} {organizer.last_name}".strip()
            elif 'organizer_id' in data and data['organizer_id']:
                # Если organizer не загружен, но есть organizer_id, оставляем None
                pass
            data['organizer_name'] = organizer_name
            # Удаляем organizer_id и organizer из данных, чтобы они не попадали в ответ
            data.pop('organizer_id', None)
            data.pop('organizer', None)
        elif hasattr(data, 'organizer'):
            # Обрабатываем объект SQLAlchemy
            organizer_name = None
            if data.organizer:
                organizer = data.organizer
                if hasattr(organizer, 'first_name') and hasattr(organizer, 'last_name'):
                    organizer_name = f"{organizer.first_name} {organizer.last_name}".strip()
            data.organizer_name = organizer_name
        return data
    
    @field_serializer('audio_file_path')
    def serialize_audio_file_path(self, value: Optional[str], _info):
        """Генерирует прямую ссылку на аудиофайл через nginx прокси"""
        if value:
            return storage.generate_direct_url(value)
        return None
    
    @field_serializer('pdf_file_path')
    def serialize_pdf_file_path(self, value: Optional[str], _info):
        """Генерирует прямую ссылку на PDF файл через nginx прокси"""
        if value:
            return storage.generate_direct_url(value)
        return None


class MeetingListOut(BaseModel):
    id: int
    title: str
    project_id: Optional[int]
    organizer_name: Optional[str] = None
    meeting_date: datetime
    duration: Optional[int] = None  # Длительность в секундах
    importance: str
    comments: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
    
    @model_validator(mode='before')
    @classmethod
    def convert_fields(cls, data):
        """Получает имя организатора"""
        if isinstance(data, dict):
            # Получаем имя организатора
            organizer_name = None
            if 'organizer' in data and data['organizer']:
                organizer = data['organizer']
                if hasattr(organizer, 'first_name') and hasattr(organizer, 'last_name'):
                    organizer_name = f"{organizer.first_name} {organizer.last_name}".strip()
            elif 'organizer_id' in data and data['organizer_id']:
                # Если organizer не загружен, но есть organizer_id, оставляем None
                pass
            data['organizer_name'] = organizer_name
            # Удаляем organizer_id и organizer из данных, чтобы они не попадали в ответ
            data.pop('organizer_id', None)
            data.pop('organizer', None)
        elif hasattr(data, 'organizer'):
            # Обрабатываем объект SQLAlchemy
            organizer_name = None
            if data.organizer:
                organizer = data.organizer
                if hasattr(organizer, 'first_name') and hasattr(organizer, 'last_name'):
                    organizer_name = f"{organizer.first_name} {organizer.last_name}".strip()
            data.organizer_name = organizer_name
        return data


class MeetingListOutWithOrganizer(BaseModel):
    """Встреча со информацией об организаторе"""
    id: int
    title: str
    project_id: Optional[int]
    organizer_id: Optional[int]
    organizer: Optional[OrganizerInfo] = None
    organizer_name: Optional[str] = None  # Имя организатора для удобства
    meeting_date: datetime
    duration: Optional[int] = None  # Длительность в секундах
    importance: str
    comments: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
    
    @model_validator(mode='before')
    @classmethod
    def convert_fields(cls, data):
        """Получает имя организатора"""
        if isinstance(data, dict):
            # Получаем имя организатора
            organizer_name = None
            if 'organizer' in data and data['organizer']:
                organizer = data['organizer']
                if isinstance(organizer, dict):
                    if 'first_name' in organizer and 'last_name' in organizer:
                        organizer_name = f"{organizer['first_name']} {organizer['last_name']}".strip()
                elif hasattr(organizer, 'first_name') and hasattr(organizer, 'last_name'):
                    organizer_name = f"{organizer.first_name} {organizer.last_name}".strip()
            data['organizer_name'] = organizer_name
        elif hasattr(data, 'organizer'):
            # Обрабатываем объект SQLAlchemy
            organizer_name = None
            if data.organizer:
                organizer = data.organizer
                if hasattr(organizer, 'first_name') and hasattr(organizer, 'last_name'):
                    organizer_name = f"{organizer.first_name} {organizer.last_name}".strip()
            data.organizer_name = organizer_name
        return data
    
    @property
    def organizer_name_property(self) -> Optional[str]:
        """Полное имя организатора (удобно для отображения) - используйте organizer_name поле"""
        if self.organizer:
            return self.organizer.full_name
        return self.organizer_name


class TranscriptOut(BaseModel):
    id: int
    meeting_id: int
    content: Optional[str]
    timestamps: Optional[dict]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class SummaryOut(BaseModel):
    id: int
    meeting_id: int
    content: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class MeetingDetailsOut(BaseModel):
    meeting: MeetingOut
    transcript: Optional[TranscriptOut] = None
    summary: Optional[SummaryOut] = None
    notes: Optional[str] = None
    action_items: list[ActionItemOut] = []
    pdf: Optional[str] = None  # URL для скачивания PDF

    model_config = ConfigDict(from_attributes=True)


class MeetingsFilterParams(BaseModel):
    """Параметры для фильтрации встреч"""
    organizer_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    min_duration: Optional[int] = None
    max_duration: Optional[int] = None
    sort_by: str = "date_desc"  # date_asc, date_desc, duration_asc, duration_desc
    
    model_config = ConfigDict(json_schema_extra={
            "example": {
                "organizer_id": 1,
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
                "min_duration": 30,
                "max_duration": 120,
                "sort_by": "date_desc"
            }
        })

