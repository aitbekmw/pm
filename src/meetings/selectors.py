from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import joinedload
from typing import Optional
from datetime import datetime

from src.meetings.models import (
    Meeting, Transcript, Summary, Note, ActionItem, MeetingProcessing
)
from src.users.models import User


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
        .options(joinedload(Meeting.organizer))
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


async def get_active_processing_meeting(
    db: AsyncSession,
    user_id: int
) -> Optional[MeetingProcessing]:
    """Получить встречу, которая находится в процессе обработки для пользователя"""
    result = await db.execute(
        select(MeetingProcessing)
        .join(Meeting, MeetingProcessing.meeting_id == Meeting.id)
        .where(
            and_(
                Meeting.organizer_id == user_id,
                MeetingProcessing.status == "processing"
            )
        )
        .order_by(MeetingProcessing.started_at.desc())
    )
    return result.scalars().first()


async def get_active_meeting_with_details(
    db: AsyncSession,
    user_id: int
):
    """Получить встречу в процессе обработки со всеми деталями"""
    processing = await get_active_processing_meeting(db, user_id)
    if not processing:
        return None
    
    meeting = await get_meeting_by_id(db, processing.meeting_id)
    return {
        "meeting": meeting,
        "processing": processing
    }


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


async def get_meetings_with_filters(
    db: AsyncSession,
    user_id: int,
    search_query: Optional[str] = None,
    project_id: Optional[int] = None,
    organizer_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    sort_by: str = "date_desc",
    skip: int = 0,
    limit: int = 50,
    return_count: bool = False
) -> tuple[list[Meeting], int] | list[Meeting]:
    """
    Получить встречи с фильтрацией и сортировкой.
    
    Параметры фильтрации:
    - search_query: поиск по названию встречи
    - organizer_id: ID организатора встречи
    - start_date: начало периода
    - end_date: конец периода
    - min_duration: минимальная длительность в минутах (поддерживает decimal)
    - max_duration: максимальная длительность в минутах (поддерживает decimal)
    
    Параметры сортировки (sort_by - может быть несколько, разделены запятыми):
    - date_asc: старые → новые
    - date_desc: новые → старые (по умолчанию)
    - duration_asc: от коротких → к длинным
    - duration_desc: от длинных → к коротким
    
    Пример: "date_desc,duration_asc"
    """
    filters = [Meeting.organizer_id == user_id]
    
    if search_query:
        filters.append(Meeting.title.ilike(f"%{search_query}%"))
    
    if project_id is not None:
        filters.append(Meeting.project_id == project_id)
    
    if organizer_id is not None:
        filters.append(Meeting.organizer_id == organizer_id)
    
    if start_date is not None:
        filters.append(Meeting.meeting_date >= start_date)
    
    if end_date is not None:
        filters.append(Meeting.meeting_date <= end_date)
    
    if min_duration is not None:
        # Преобразуем минуты в секунды для сравнения
        min_duration_seconds = int(min_duration * 60)
        filters.append(Meeting.duration >= min_duration_seconds)
    
    if max_duration is not None:
        # Преобразуем минуты в секунды для сравнения
        max_duration_seconds = int(max_duration * 60)
        filters.append(Meeting.duration <= max_duration_seconds)
    
    query = select(Meeting).where(and_(*filters))
    
    # Загружаем организатора с встречей для отображения полной информации
    query = query.options(joinedload(Meeting.organizer))
    
    # Применить сортировку (поддерживает несколько полей через запятую)
    sort_fields = sort_by.split(",") if sort_by else ["date_desc"]
    for sort_field in sort_fields:
        sort_field = sort_field.strip()
        if sort_field == "date_asc":
            query = query.order_by(Meeting.meeting_date.asc())
        elif sort_field == "date_desc":
            query = query.order_by(Meeting.meeting_date.desc())
        elif sort_field == "duration_asc":
            query = query.order_by(Meeting.duration.asc())
        elif sort_field == "duration_desc":
            query = query.order_by(Meeting.duration.desc())
    
    # Получаем общее количество до apply offset/limit
    if return_count:
        count_result = await db.execute(select(func.count(Meeting.id)).where(and_(*filters)))
        total = count_result.scalar()
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    meetings = list(result.scalars().all())
    
    if return_count:
        return meetings, total
    return meetings


async def get_project_meetings_with_filters(
    db: AsyncSession,
    project_id: int,
    search_query: Optional[str] = None,
    organizer_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    sort_by: str = "date_desc",
    skip: int = 0,
    limit: int = 50,
    return_count: bool = False
) -> tuple[list[Meeting], int] | list[Meeting]:
    """
    Получить встречи проекта с фильтрацией и сортировкой.
    
    Параметры фильтрации:
    - search_query: поиск по названию встречи
    - organizer_id: ID организатора встречи
    - start_date: начало периода
    - end_date: конец периода
    - min_duration: минимальная длительность в минутах (поддерживает decimal)
    - max_duration: максимальная длительность в минутах (поддерживает decimal)
    
    Параметры сортировки (sort_by - может быть несколько, разделены запятыми):
    - date_asc: старые → новые
    - date_desc: новые → старые (по умолчанию)
    - duration_asc: от коротких → к длинным
    - duration_desc: от длинных → к коротким
    
    Пример: "date_desc,duration_asc"
    """
    filters = [Meeting.project_id == project_id]
    
    if search_query:
        filters.append(Meeting.title.ilike(f"%{search_query}%"))
    
    if organizer_id is not None:
        filters.append(Meeting.organizer_id == organizer_id)
    
    if start_date is not None:
        filters.append(Meeting.meeting_date >= start_date)
    
    if end_date is not None:
        filters.append(Meeting.meeting_date <= end_date)
    
    if min_duration is not None:
        # Преобразуем минуты в секунды для сравнения
        min_duration_seconds = int(min_duration * 60)
        filters.append(Meeting.duration >= min_duration_seconds)
    
    if max_duration is not None:
        # Преобразуем минуты в секунды для сравнения
        max_duration_seconds = int(max_duration * 60)
        filters.append(Meeting.duration <= max_duration_seconds)
    
    query = select(Meeting).where(and_(*filters))
    
    # Загружаем организатора с встречей для отображения полной информации
    query = query.options(joinedload(Meeting.organizer))
    
    # Применить сортировку (поддерживает несколько полей через запятую)
    sort_fields = sort_by.split(",") if sort_by else ["date_desc"]
    for sort_field in sort_fields:
        sort_field = sort_field.strip()
        if sort_field == "date_asc":
            query = query.order_by(Meeting.meeting_date.asc())
        elif sort_field == "date_desc":
            query = query.order_by(Meeting.meeting_date.desc())
        elif sort_field == "duration_asc":
            query = query.order_by(Meeting.duration.asc())
        elif sort_field == "duration_desc":
            query = query.order_by(Meeting.duration.desc())
    
    # Получаем общее количество до apply offset/limit
    if return_count:
        count_result = await db.execute(select(func.count(Meeting.id)).where(and_(*filters)))
        total = count_result.scalar()
    
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    meetings = list(result.scalars().all())
    
    if return_count:
        return meetings, total
    return meetings

