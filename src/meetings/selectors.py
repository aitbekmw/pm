from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import Optional

from src.meetings.models import (
    Meeting, Transcript, Summary, Note, ActionItem, MeetingProcessing
)


async def get_meeting_by_id(db: AsyncSession, meeting_id: int) -> Optional[Meeting]:
    """Получить встречу по ID"""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    return result.scalars().first()


async def get_project_meetings(
    db: AsyncSession,
    project_id: int,
    skip: int = 0,
    limit: int = 50
) -> list[Meeting]:
    """Получить все встречи проекта"""
    result = await db.execute(
        select(Meeting)
        .where(Meeting.project_id == project_id)
        .order_by(Meeting.meeting_date.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_uncategorized_meetings(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 50
) -> list[Meeting]:
    """Получить некатегорированные встречи пользователя"""
    result = await db.execute(
        select(Meeting)
        .where(
            and_(
                Meeting.project_id.is_(None),
                Meeting.organizer_id == user_id
            )
        )
        .order_by(Meeting.meeting_date.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_user_meetings(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 50
) -> list[Meeting]:
    """Получить все встречи пользователя"""
    result = await db.execute(
        select(Meeting)
        .where(Meeting.organizer_id == user_id)
        .order_by(Meeting.meeting_date.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_meeting_transcript(
    db: AsyncSession,
    meeting_id: int
) -> Optional[Transcript]:
    """Получить транскрипт встречи"""
    result = await db.execute(
        select(Transcript).where(Transcript.meeting_id == meeting_id)
    )
    return result.scalars().first()


async def get_meeting_summary(
    db: AsyncSession,
    meeting_id: int
) -> Optional[Summary]:
    """Получить суммаризацию встречи"""
    result = await db.execute(
        select(Summary).where(Summary.meeting_id == meeting_id)
    )
    return result.scalars().first()


async def get_meeting_notes(
    db: AsyncSession,
    meeting_id: int
) -> list[Note]:
    """Получить заметки встречи"""
    result = await db.execute(
        select(Note)
        .where(Note.meeting_id == meeting_id)
        .order_by(Note.created_at.asc())
    )
    return list(result.scalars().all())


async def get_meeting_action_items(
    db: AsyncSession,
    meeting_id: int
) -> list[ActionItem]:
    """Получить action items встречи"""
    result = await db.execute(
        select(ActionItem)
        .where(ActionItem.meeting_id == meeting_id)
        .order_by(ActionItem.created_at.asc())
    )
    return list(result.scalars().all())


async def get_meeting_processing(
    db: AsyncSession,
    meeting_id: int
) -> Optional[MeetingProcessing]:
    """Получить статус обработки встречи"""
    result = await db.execute(
        select(MeetingProcessing).where(MeetingProcessing.meeting_id == meeting_id)
    )
    return result.scalars().first()


async def search_meetings(
    db: AsyncSession,
    query: str,
    project_id: Optional[int] = None,
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50
) -> list[Meeting]:
    """Поиск встреч по названию"""
    filters = [Meeting.title.ilike(f"%{query}%")]
    
    if project_id is not None:
        filters.append(Meeting.project_id == project_id)
    
    if user_id is not None:
        filters.append(Meeting.organizer_id == user_id)
    
    result = await db.execute(
        select(Meeting)
        .where(and_(*filters))
        .order_by(Meeting.meeting_date.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())

