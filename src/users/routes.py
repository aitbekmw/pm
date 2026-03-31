from fastapi import APIRouter, Depends, Response, Request, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from urllib.parse import urlencode
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

from src.db.deps import get_db
from src.users import services
from src.users.schemas import LoginRequest, LoginResponse, UserOut, UserUpdateRole, UserList, PushTokenRegister, PushTokenDelete
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


# Whitelist допустимых схем для redirect_uri (мобильные deep links)
ALLOWED_REDIRECT_URI_SCHEMES = {"mdscribe://"}


def _validate_redirect_uri(redirect_uri: Optional[str]) -> None:
    """Валидирует redirect_uri по whitelist допустимых схем."""
    if redirect_uri is None:
        return
    allowed = any(redirect_uri.startswith(scheme) for scheme in ALLOWED_REDIRECT_URI_SCHEMES)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"redirect_uri scheme is not allowed. Allowed schemes: {', '.join(ALLOWED_REDIRECT_URI_SCHEMES)}"
        )


@router.get(
    "/login/google",
    tags=["oauth"],
    summary="Войти через Google OAuth",
    description=(
        "Перенаправляет браузер пользователя на страницу авторизации Google.\n\n"
        "**Параметр `company`** определяет, какой Google Cloud проект используется:\n"
        "- `mmarket` *(по умолчанию)* — проект M-Market (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`)\n"
        "- `minvest` — проект MInvest (`MINVEST_GOOGLE_CLIENT_ID` / `MINVEST_GOOGLE_CLIENT_SECRET`)\n\n"
        "**Параметр `redirect_uri`** (опционально) — deep link для мобильного приложения.\n"
        "Если передан, после авторизации редирект будет на `<redirect_uri>?session_id=<id>` вместо веб-фронта.\n"
        "Допустимые схемы: `mdscribe://`\n\n"
        "После авторизации Google редиректит пользователя на `/api/users/auth/google/callback`."
    ),
    response_class=RedirectResponse,
    responses={
        302: {"description": "Редирект на страницу авторизации Google"},
        400: {"description": "redirect_uri содержит недопустимую схему", "model": GoogleCallbackError},
        503: {"description": "OAuth для выбранной компании не настроен (нет client_id/secret в .env)", "model": GoogleCallbackError},
    },
    status_code=302,
)
async def google_login(
    request: Request,
    company: str = Query(default="mmarket", description="Компания: `mmarket` или `minvest`"),
    redirect_uri: Optional[str] = Query(default=None, description="Deep link для мобильного приложения (например `mdscribe://auth/callback`)"),
):
    """Редирект на Google авторизацию.
    - company=mmarket (дефолт) — использует креды M-Market
    - company=minvest — использует креды MInvest (нужны MINVEST_GOOGLE_CLIENT_ID/SECRET в .env)
    - redirect_uri — если передан, после авторизации редиректит на него с ?session_id=<id>
    """
    _validate_redirect_uri(redirect_uri)

    logger.info(
        f"[google_login] company={company} | redirect_uri={redirect_uri} | "
        f"MINVEST_CLIENT_ID set={bool(settings.MINVEST_GOOGLE_CLIENT_ID)} | "
        f"MINVEST_CLIENT_SECRET set={bool(settings.MINVEST_GOOGLE_CLIENT_SECRET)} | "
        f"GOOGLE_REDIRECT_URI={settings.GOOGLE_REDIRECT_URI} | "
        f"FRONTEND_URL={settings.FRONTEND_URL} | "
        f"OAUTH_SESSION_SECRET set={bool(settings.OAUTH_SESSION_SECRET)} | "
        f"debug={settings.debug}"
    )
    logger.info(f"[google_login] request.url={request.url} | base_url={request.base_url}")

    # Сохраняем redirect_uri в сессии, чтобы использовать в callback
    if redirect_uri:
        request.session["mobile_redirect_uri"] = redirect_uri

    if company == "minvest":
        if not settings.MINVEST_GOOGLE_CLIENT_ID or not settings.MINVEST_GOOGLE_CLIENT_SECRET:
            logger.error("[google_login] MInvest OAuth creds not set in .env!")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MInvest Google OAuth is not configured yet"
            )
        logger.info("[google_login] starting authorize_redirect for google_minvest")
        try:
            request.session["oauth_provider"] = "google_minvest"
            redirect = await oauth.google_minvest.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)
            logger.info(f"[google_login] authorize_redirect success, redirect headers={dict(redirect.headers)}")
            return redirect
        except Exception as e:
            logger.error(f"[google_login] authorize_redirect FAILED: {type(e).__name__}: {e}", exc_info=True)
            raise

    # дефолт — mmarket
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        logger.error("[google_login] mmarket OAuth creds not set in .env!")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured"
        )
    logger.info("[google_login] starting authorize_redirect for google_mmarket")
    try:
        request.session["oauth_provider"] = "google_mmarket"
        redirect = await oauth.google_mmarket.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)
        logger.info(f"[google_login] authorize_redirect success, redirect headers={dict(redirect.headers)}")
        return redirect
    except Exception as e:
        logger.error(f"[google_login] authorize_redirect FAILED: {type(e).__name__}: {e}", exc_info=True)
        raise


