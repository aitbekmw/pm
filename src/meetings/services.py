from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional, BinaryIO
import uuid
import io
import os
import shutil
import tempfile
import asyncio
from fastapi import UploadFile

from src.meetings.models import (
    Meeting, Transcript, Summary, Note, ActionItem, MeetingProcessing
)
from src.meetings.schemas import MeetingCreate, MeetingUpdate
from src.meetings import selectors
from src.core.storage import storage
from src.core.ai_services import ai_service
from src.users.models import User
from src.projects.models import Project


async def create_meeting(
    db: AsyncSession,
    data: MeetingCreate,
    user_id: int,
    audio_file: Optional[UploadFile] = None
) -> Meeting:
    """Создать новую встречу"""
    # Генерировать уникальное имя файла для S3
    audio_path = None
    audio_size = None
    audio_content_type = None
    duration_seconds = None
    user = None  # Initialize user variable
    project = None  # Initialize project variable

    if audio_file:
        audio_filename = audio_file.filename
        file_extension = audio_filename.split('.')[-1] if audio_filename else 'mp3'
        audio_path = f"meetings/{uuid.uuid4()}.{file_extension}"
        
        # Сохраняем во временный файл для определения длительности и загрузки
        # Это предотвращает OOM, так как файл читается чанками
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
            tmp_path = tmp.name
            try:
                # Стримим из UploadFile во временный файл
                audio_file.file.seek(0)
                shutil.copyfileobj(audio_file.file, tmp)
                tmp.flush()
                audio_size = os.path.getsize(tmp_path)
                
                # Получаем длительность (в отдельном потоке, так как ffprobe блокирует)
                duration_seconds = await asyncio.to_thread(
                    storage.get_audio_duration_from_path, tmp_path
                )
                
                # Загружаем в S3 (в отдельном потоке)
                with open(tmp_path, "rb") as f:
                    final_audio_path, audio_content_type = await storage.async_upload_file(
                        f, audio_path
                    )
                    if final_audio_path:
                        audio_path = final_audio_path
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
    
    # Если duration передан из фронта, используем его (приоритет фронта)
    if data.duration is not None:
        duration_seconds = data.duration
    
    # Если project_id равен 0, преобразуем в None (нет проекта)
    project_id = data.project_id if data.project_id and data.project_id > 0 else None
    
    # Определяем company_id
    company_id = None
    if project_id:
        # Если встреча привязана к проекту, берем company_id проекта
        from src.projects.models import Project
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalars().first()
        if project:
            company_id = project.company_id
    
    if not company_id:
        # Если нет проекта или у проекта нет company_id, берем у организатора
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalars().first()
        if user:
            company_id = user.company_id

    meeting = Meeting(
        title=data.title,
        subtitle=data.subtitle,
        project_id=project_id,
        organizer_id=user_id,
        company_id=company_id,
        meeting_date=data.meeting_date or datetime.now(timezone.utc),
        duration=duration_seconds,  # Сохраняем в секундах
        importance=data.importance,
        comments=data.comments,
        notes=data.notes,
        audio_file_path=audio_path,
        audio_file_size=audio_size,
        audio_content_type=audio_content_type if audio_file else None,
    )
    
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    
    # Если встреча привязана к проекту, обновляем updated_at проекта
    if project and project_id:
        project.updated_at = datetime.now(timezone.utc)
        await db.commit()

    # Отправка уведомлений участникам проекта
    if project_id:
        from src.projects import selectors as project_selectors
        from src.notifications import services as notification_services
        
        # Получаем участников проекта
        project_members = await project_selectors.get_project_access(db, project_id)
        
        # Получаем имя организатора
        organizer_name = "Unknown"
        if not user: # user might have been fetched above
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalars().first()
        
        if user:
            organizer_name = f"{user.first_name} {user.last_name}"
            
        # Получаем название проекта
        project_name = "Unknown"
        if not project: # project might have been fetched above
            project_result = await db.execute(select(Project).where(Project.id == project_id))
            project = project_result.scalars().first()
            
        if project:
            project_name = project.name
            
        # Отправляем уведомления всем участникам, кроме организатора
        for access in project_members:
            if access.user_id != user_id:
                await notification_services.create_notification(
                    db=db,
                    user_id=access.user_id,
                    type="new_meeting",
                    title="Новая встреча",
                    message=f"{organizer_name} загрузил(а) встречу в проект {project_name}",
                    meeting_id=meeting.id,
                    project_id=project_id
                )
    
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

    # Если встреча привязана к проекту, обновляем updated_at проекта
    if meeting.project_id:
        project_result = await db.execute(select(Project).where(Project.id == meeting.project_id))
        project = project_result.scalars().first()
        if project:
            project.updated_at = datetime.now(timezone.utc)
            await db.commit()

    return meeting


async def delete_meeting(db: AsyncSession, meeting_id: int) -> bool:
    """Удалить встречу"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        return False
    
    # Удалить аудио из S3
    if meeting.audio_file_path:
        await storage.async_delete_file(meeting.audio_file_path)
    
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

    # Отправка уведомлений участникам нового проекта
    if project_id:
        from src.projects import selectors as project_selectors
        from src.notifications import services as notification_services

        project_members = await project_selectors.get_project_access(db, project_id)

        # Получаем имя организатора
        organizer_name = "Unknown"
        organizer_result = await db.execute(select(User).where(User.id == meeting.organizer_id))
        organizer = organizer_result.scalars().first()
        if organizer:
            organizer_name = f"{organizer.first_name} {organizer.last_name}"

        # Получаем название проекта
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalars().first()
        project_name = project.name if project else "Unknown"

        # Обновляем updated_at проекта
        if project:
            project.updated_at = datetime.now(timezone.utc)
            await db.commit()

        # Отправляем уведомления всем участникам, кроме организатора
        for access in project_members:
            if access.user_id != meeting.organizer_id:
                await notification_services.create_notification(
                    db=db,
                    user_id=access.user_id,
                    type="new_meeting",
                    title="Новая встреча",
                    message=f"{organizer_name} добавил(а) встречу в проект {project_name}",
                    meeting_id=meeting.id,
                    project_id=project_id
                )

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


async def update_transcript(
    db: AsyncSession,
    meeting_id: int,
    content: str
) -> Optional[Transcript]:
    """Обновить транскрипт встречи"""
    result = await db.execute(select(Transcript).where(Transcript.meeting_id == meeting_id))
    transcript = result.scalars().first()
    
    if not transcript:
        return None
    
    transcript.content = content
    await db.commit()
    await db.refresh(transcript)
    return transcript


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


async def get_audio_download_url(db: AsyncSession, meeting_id: int, as_attachment: bool = False) -> Optional[str]:
    """Получить прямую ссылку на аудио через nginx прокси
    
    Args:
        db: database session
        meeting_id: ID встречи
        as_attachment: параметр игнорируется для прямых ссылок (оставлен для совместимости)
    """
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting or not meeting.audio_file_path:
        return None
    
    return storage.generate_direct_url(meeting.audio_file_path)

