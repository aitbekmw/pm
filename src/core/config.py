from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    DB_POOL_SIZE: int = Field(default=10, env="DB_POOL_SIZE")
    DB_MAX_OVERFLOW: int = Field(default=20, env="DB_MAX_OVERFLOW")
    
    # App
    app_name: str = Field(default="RAG Backend", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")
    
    # API
    api_prefix: str = Field(default="/api", env="API_PREFIX")

    # LDAP / AD
    AD_SERVER: str = Field(default="ldap://ad.example.com", env="AD_SERVER")
    AD_DOMAIN: str = Field(default="EXAMPLE", env="AD_DOMAIN")
    AD_BASE_DN: str = Field(default="DC=example,DC=com", env="AD_BASE_DN")
    AD_USE_NTLM: bool = Field(default=True, env="AD_USE_NTLM")

    # Session
    SESSION_TTL_DAYS: int = Field(default=30, env="SESSION_TTL_DAYS")

    # S3 / MinIO
    S3_ENDPOINT_URL: str = Field(..., env="S3_ENDPOINT_URL")
    S3_ACCESS_KEY: str = Field(..., env="S3_ACCESS_KEY")
    S3_SECRET_KEY: str = Field(..., env="S3_SECRET_KEY")
    S3_BUCKET_NAME: str = Field(default="pm-assistant", env="S3_BUCKET_NAME")
    S3_REGION: str = Field(default="us-east-1", env="S3_REGION")

    # OpenAI
    OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    WHISPER_MODEL: str = Field(default="whisper-1", env="WHISPER_MODEL")
    GPT_MODEL: str = Field(default="gpt-4-turbo-preview", env="GPT_MODEL")

    # Redis for ARQ
    REDIS_URL: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
