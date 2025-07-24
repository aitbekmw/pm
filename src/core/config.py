from enum import Enum
from pathlib import Path
from typing import List, Union

from pydantic import BaseModel, PostgresDsn, AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent

class AppEnvironment(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TESTING = "testing"

class Config(BaseSettings):
    # --- App metadata ---
    PROJECT_NAME: str = "PM Assistant"
    APP_VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    WS_PREFIX: str = "/ws"
    LOGGING_LEVEL: str = "INFO"

    # --- Environment ---
    FASTAPI_ENV: AppEnvironment = AppEnvironment.DEVELOPMENT

    # --- Database ---
    DATABASE_URL: str

    # --- CORS ---
    BACKEND_CORS_ORIGINS: List[Union[AnyHttpUrl, str]] = []
    CORS_ORIGINS: List[str] = ["*"]
    CORS_HEADERS: List[str] = ["*"]

    # --- pgAdmin support (optional) ---
    PGADMIN_EMAIL: str = "admin@example.com"
    PGADMIN_PASSWORD: str = "admin123"


    # --- S3 config ---

    # --- S3 config ---
    ENDPOINT_URL: str
    ACCESS_KEY_ID: str
    SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str
    S3_REGION_NAME: str

    # --- Pydantic Settings ---
    model_config = SettingsConfigDict(
        env_file="infra/envs/.env.dev",
        env_file_encoding="utf-8"
    )

    def is_dev(self) -> bool:
        return self.FASTAPI_ENV == AppEnvironment.DEVELOPMENT

    def is_prod(self) -> bool:
        return self.FASTAPI_ENV == AppEnvironment.PRODUCTION


settings = Config()
