from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional

from src.meetings.models import Notification


async def get_user_notifications(
    db: AsyncSession,
    user_id: int,
    unread_only: bool = False,
    skip: int = 0,
    limit: int = 50
) -> list[Notification]:
    """Получить уведомления пользователя"""
    query = select(Notification).where(Notification.user_id == user_id)
    
    if unread_only:
        query = query.where(Notification.is_read == False)
    
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_notification_by_id(
    db: AsyncSession,
    notification_id: int
) -> Optional[Notification]:
    """Получить уведомление по ID"""
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    return result.scalars().first()


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    """Получить количество непрочитанных уведомлений"""
    from sqlalchemy import func
    result = await db.execute(
        select(func.count(Notification.id))
        .where(
            and_(
                Notification.user_id == user_id,
                Notification.is_read == False
            )
        )
    )
    return result.scalar() or 0