@router.get(
    "/auth/google/callback",
    tags=["oauth"],
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
    mobile_redirect_uri = request.session.get("mobile_redirect_uri")
    logger.info(f"[OAuth callback] provider_name={provider_name}, mobile_redirect_uri={mobile_redirect_uri}, session={dict(request.session)}")
    provider = getattr(oauth, provider_name, None)

    def _error_redirect(error: str, message: Optional[str] = None) -> RedirectResponse:
        """Редиректит на мобильное приложение или веб-фронт с ошибкой."""
        if mobile_redirect_uri:
            params = {"error": error}
            if message:
                params["message"] = message
            return RedirectResponse(url=f"{mobile_redirect_uri}?{urlencode(params)}")
        params = {"error": error}
        if message:
            params["message"] = message
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?{urlencode(params)}")

    if provider is None:
        logger.error(f"[OAuth callback] provider '{provider_name}' not registered")
        return _error_redirect("oauth_not_configured")

    try:
        token = await provider.authorize_access_token(request)
        logger.info(f"[OAuth callback] token received successfully")
    except Exception as e:
        logger.error(f"[OAuth callback] authorize_access_token failed: {type(e).__name__}: {e}")
        return _error_redirect("google_auth_failed")

    # Чистим сессию — данные больше не нужны
    request.session.pop("oauth_provider", None)
    request.session.pop("mobile_redirect_uri", None)

    google_user = token.get("userinfo")
    if not google_user:
        logger.error(f"[OAuth callback] no userinfo in token")
        return _error_redirect("google_auth_failed")

    logger.info(f"[OAuth callback] google_user email={google_user.get('email')}")

    try:
        session_id = await services.login_with_google(db, google_user)
    except UnauthorizedDomainError as e:
        logger.warning(f"[OAuth callback] unauthorized domain: {e}")
        return _error_redirect("unauthorized_domain", str(e))

    if not session_id:
        logger.error(f"[OAuth callback] session_id is None after login_with_google")
        return _error_redirect("user_creation_failed")

    # Мобильное приложение — редиректим на deep link с session_id в query-параметрах
    if mobile_redirect_uri:
        mobile_url = f"{mobile_redirect_uri}?{urlencode({'session_id': session_id})}"
        logger.info(f"[OAuth callback] mobile flow — redirecting to {mobile_url}")
        return RedirectResponse(url=mobile_url, status_code=302)

    # Веб-фронт — устанавливаем cookie и редиректим
    logger.info(f"[OAuth callback] web flow — setting cookie and redirecting to {settings.FRONTEND_URL}/")
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


@router.post(
    "/push-token",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["push"],
    summary="Зарегистрировать push-токен устройства",
    description=(
        "Сохраняет Expo push-токен, привязанный к текущему пользователю.\n\n"
        "Один пользователь может иметь несколько токенов (несколько устройств).\n"
        "Повторная регистрация того же токена — upsert, без дублирования."
    ),
)
async def register_push_token(
    payload: PushTokenRegister,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await services.upsert_push_token(db, current_user.id, payload.token, payload.device_type)


@router.delete(
    "/push-token",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["push"],
    summary="Удалить push-токен устройства",
    description="Удаляет push-токен из базы (вызывать при логауте), чтобы пуши больше не приходили на устройство.",
)
async def remove_push_token(
    payload: PushTokenDelete,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await services.delete_push_token(db, current_user.id, payload.token)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить аккаунт пользователя",
    description=(
        "Мягкое удаление аккаунта: пользователь помечается как неактивный, "
        "а если он владелец проектов — владельцы переназначаются автоматически."
    ),
)
async def delete_my_account(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await services.deactivate_user_account(db, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


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
    """Получает список пользователей **своей компании** (для всех аутентифицированных пользователей).

    Фильтрация по компании происходит автоматически — пользователь видит только тех,
    кто принадлежит той же компании, что и он сам.

    Параметры:
    - q или search: поиск по имени (first_name), фамилии (last_name) или логину (ad_account)
    - skip: смещение для пагинации
    - limit: количество результатов на странице
    
    Примеры:
    - GET /api/users/ - все пользователи своей компании
    - GET /api/users/?q=john - все Джоны в своей компании
    - GET /api/users/?search=doe - все с фамилией Doe в своей компании
    - GET /api/users/?q=john&skip=50&limit=25 - пагинированный поиск
    """
    # Используем q если передан, иначе используем search
    search_query = q or search
    users, total = await services.get_users(
        db,
        skip=skip,
        limit=limit,
        search=search_query,
        company_id=current_user.company_id,
    )
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
