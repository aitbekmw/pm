from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from contextlib import asynccontextmanager
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from src.core.config import settings
from src.core.logging import setup_logging
from src.core.admin import setup_admin
from src.users.routes import router as users_router
from src.projects.routes import router as projects_router
from src.meetings.routes import router as meetings_router
from src.notifications.routes import router as notifications_router
from src.companies.routes import router as companies_router
from src.faq.routes import router as faq_router
from src.companies.services import seed_default_companies
from src.db.session import AsyncSessionLocal

# Initialize Sentry before logging setup
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=True,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
    )

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Наполняем таблицу компаний дефолтными значениями если она пуста
    async with AsyncSessionLocal() as db:
        await seed_default_companies(db)
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)



app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.OAUTH_SESSION_SECRET,
    session_cookie="oauth_session",
    same_site="lax",
    https_only=False,
)

# CORS middleware
_CORS_ORIGINS = (
    ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"]
    if settings.debug
    else ([settings.FRONTEND_URL] if settings.FRONTEND_URL else [])
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Setup admin panel
setup_admin(app)

app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(meetings_router, prefix=settings.api_prefix)
app.include_router(notifications_router, prefix=settings.api_prefix)
app.include_router(companies_router, prefix=settings.api_prefix)
app.include_router(faq_router, prefix=settings.api_prefix)

@app.get("/")
async def root():
    return {"message": "API for meeting"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
