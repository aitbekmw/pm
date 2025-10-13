from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.meetings.models import Notification
from src.notifications import selectors


async def create_notification(
    db: AsyncSession,
    user_id: int,
    type: str,
    title: str,
    message: Optional[str] = None,
    meeting_id: Optional[int] = None
) -> Notification:
    """Создать уведомление"""
    notification = Notification(
        user_id=user_id,
        meeting_id=meeting_id,
        type=type,
        title=title,
        message=message,
        is_read=False
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_as_read(
    db: AsyncSession,
    notification_id: int
) -> Optional[Notification]:
    """Отметить уведомление как прочитанное"""
    notification = await selectors.get_notification_by_id(db, notification_id)
    if not notification:
        return None
    
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification


async def mark_all_as_read(db: AsyncSession, user_id: int) -> int:
    """Отметить все уведомления пользователя как прочитанные"""
    from sqlalchemy import update
    
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return result.rowcount


async def delete_notification(db: AsyncSession, notification_id: int) -> bool:
    """Удалить уведомление"""
    notification = await selectors.get_notification_by_id(db, notification_id)
    if not notification:
        return False
    
    await db.delete(notification)
    await db.commit()
    return True

