from fastapi import APIRouter, Depends, Response, Request, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.db.deps import get_db
from src.users import services
from src.users.schemas import LoginRequest, LoginResponse, UserOut, UserUpdateRole, UserList
from src.core.config import settings
from src.core.permissions import get_current_user


router = APIRouter(prefix="/users", tags=["users"])


SESSION_COOKIE_NAME = "session_id"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    session_id = await services.login_with_ad(db, payload.username, payload.password)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )
    return {"success": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await services.logout(db, session_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/login/google")
async def google_login():
    """Редирект пользователя на страницу авторизации Google"""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    url = services.get_google_oauth_url()
    return RedirectResponse(url=url)


@router.get("/auth/google/callback")
async def google_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Redirect URL для Google OAuth — получает code от Google и создаёт сессию"""
    if error:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error={error}")

    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code")

    google_user = await services.exchange_google_code(code)
    if not google_user:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=google_auth_failed")

    session_id = await services.login_with_google(db, google_user)
    if not session_id:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=user_creation_failed")

    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        path="/",
        domain=settings.COOKIE_DOMAIN,
    )
    return response


@router.get("/me", response_model=UserOut)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = await services.get_user_by_session(db, session_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return UserOut.model_validate(user)


@router.get("/roles", response_model=dict)
async def get_roles(
    current_user = Depends(get_current_user)
):
    """Получить список доступных ролей в системе"""
    available_roles = [
        "Manager",
        "Member",
        "Admin",
        "Backend Dev",
        "Frontend Dev",
        "Designer",
        "QA"
    ]
    return {
        "roles": available_roles,
        "count": len(available_roles)
    }


@router.get("/", response_model=UserList)
async def list_users(
    q: Optional[str] = Query(None, min_length=1, description="Поиск по имени, фамилии или логину (ad_account) - альтернатива параметру search"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None, min_length=1, description="Поиск по имени, фамилии или логину (ad_account)"),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает список пользователей (для всех аутентифицированных пользователей)
    
    Параметры:
    - q или search: поиск по имени (first_name), фамилии (last_name) или логину (ad_account)
    - skip: смещение для пагинации
    - limit: количество результатов на странице
    
    Примеры:
    - GET /api/users/ - все пользователи
    - GET /api/users/?q=john - все Джоны
    - GET /api/users/?search=doe - все с фамилией Doe
    - GET /api/users/?q=jdoe - поиск по логину jdoe
    - GET /api/users/?q=john&skip=50&limit=25 - пагинированный поиск
    """
    # Используем q если передан, иначе используем search
    search_query = q or search
    users, total = await services.get_users(db, skip=skip, limit=limit, search=search_query)
    user_out_list = [UserOut.model_validate(user) for user in users]
    return UserList(users=user_out_list, total=total)


@router.put("/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: int,
    role_data: UserUpdateRole,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновляет роль пользователя (только для Admin)"""
    if current_user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    updated_user = await services.update_user_role(db, user_id, role_data.role, current_user)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not update user")
    
    return UserOut.model_validate(updated_user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает информацию о пользователе по ID (для всех аутентифицированных пользователей)"""
    user = await services.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return UserOut.model_validate(user)
