from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from src.users.models import User


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


async def get_user_by_ad_account(db: AsyncSession, ad_account: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.ad_account == ad_account))
    return result.scalars().first()
