from typing import Optional
from fastapi import Request
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.deps import get_db
from src.users.models import AdminUser
from src.companies.models import Company
from src.core.security import verify_password


class TenantAdminAuth(AuthenticationBackend):
    """Кастомный authentication backend для multi-tenant админки"""
    
    def __init__(self, secret_key: str, company_slug: str):
        super().__init__(secret_key=secret_key)
        self.company_slug = company_slug

    async def login(self, request: Request) -> bool:
        """Авторизация в админку с проверкой через AdminUser и ограничением по компании"""
        form = await request.form()
        email = form.get("username")  # sqladmin form uses 'username' field for login
        password = form.get("password")
        
        if not email or not password:
            return False
            
        async for db in get_db():
            try:
                # Найти компанию по слагу
                company_result = await db.execute(select(Company).where(Company.slug == self.company_slug))
                company: Optional[Company] = company_result.scalars().first()
                
                if not company:
                    return False

                # Найти админа по email
                result = await db.execute(select(AdminUser).where(AdminUser.email == email))
                admin_user: Optional[AdminUser] = result.scalars().first()
                
                if not admin_user:
                    return False
                
                if not admin_user.is_active:
                    return False
                
                if admin_user.company_id != company.id:
                    return False
                    
                if not verify_password(password, admin_user.hashed_password):
                    return False
                
                request.session.update({
                    "admin_user_id": admin_user.id,
                    "email": admin_user.email,
                    "company_id": company.id,
                    "company_slug": self.company_slug,
                    "authenticated": True
                })
                
                return True
                
            except Exception as e:
                print(f"Tenant Admin authentication error: {e}")
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
            
        # Проверяем что сессия принадлежит правильной компании
        if request.session.get("company_slug") != self.company_slug:
            return False
            
        return True
