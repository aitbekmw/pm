from fastapi import APIRouter, Depends, Response, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.deps import get_db
from src.users import services
from src.users.schemas import LoginRequest, LoginResponse, UserOut
from src.core.config import settings


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
