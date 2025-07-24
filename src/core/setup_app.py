from fastapi import FastAPI

from src.core.config import settings
from src.core.routers import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.APP_VERSION,
        docs_url=None if settings.is_prod() else "/docs",
        redoc_url=None if settings.is_prod() else "/redoc",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
    )
    setup_routers(app)
    setup_middlewares(app)
    return app


def setup_routers(app: FastAPI) -> None:
    app.include_router(api_router, prefix=settings.API_V1_STR)


def setup_middlewares(app: FastAPI) -> None:
    pass
