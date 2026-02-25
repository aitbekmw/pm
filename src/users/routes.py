from fastapi import APIRouter, Depends, Response, Request, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from urllib.parse import urlencode
from pydantic import BaseModel

from src.db.deps import get_db
from src.users import services
from src.users.schemas import LoginRequest, LoginResponse, UserOut, UserUpdateRole, UserList
from src.core.config import settings
from src.core.permissions import get_current_user
from src.core.exceptions import UnauthorizedDomainError
from src.core.oauth import oauth


router = APIRouter(prefix="/users", tags=["users"])


# ---------- Swagger response schemas ----------

class GoogleLoginRedirect(BaseModel):
    """Тело не возвращается — происходит редирект на Google"""
    pass


class GoogleCallbackError(BaseModel):
    detail: str


# ----------------------------------------------


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


@router.get(
    "/login/google",
    tags=["auth", "oauth"],
    summary="Войти через Google OAuth",
    description=(
        "Перенаправляет браузер пользователя на страницу авторизации Google.\n\n"
        "**Параметр `company`** определяет, какой Google Cloud проект используется:\n"
        "- `mmarket` *(по умолчанию)* — проект M-Market (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`)\n"
        "- `minvest` — проект MInvest (`MINVEST_GOOGLE_CLIENT_ID` / `MINVEST_GOOGLE_CLIENT_SECRET`)\n\n"
        "После авторизации Google редиректит пользователя на `/api/users/auth/google/callback`."
    ),
    response_class=RedirectResponse,
    responses={
        302: {"description": "Редирект на страницу авторизации Google"},
        503: {"description": "OAuth для выбранной компании не настроен (нет client_id/secret в .env)", "model": GoogleCallbackError},
    },
    status_code=302,
)
async def google_login(request: Request, company: str = Query(default="mmarket", description="Компания: `mmarket` или `minvest`")):
    """Редирект на Google авторизацию.
    - company=mmarket (дефолт) — использует креды M-Market
    - company=minvest — использует креды MInvest (нужны MINVEST_GOOGLE_CLIENT_ID/SECRET в .env)
    """
    if company == "minvest":
        if not settings.MINVEST_GOOGLE_CLIENT_ID or not settings.MINVEST_GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MInvest Google OAuth is not configured yet"
            )
        # Запоминаем какой провайдер использовали — нужно в коллбеке
        request.session["oauth_provider"] = "google_minvest"
        return await oauth.google_minvest.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)

    # дефолт — mmarket
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    request.session["oauth_provider"] = "google_mmarket"
    return await oauth.google_mmarket.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@router.get(
    "/auth/google/callback",
    tags=["auth", "oauth"],
    summary="Google OAuth callback",
    description=(
        "Этот роут вызывается Google'ом автоматически после того как пользователь подтвердил авторизацию.\n\n"
        "**Вручную вызывать не нужно.**\n\n"
        "Бэкенд:\n"
        "1. Определяет провайдера из сессии (`google_mmarket` или `google_minvest`)\n"
        "2. Обменивает `code` на токен Google\n"
        "3. Получает `userinfo` (email, имя)\n"
        "4. Определяет компанию по домену email (`@m-market.kg` → mmarket, `@minvest.kg` → minvest)\n"
        "5. Находит или создаёт пользователя в БД\n"
        "6. Создаёт сессию, устанавливает cookie `session_id` и редиректит на фронт\n\n"
        "**Ошибки** передаются через query-параметры редиректа на фронт:\n"
        "- `?error=google_auth_failed` — не удалось получить токен\n"
        "- `?error=unauthorized_domain&message=...` — домен почты не разрешён\n"
        "- `?error=user_creation_failed` — не удалось создать пользователя\n"
        "- `?error=oauth_not_configured` — провайдер не зарегистрирован"
    ),
    response_class=RedirectResponse,
    responses={
        302: {"description": "Редирект на фронт (успех — на `/`, ошибка — на `/login?error=...`)"},
    },
    status_code=302,
    include_in_schema=True,
)
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Единый callback — провайдер определяется по сессии, которая была записана при логине."""
    provider_name = request.session.get("oauth_provider", "google_mmarket")
    provider = getattr(oauth, provider_name, None)

    if provider is None:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=oauth_not_configured")

    try:
        token = await provider.authorize_access_token(request)
    except Exception:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=google_auth_failed")

    # Чистим провайдер из сессии — он больше не нужен
    request.session.pop("oauth_provider", None)

    google_user = token.get("userinfo")
    if not google_user:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=google_auth_failed")

    try:
        session_id = await services.login_with_google(db, google_user)
    except UnauthorizedDomainError as e:
        error_msg = urlencode({"error": "unauthorized_domain", "message": str(e)})
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?{error_msg}")

    if not session_id:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=user_creation_failed")

    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/", status_code=302)
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
