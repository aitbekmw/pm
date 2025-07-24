from ldap3 import Server, Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

'''

# 👇 Hardcoded settings
LDAP_SERVER = "ldap://your.ad.server"
LDAP_DOMAIN = "mdigital.kg"
LDAP_BASE_DN = "dc=mdigital,dc=kg"# not used here, but useful if needed

def authenticate_with_ldap(login: str, password: str) -> bool:
    try:
        # Bind format: user@domain
        user_dn = f"{login}@{LDAP_DOMAIN}"

        server = Server(LDAP_SERVER, get_info=None)
        conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        return conn.bind()
    except Exception as e:
        print(f"[LDAP AUTH ERROR] {e}")
        return False


async def get_or_create_profile(login: str, db: AsyncSession) -> Profile:
    result = await db.execute(select(Profile).where(Profile.login == login))
    profile = result.scalars().first()

    if profile:
        return profile

    profile = Profile(
        login=login,
        first_name="LDAP",
        last_name="User",
        email=f"{login}@{LDAP_DOMAIN}",
        is_active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile
