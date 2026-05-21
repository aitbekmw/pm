from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import os
import shutil
import tempfile
import asyncio
import logging
from fastapi import UploadFile

from src.meetings.models import (
    Meeting, Transcript, Summary, Note, ActionItem, MeetingProcessing
)
from src.meetings.schemas import MeetingCreate, MeetingUpdate
from src.meetings import selectors
from src.core.storage import storage
from src.users.models import User
from src.projects.models import Project
from src.core.config import settings

logger = logging.getLogger(__name__)


async def _touch_project(db: AsyncSession, project_id: Optional[int]):
    if project_id:
        project = await db.get(Project, project_id)
        if project:
            project.updated_at = datetime.now(timezone.utc)


async def create_meeting(
        db: AsyncSession,
        data: MeetingCreate,
        user_id: int,
        audio_file: Optional[UploadFile] = None
) -> Meeting:
    audio_path = None
    audio_size = None
    audio_content_type = None
    duration_seconds = data.duration if data.duration is not None else None

    if audio_file:
        audio_filename = audio_file.filename
        file_extension = audio_filename.split('.')[-1] if audio_filename else 'mp3'
        audio_path = f"meetings/{uuid.uuid4()}.{file_extension}"

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as tmp:
            tmp_path = tmp.name
            try:
                await audio_file.seek(0)
                shutil.copyfileobj(audio_file.file, tmp)
                tmp.flush()
                audio_size = os.path.getsize(tmp_path)
                duration_seconds = await asyncio.to_thread(storage.get_audio_duration_from_path, tmp_path)
                with open(tmp_path, "rb") as f:
                    final_audio_path, audio_content_type = await storage.async_upload_file(f, audio_path)
                    if final_audio_path:
                        audio_path = final_audio_path
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

    project_id = data.project_id or None

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    company_id = user.company_id if user else None

    project = None
    if project_id:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalars().first()
        if project:
            company_id = project.company_id

    meeting = Meeting(
        title=data.title, subtitle=data.subtitle, project_id=project_id,
        organizer_id=user_id, company_id=company_id,
        meeting_date=data.meeting_date or datetime.now(timezone.utc),
        duration=duration_seconds, importance=data.importance,
        comments=data.comments, notes=data.notes,
        audio_file_path=audio_path, audio_file_size=audio_size,
        audio_content_type=audio_content_type if audio_file else None,
    )

    db.add(meeting)
    await _touch_project(db, project_id)
    await db.commit()
    await db.refresh(meeting)

    if project_id and project:
        from src.projects import selectors as project_selectors
        from src.notifications import services as notification_services

        project_members = await project_selectors.get_project_access(db, project_id)
        organizer_name = f"{user.first_name} {user.last_name}".strip() if user else "Unknown"

        for access in project_members:
            if access.user_id != user_id:
                await notification_services.create_notification(
                    db=db,
                    user_id=access.user_id,
                    type="new_meeting",
                    title="Новая встреча",
                    message=f"В проекте «{project.name}» добавлена новая встреча: «{data.title}»",
                    meeting_id=meeting.id,
                    project_id=project_id
                )

        if meeting.meeting_date and project.telegram_chat_id:
            from arq import create_pool
            from arq.connections import RedisSettings

            arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

            remind_1h = meeting.meeting_date - timedelta(hours=1)
            if remind_1h > datetime.now(timezone.utc):
                await arq_pool.enqueue_job("send_meeting_reminder", meeting.id, 60, _defer_until=remind_1h)

            remind_15m = meeting.meeting_date - timedelta(minutes=15)
            if remind_15m > datetime.now(timezone.utc):
                await arq_pool.enqueue_job("send_meeting_reminder", meeting.id, 15, _defer_until=remind_15m)

            await arq_pool.aclose()

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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(meeting, field, value)

    await _touch_project(db, meeting.project_id)
    await db.commit()
    await db.refresh(meeting)
    return meeting


async def delete_meeting(db: AsyncSession, meeting_id: int) -> bool:
    """Удалить встречу"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        return False

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

    old_pid = meeting.project_id
    meeting.project_id = project_id

    await _touch_project(db, old_pid)
    await _touch_project(db, project_id)
    await db.commit()
    await db.refresh(meeting)

    if project_id:
        from src.projects import selectors as project_selectors
        from src.notifications import services as notification_services

        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalars().first()

        organizer_result = await db.execute(select(User).where(User.id == meeting.organizer_id))
        organizer = organizer_result.scalars().first()
        organizer_name = f"{organizer.first_name} {organizer.last_name}".strip() if organizer else "Unknown"
        project_name = project.name if project else "Unknown"

        project_members = await project_selectors.get_project_access(db, project_id)
        for access in project_members:
            if access.user_id != meeting.organizer_id:
                await notification_services.create_notification(
                    db=db,
                    user_id=access.user_id,
                    type="new_meeting",
                    title="Новая встреча",
                    message=f"{organizer_name} добавил(а) встречу «{meeting.title}» в проект {project_name}",
                    meeting_id=meeting.id,
                    project_id=project_id
                )

    return meeting


async def create_or_update_transcript(
        db: AsyncSession,
        meeting_id: int,
        content: str
) -> Optional[Transcript]:
    """Создать или обновить транскрипт встречи"""
    result = await db.execute(select(Transcript).where(Transcript.meeting_id == meeting_id))
    transcript = result.scalars().first()

    if not transcript:
        transcript = Transcript(meeting_id=meeting_id, content=content)
        db.add(transcript)
    else:
        transcript.content = content

    await db.commit()
    await db.refresh(transcript)
    return transcript


async def create_note(
        db: AsyncSession,
        meeting_id: int,
        content: str,
        user_id: int
) -> Note:
    """Создать заметку для встречи"""
    note = Note(meeting_id=meeting_id, content=content, creator_id=user_id)
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
    result = await db.execute(select(ActionItem).where(ActionItem.id == action_item_id))
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
    result = await db.execute(select(ActionItem).where(ActionItem.id == action_item_id))
    action_item = result.scalars().first()
    if not action_item:
        return False

    await db.delete(action_item)
    await db.commit()
    return True


async def get_audio_download_url(
        db: AsyncSession,
        meeting_id: int,
        as_attachment: bool = False
) -> Optional[str]:
    """Получить ссылку на аудио"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting or not meeting.audio_file_path:
        return None
    return storage.generate_direct_url(meeting.audio_file_path)