from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_

from ldap3 import Server, Connection, ALL, NTLM

from src.core.config import settings
from src.users.models import User, Session


def _ldap_authenticate(username: str, password: str) -> Optional[dict]:
    """
    Аутентификация пользователя через LDAP/AD.
    Использует сервисный аккаунт для подключения к LDAP и проверяет учетные данные пользователя.
    """
    # Создаем сервер с правильными настройками
    server = Server(settings.LDAP_SERVER, use_ssl=False, get_info=ALL)
    
    # Формируем имя сервисного пользователя в формате domain\username
    service_user = f"{settings.LDAP_USER_DN}\\{settings.LDAP_SERVICE_USER}"
    
    try:
        # Подключаемся как сервисный пользователь
        conn = Connection(
            server,
            user=service_user,
            password=settings.LDAP_SERVICE_PASSWORD,
            auto_bind=True,
        )
        
        if not conn.bound:
            return None
            
        # Ищем пользователя в AD
        search_filter = f"(sAMAccountName={username})"
        print(f"LDAP search: {search_filter} in {settings.LDAP_BASE_DN}")
        
        conn.search(
            settings.LDAP_BASE_DN,
            search_filter,
            attributes=["givenName", "sn", "mail", "memberOf", "userAccountControl"]
        )
        
        print(f"LDAP search result: {len(conn.entries)} entries found")
        
        if not conn.entries:
            print(f"User {username} not found in AD")
            return None
            
        entry = conn.entries[0]
        
        # Проверяем, что аккаунт активен (userAccountControl = 512 означает активный аккаунт)
        user_account_control = getattr(entry, "userAccountControl", None)
        if user_account_control:
            try:
                # Преобразуем в строку, затем в int
                uac_value = str(user_account_control)
                if uac_value and int(uac_value) & 2:  # 2 = ACCOUNTDISABLE
                    return None
            except (ValueError, TypeError):
                # Если не можем преобразовать, пропускаем проверку
                pass
            
        # Проверяем пароль пользователя, пытаясь подключиться с его учетными данными
        user_dn = entry.entry_dn
        print(f"Checking password for user DN: {user_dn}")
        
        try:
            user_conn = Connection(
                server,
                user=user_dn,
                password=password,
                auto_bind=True,
            )
            print("Password verification successful")
            user_conn.unbind()
        except Exception as e:
            print(f"Password verification failed: {e}")
            return None  # Неверный пароль
            
        # Возвращаем информацию о пользователе
        return {
            "first_name": str(getattr(entry, "givenName", "") or ""),
            "last_name": str(getattr(entry, "sn", "") or ""),
            "email": str(getattr(entry, "mail", "") or ""),
            "member_of": [str(group) for group in getattr(entry, "memberOf", [])],
        }
        
    except Exception as e:
        print(f"LDAP authentication error: {e}")
        return None
    finally:
        if 'conn' in locals() and conn.bound:
            conn.unbind()


async def login_with_ad(db: AsyncSession, username: str, password: str) -> Optional[str]:
    ad_info = _ldap_authenticate(username, password)
    if ad_info is None:
        return None

    # Find or create user by ad_account
    result = await db.execute(select(User).where(User.ad_account == username))
    user: Optional[User] = result.scalars().first()
    if user is None:
        # Создаем нового пользователя с ролью Member по умолчанию
        user = User(
            ad_account=username,
            first_name=ad_info.get("first_name") or username,
            last_name=ad_info.get("last_name") or "",
            role="Member",  # Всегда Member по умолчанию
            is_active=True,
        )
        db.add(user)
        await db.flush()
    else:
        # Обновляем только имя и фамилию, если они изменились в AD
        # Роль остается той, что была назначена в системе
        new_first_name = ad_info.get("first_name") or username
        new_last_name = ad_info.get("last_name") or ""
        
        if user.first_name != new_first_name or user.last_name != new_last_name:
            user.first_name = new_first_name
            user.last_name = new_last_name
            await db.flush()

    # Create session
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.SESSION_TTL_DAYS)
    db.add(Session(session_id=session_id, user_id=user.id, expires_at=expires_at))
    await db.commit()
    return session_id


async def logout(db: AsyncSession, session_id: str) -> None:
    await db.execute(delete(Session).where(Session.session_id == session_id))
    await db.commit()


async def get_user_by_session(db: AsyncSession, session_id: str) -> Optional[User]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.session_id == session_id)
        .where(Session.expires_at > now)
    )
    return result.scalars().first()


async def get_users(db: AsyncSession, skip: int = 0, limit: int = 100, search: Optional[str] = None) -> tuple[list[User], int]:
    """Получает список пользователей с пагинацией и поиском
    
    Параметры:
    - skip: смещение для пагинации
    - limit: количество результатов
    - search: поиск по имени, фамилии или логину (ad_account)
    """
    # Получаем базовый запрос
    query = select(User)
    
    # Добавляем фильтр поиска если указан
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.where(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.ad_account.ilike(search_term)
            )
        )
    
    # Получаем общее количество пользователей
    count_result = await db.execute(select(func.count(User.id)).select_from(query.subquery()))
    total = count_result.scalar() or 0
    
    # Получаем пользователей с пагинацией
    result = await db.execute(
        query
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    
    return users, total


async def update_user_role(db: AsyncSession, user_id: int, role: str, current_user: User) -> Optional[User]:
    """Обновляет роль пользователя (только для Manager)"""
    # Проверяем права доступа
    if current_user.role != "Manager":
        return None
    
    # Валидируем роль
    valid_roles = ["Member", "PM", "Manager", "Backend Dev", "Frontend Dev", "Designer", "QA"]
    if role not in valid_roles:
        return None
    
    # Получаем пользователя
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        return None
    
    # Обновляем роль
    user.role = role
    await db.commit()
    
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Получает пользователя по ID"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()
