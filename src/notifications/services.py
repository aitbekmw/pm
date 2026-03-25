from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from src.meetings.models import Notification
from src.notifications import selectors

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    user_id: int,
    type: str,
    title: str,
    message: Optional[str] = None,
    meeting_id: Optional[int] = None,
    project_id: Optional[int] = None
) -> Notification:
    """Создать уведомление и отправить push на все устройства пользователя."""
    notification = Notification(
        user_id=user_id,
        meeting_id=meeting_id,
        project_id=project_id,
        type=type,
        title=title,
        message=message,
        is_read=False
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    await _send_push_for_notification(db, user_id=user_id, title=title, body=message or "", type=type, meeting_id=meeting_id, project_id=project_id)

    return notification


async def _send_push_for_notification(
    db: AsyncSession,
    *,
    user_id: int,
    title: str,
    body: str,
    type: str,
    meeting_id: Optional[int],
    project_id: Optional[int],
) -> None:
    """Получить токены пользователя и отправить push через Expo."""
    try:
        from src.users.services import get_push_tokens_for_users, delete_push_token
        from src.core.push import send_expo_push, DeviceNotRegisteredError

        tokens = await get_push_tokens_for_users(db, [user_id])
        if not tokens:
            return

        # Формируем data-payload по типу уведомления
        data: dict = {}
        if type == "new_meeting" and meeting_id:
            data = {"meet_id": meeting_id}
        elif type == "added_to_project" and project_id:
            data = {"project_id": project_id}

        for token in tokens:
            try:
                await send_expo_push(token=token, title=title, body=body, data=data)
            except DeviceNotRegisteredError:
                logger.info(f"[push] DeviceNotRegistered — удаляем токен {token[:30]}…")
                await delete_push_token(db, user_id=user_id, token=token)
    except Exception as exc:
        # Push — вспомогательная функция, не должна ломать основной флоу
        logger.error(f"[push] ошибка при отправке push для user_id={user_id}: {exc}", exc_info=True)


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

