from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import LoginSchema, TokenInfo
from src.auth.exceptions import WrongCredentials
from src.auth.utils import create_access_token, create_refresh_token
from src.database import get_db
from src.auth.services import authenticate_with_ldap, get_or_create_profile

router = APIRouter()

'''
@router.post("/login", response_model=TokenInfo)
async def login(
    data: LoginSchema,
    db: AsyncSession = Depends(get_db),
):
    if not authenticate_with_ldap(data.login, data.password):
        raise WrongCredentials()

    profile = await get_or_create_profile(data.login, db)

    access_token = await create_access_token(profile)
    refresh_token = await create_refresh_token(profile)

    return TokenInfo(
        access_token=access_token,
        refresh_token=refresh_token,
    )
