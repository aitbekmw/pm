from authlib.integrations.starlette_client import OAuth
from src.core.config import settings

oauth = OAuth()

# M-Market — креды уже есть
oauth.register(
    name="google_mmarket",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# MInvest — регистрируем провайдер только если креды уже заданы в .env
if settings.MINVEST_GOOGLE_CLIENT_ID and settings.MINVEST_GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google_minvest",
        client_id=settings.MINVEST_GOOGLE_CLIENT_ID,
        client_secret=settings.MINVEST_GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
