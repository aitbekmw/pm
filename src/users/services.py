from datetime import datetime, timedelta, timezone
import secrets
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ldap3 import Server, Connection, ALL, NTLM

from src.core.config import settings
from src.users.models import User, Session


def _ldap_authenticate(username: str, password: str) -> Optional[dict]:
    domain_user = f"{settings.AD_DOMAIN}\\{username}" if "\\" not in username else username
    server = Server(settings.AD_SERVER, get_info=ALL)
    try:
        conn = Connection(
            server,
            user=domain_user,
            password=password,
            authentication=NTLM if settings.AD_USE_NTLM else None,
            auto_bind=True,
        )
    except Exception:
        return None

    # Optionally fetch attributes
    try:
        conn.search(
            settings.AD_BASE_DN,
            f"(sAMAccountName={username.split('\\\\')[-1]})",
            attributes=["givenName", "sn", "mail"],
        )
        if conn.entries:
            entry = conn.entries[0]
            return {
                "first_name": str(getattr(entry, "givenName", "") or ""),
                "last_name": str(getattr(entry, "sn", "") or ""),
                "email": str(getattr(entry, "mail", "") or ""),
            }
    finally:
        conn.unbind()
    return {}


async def login_with_ad(db: AsyncSession, username: str, password: str) -> Optional[str]:
    ad_info = _ldap_authenticate(username, password)
    if ad_info is None:
        return None

    # Find or create user by ad_account
    result = await db.execute(select(User).where(User.ad_account == username))
    user: Optional[User] = result.scalars().first()
    if user is None:
        user = User(
            ad_account=username,
            first_name=ad_info.get("first_name") or username,
            last_name=ad_info.get("last_name") or "",
            role="Member",
            is_active=True,
        )
        db.add(user)
        await db.flush()

    # Create session
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.SESSION_TTL_DAYS)
    db.add(Session(session_id=session_id, user_id=user.id, expires_at=expires_at))
    await db.commit()
    return session_id


async def logout(db: AsyncSession, session_id: str) -> None:
    await db.execute(delete(Session).where(Session.session_id == session_id))
    await db.commit()


async def get_user_by_session(db: AsyncSession, session_id: str) -> Optional[User]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.session_id == session_id)
        .where(Session.expires_at > now)
    )
    return result.scalars().first()
