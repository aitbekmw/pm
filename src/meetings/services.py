from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional, BinaryIO
import uuid
import io

from src.meetings.models import (
    Meeting, Transcript, Summary, Note, ActionItem, MeetingProcessing
)
from src.meetings.schemas import MeetingCreate, MeetingUpdate
from src.meetings import selectors
from src.core.storage import storage
from src.core.ai_services import ai_service


async def create_meeting(
    db: AsyncSession,
    data: MeetingCreate,
    user_id: int,
    audio_file: Optional[BinaryIO] = None,
    audio_filename: Optional[str] = None
) -> Meeting:
    """Создать новую встречу"""
    # Генерировать уникальное имя файла для S3
    audio_path = None
    audio_size = None
    
    if audio_file:
        file_extension = audio_filename.split('.')[-1] if audio_filename else 'mp3'
        audio_path = f"meetings/{uuid.uuid4()}.wav"
        
        # Загрузить в S3
        audio_file.seek(0, 2)  # Перейти в конец файла
        audio_size = audio_file.tell()  # Получить размер
        audio_file.seek(0)  # Вернуться в начало
        
        storage.upload_file(audio_file, audio_path)
    
    # Если project_id равен 0, преобразуем в None (нет проекта)
    project_id = data.project_id if data.project_id and data.project_id > 0 else None
    
    meeting = Meeting(
        title=data.title,
        project_id=project_id,
        organizer_id=user_id,
        meeting_date=data.meeting_date or datetime.now(timezone.utc),
        comments=data.comments,
        audio_file_path=audio_path,
        audio_file_size=audio_size
    )
    
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    
    return meeting


async def update_meeting(
    db: AsyncSession,
    meeting_id: int,
    data: MeetingUpdate
) -> Optional[Meeting]:
    """Обновить встречу"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(meeting, field, value)
    
    await db.commit()
    await db.refresh(meeting)
    return meeting


async def delete_meeting(db: AsyncSession, meeting_id: int) -> bool:
    """Удалить встречу"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        return False
    
    # Удалить аудио из S3
    if meeting.audio_file_path:
        storage.delete_file(meeting.audio_file_path)
    
    await db.delete(meeting)
    await db.commit()
    return True


async def move_meeting_to_project(
    db: AsyncSession,
    meeting_id: int,
    project_id: Optional[int]
) -> Optional[Meeting]:
    """Переместить встречу в другой проект"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        return None
    
    meeting.project_id = project_id
    await db.commit()
    await db.refresh(meeting)
    return meeting


async def create_note(
    db: AsyncSession,
    meeting_id: int,
    content: str,
    user_id: int
) -> Note:
    """Создать заметку для встречи"""
    note = Note(
        meeting_id=meeting_id,
        content=content,
        created_by=user_id
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def update_note(
    db: AsyncSession,
    note_id: int,
    content: str
) -> Optional[Note]:
    """Обновить заметку"""
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalars().first()
    
    if not note:
        return None
    
    note.content = content
    await db.commit()
    await db.refresh(note)
    return note


async def delete_note(db: AsyncSession, note_id: int) -> bool:
    """Удалить заметку"""
    result = await db.execute(select(Note).where(Note.id == note_id))
    note = result.scalars().first()
    
    if not note:
        return False
    
    await db.delete(note)
    await db.commit()
    return True


async def create_action_item(
    db: AsyncSession,
    meeting_id: int,
    title: str,
    description: Optional[str] = None,
    assignee_id: Optional[int] = None,
    due_date: Optional[datetime] = None
) -> ActionItem:
    """Создать action item"""
    action_item = ActionItem(
        meeting_id=meeting_id,
        title=title,
        description=description,
        assignee_id=assignee_id,
        status="pending",
        due_date=due_date
    )
    db.add(action_item)
    await db.commit()
    await db.refresh(action_item)
    return action_item


async def update_action_item(
    db: AsyncSession,
    action_item_id: int,
    **kwargs
) -> Optional[ActionItem]:
    """Обновить action item"""
    result = await db.execute(
        select(ActionItem).where(ActionItem.id == action_item_id)
    )
    action_item = result.scalars().first()
    
    if not action_item:
        return None
    
    for field, value in kwargs.items():
        if hasattr(action_item, field) and value is not None:
            setattr(action_item, field, value)
    
    await db.commit()
    await db.refresh(action_item)
    return action_item


async def delete_action_item(db: AsyncSession, action_item_id: int) -> bool:
    """Удалить action item"""
    result = await db.execute(
        select(ActionItem).where(ActionItem.id == action_item_id)
    )
    action_item = result.scalars().first()
    
    if not action_item:
        return False
    
    await db.delete(action_item)
    await db.commit()
    return True


async def get_audio_download_url(db: AsyncSession, meeting_id: int) -> Optional[str]:
    """Получить URL для скачивания аудио"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting or not meeting.audio_file_path:
        return None
    
    return storage.generate_presigned_url(meeting.audio_file_path, expiration=3600)

