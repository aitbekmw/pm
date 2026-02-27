from typing import Optional
from fastapi import Request, HTTPException, status
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.deps import get_db
from src.users.models import User
from src.users.services import _ldap_authenticate


class AdminAuthenticationBackend(AuthenticationBackend):
    """Кастомный authentication backend для админки с проверкой роли Admin"""
    
    async def login(self, request: Request) -> bool:
        """Авторизация в админку через AD с проверкой роли Admin"""
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        if not username or not password:
            return False
        
        async for db in get_db():
            try:
                from sqlalchemy.orm import selectinload
                
                # Сначала ищем пользователя в базе
                result = await db.execute(
                    select(User).options(selectinload(User.company)).where(User.ad_account == username)
                )
                user: Optional[User] = result.scalars().first()
                
                authenticated = False
                
                if user and user.admin_password:
                    # Проверяем локальный пароль
                    from src.core.security import verify_password
                    if verify_password(password, user.admin_password):
                        authenticated = True
                
                if not authenticated:
                    # Если локального пароля нет или он не подошел, пробуем через AD
                    ad_info = _ldap_authenticate(username, password)
                    if ad_info is not None:
                        authenticated = True
                        
                        # Если пользователь авторизовался через AD, но его еще нет в базе, 
                        # логика создания должна быть в другом месте, 
                        # но для админки нам нужен существующий пользователь
                        if not user:
                            # Пытаемся найти снова на случай если он был только что создан
                            result = await db.execute(
                                select(User).options(selectinload(User.company)).where(User.ad_account == username)
                            )
                            user = result.scalars().first()

                if not authenticated or not user:
                    return False
                
                if not user.is_active:
                    return False
                
                # КРИТИЧЕСКАЯ ПРОВЕРКА: только Admin может войти в админку
                if user.role != "Admin":
                    return False
                
                request.session.update({
                    "user_id": user.id,
                    "ad_account": user.ad_account,
                    "role": user.role,
                    "company_name": user.company.name if user.company else None,
                    "authenticated": True
                })
                
                return True
                
            except Exception as e:
                print(f"Admin authentication error: {e}")
                return False
            finally:
                await db.close()
    
    async def logout(self, request: Request) -> bool:
        """Выход из админки"""
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        """Проверка аутентификации для доступа к админке"""
        if not request.session.get("authenticated"):
            return False
        
        if request.session.get("role") != "Admin":
            return False
        
        return True
