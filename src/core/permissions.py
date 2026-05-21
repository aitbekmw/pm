from fastapi import HTTPException, status, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Callable, Sequence

from src.db.deps import get_db
from src.users.models import User
from src.users import services as user_services

SESSION_COOKIE_NAME = "session_id"


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Получить текущего пользователя по сессии"""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    user = await user_services.get_user_by_session(db, session_id)
    # Явная проверка на существование объекта
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Получить активного пользователя"""
    # Если у пользователя есть поле 'is_active', добавьте проверку здесь:
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_role(*allowed_roles: str) -> Callable:
    """Декоратор для проверки роли пользователя"""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user

    return role_checker


# Готовые зависимости
require_manager = require_role("Manager")
require_manager_or_admin = require_role("Manager", "Admin")
require_any_role = require_role("Manager", "Admin", "Member", "Backend Dev", "Frontend Dev", "Designer", "QA")