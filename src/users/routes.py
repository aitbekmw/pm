from fastapi import APIRouter, Depends, Response, Request, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.get("/me", response_model=UserOut)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = await services.get_user_by_session(db, session_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user




@router.get("/", response_model=UserList)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получает список пользователей (для всех аутентифицированных пользователей)"""
    users, total = await services.get_users(db, skip=skip, limit=limit)
    return UserList(users=users, total=total)


@router.put("/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: int,
    role_data: UserUpdateRole,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновляет роль пользователя (только для Manager)"""
    if current_user.role != "Manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    updated_user = await services.update_user_role(db, user_id, role_data.role, current_user)
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not update user")
    
    return updated_user


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
    
    return user
