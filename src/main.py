from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"] if settings.debug else [],
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

@app.get("/")
async def root():
    return {"message": "API for meeting"}

@app.get("/health")
async def health():
    return {"status": "ok"}
