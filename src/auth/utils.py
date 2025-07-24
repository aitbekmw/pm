import uuid
from datetime import datetime, timedelta, timezone
'''
import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.exceptions import TokenInvalid, UserIsNotActive
from src.auth.services import AuthService
from src.core.config import settings
from src.database import get_db
from src.profile.models import Profile
from src.profile.schemas import ProfileSchema

TOKEN_TYPE_FIELD = "token_type"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/profile/login",
)


def encode_jwt(
    payload: dict,
    secret_key: str = settings.AUTH_JWT.SECRET_KEY,
    algorithm: str = settings.AUTH_JWT.ALGORITHM,
    expiration_minutes: int = settings.AUTH_JWT.ACCESS_TOKEN_EXPIRATION_MINUTES,
    expire_timedelta: timedelta | None = None,
) -> str:
    to_encode = payload.copy()
    now = datetime.now(timezone.utc)
    if expire_timedelta:
        expire = now + expire_timedelta
    else:
        expire = now + timedelta(minutes=expiration_minutes)
    to_encode.update(
        exp=expire,
        iat=now,
        jti=str(uuid.uuid4()),
    )
    encoded = jwt.encode(
        to_encode,
        secret_key,
        algorithm=algorithm,
    )
    return encoded


def decode_jwt(
    token: str | bytes,
    secret_key: str = settings.AUTH_JWT.SECRET_KEY,
    algorithm: str = settings.AUTH_JWT.ALGORITHM
) -> dict:
    decoded = jwt.decode(token, secret_key, algorithms=[algorithm])
    return decoded


def hash_password(
    password: str,
) -> str:
    return bcrypt.hashpw(
        password.encode(),
        bcrypt.gensalt()
    ).decode('utf-8')


def validate_password(
    password: str,
    hashed_password: bytes | str,
) -> bool:
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(
        password=password.encode(),
        hashed_password=hashed_password_bytes,
    )


async def generate_jwt_token(
    token_type: str,
    token_data: dict,
    expiration_minutes: int = settings.AUTH_JWT.ACCESS_TOKEN_EXPIRATION_MINUTES,
    expire_timedelta: timedelta | None = None,
) -> str:
    jwt_payload = {
        TOKEN_TYPE_FIELD: token_type
    }
    jwt_payload.update(token_data)
    return encode_jwt(
        jwt_payload,
        expiration_minutes=expiration_minutes,
        expire_timedelta=expire_timedelta,
    )


async def create_access_token(profile: Profile):
    jwt_payload = {
        "sub": profile.login,
        "username": profile.first_name + ' ' + profile.last_name,
        "email": profile.email,
    }
    return await generate_jwt_token(
        token_type=ACCESS_TOKEN_TYPE,
        token_data=jwt_payload,
        expiration_minutes=settings.AUTH_JWT.ACCESS_TOKEN_EXPIRATION_MINUTES,
    )


async def create_refresh_token(profile: Profile):
    jwt_payload = {
        "sub": profile.login,
    }
    return await generate_jwt_token(
        token_type=REFRESH_TOKEN_TYPE,
        token_data=jwt_payload,
        expire_timedelta=timedelta(days=settings.AUTH_JWT.REFRESH_TOKEN_EXPIRATION_DAYS),
    )


def validate_token_type(payload: dict, token_type: str):
    if payload.get(TOKEN_TYPE_FIELD) == token_type:
        return True
    raise TokenInvalid


async def get_current_token_payload(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_jwt(token=token)
    except jwt.InvalidTokenError as e:
        raise TokenInvalid(str(e))
    return payload


class UserGetterFromToken:
    def __init__(self, token_type: str):
        self.token_type = token_type

    async def __call__(
        self,
        payload: dict = Depends(get_current_token_payload),
        db: AsyncSession = Depends(get_db),
    ):
        validate_token_type(payload, self.token_type)
        return await get_user_by_token_sub(payload, db)


get_current_profile = UserGetterFromToken(token_type=ACCESS_TOKEN_TYPE)
get_current_profile_by_refresh = UserGetterFromToken(token_type=REFRESH_TOKEN_TYPE)


async def get_user_by_token_sub(
        payload: dict,
        db: AsyncSession = Depends(get_db)
):
    login: str | None = payload.get("sub")
    auth_service: AuthService = AuthService(db)
    profile: Profile = await auth_service.get_by_login(login)
    if profile:
        return profile
    raise TokenInvalid


async def get_current_active_profile(
    profile: ProfileSchema = Depends(get_current_profile)
):
    if profile.is_active:
        return profile
    raise UserIsNotActive()


# async def get_access_token_from_cookies(access_token: str = Cookie(None)):
#     if access_token is None:
#         raise TokenInvalid("No access token found in cookies")
#     return access_token
#
# async def get_refresh_token_from_cookies(refresh_token: str = Cookie(None)):
#     if refresh_token is None:
#         raise TokenInvalid("No refresh token found in cookies")
#     return refresh_token
