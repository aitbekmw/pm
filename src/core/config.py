from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict
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
    LDAP_SERVER: str = Field(default=" ", env="LDAP_SERVER")
    LDAP_BASE_DN: str = Field(default="DC=mdigital,DC=local", env="LDAP_BASE_DN")
    LDAP_USER_DN: str = Field(default="mdigital", env="LDAP_USER_DN")
    LDAP_SERVICE_USER: str = Field(default="pm.assistant", env="LDAP_SERVICE_USER")
    LDAP_ADMIN_GROUP: str = Field(default="CN=Staff,OU=Groups,DC=mdigital,DC=local", env="LDAP_ADMIN_GROUP")
    LDAP_SERVICE_PASSWORD: str = Field(default=" ", env="LDAP_SERVICE_PASSWORD")
    
    # Legacy AD fields (for backward compatibility)
    AD_SERVER: str = Field(default="ldap://ad.example.com", env="AD_SERVER")
    AD_DOMAIN: str = Field(default="EXAMPLE", env="AD_DOMAIN")
    AD_BASE_DN: str = Field(default="DC=example,DC=com", env="AD_BASE_DN")
    AD_USE_NTLM: bool = Field(default=True, env="AD_USE_NTLM")

    # Session
    SESSION_TTL_DAYS: int = Field(default=30, env="SESSION_TTL_DAYS")
    COOKIE_DOMAIN: Optional[str] = Field(default=None, env="COOKIE_DOMAIN")

    # S3 / MinIO
    S3_ENDPOINT_URL: str = Field(..., env="S3_ENDPOINT_URL")
    S3_PUBLIC_URL: str = Field(..., env="S3_PUBLIC_URL")
    S3_ACCESS_KEY: str = Field(..., env="S3_ACCESS_KEY")
    S3_SECRET_KEY: str = Field(..., env="S3_SECRET_KEY")
    S3_BUCKET_NAME: str = Field(default="pm-assistant", env="S3_BUCKET_NAME")
    S3_REGION: str = Field(default="us-east-1", env="S3_REGION")

    # OpenAI (закомментировано - переходим на Gemini)
    # OPENAI_API_KEY: str = Field(..., env="OPENAI_API_KEY")
    # WHISPER_MODEL: str = Field(default="whisper-1", env="WHISPER_MODEL")
    # GPT_MODEL: str = Field(default="gpt-4-turbo-preview", env="GPT_MODEL")
    
    # Gemini
    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash", env="GEMINI_MODEL")
    
    # Whisper Transcription (Local or OpenAI)
    WHISPER_SERVER_URL: Optional[str] = Field(default="http://10.0.10.3:8000/transcribe", env="WHISPER_SERVER_URL")
    USE_LOCAL_WHISPER: bool = Field(default=True, env="USE_LOCAL_WHISPER")
    WHISPER_TIMEOUT_SECONDS: float = Field(default=600.0, env="WHISPER_TIMEOUT_SECONDS")
    WHISPER_CONNECT_TIMEOUT_SECONDS: float = Field(default=15.0, env="WHISPER_CONNECT_TIMEOUT_SECONDS")
    WHISPER_RETRY_DEFER_SECONDS: int = Field(default=60, env="WHISPER_RETRY_DEFER_SECONDS")
    WHISPER_RETRY_MAX_DEFER_SECONDS: int = Field(default=600, env="WHISPER_RETRY_MAX_DEFER_SECONDS")

    # Gemini throttling/retries
    GEMINI_REQUEST_TIMEOUT_SECONDS: float = Field(default=120.0, env="GEMINI_REQUEST_TIMEOUT_SECONDS")
    GEMINI_REQUEST_MAX_ATTEMPTS: int = Field(default=2, env="GEMINI_REQUEST_MAX_ATTEMPTS")
    GEMINI_REQUEST_INITIAL_BACKOFF_SECONDS: float = Field(default=5.0, env="GEMINI_REQUEST_INITIAL_BACKOFF_SECONDS")
    GEMINI_REQUEST_MAX_BACKOFF_SECONDS: float = Field(default=30.0, env="GEMINI_REQUEST_MAX_BACKOFF_SECONDS")
    GEMINI_RETRY_DEFER_SECONDS: int = Field(default=60, env="GEMINI_RETRY_DEFER_SECONDS")
    GEMINI_RETRY_MAX_DEFER_SECONDS: int = Field(default=600, env="GEMINI_RETRY_MAX_DEFER_SECONDS")

    # Redis for ARQ
    REDIS_URL: str = Field(default="redis://redis:6379", env="REDIS_URL")
    WORKER_MAX_JOBS: int = Field(default=1, env="WORKER_MAX_JOBS")
    WORKER_MAX_TRIES: int = Field(default=8, env="WORKER_MAX_TRIES")
    MEETING_PROCESSING_LOCK_TTL_SECONDS: int = Field(default=7200, env="MEETING_PROCESSING_LOCK_TTL_SECONDS")
    
    # Sentry
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    SENTRY_ARQ_DSN: Optional[str] = Field(default=None, env="SENTRY_ARQ_DSN")
    SENTRY_ENVIRONMENT: str = Field(default="production", env="SENTRY_ENVIRONMENT")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.005, env="SENTRY_TRACES_SAMPLE_RATE")

    TELEGRAM_BOT_TOKEN: str = Field(default="", env="TELEGRAM_BOT_TOKEN")


    # OAuth session secret (для SessionMiddleware / CSRF-защита)
    # ВАЖНО: в продакшне задайте случайную строку через переменную окружения OAUTH_SESSION_SECRET
    OAUTH_SESSION_SECRET: str = Field(default=None, env="OAUTH_SESSION_SECRET")

    # Google OAuth — M-Market
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, env="GOOGLE_CLIENT_SECRET")

    # Google OAuth — MInvest (креды ожидаются)
    MINVEST_GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, env="MINVEST_GOOGLE_CLIENT_ID")
    MINVEST_GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, env="MINVEST_GOOGLE_CLIENT_SECRET")

    # Общий callback URI (один для обоих)
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:8000/api/users/auth/google/callback", env="GOOGLE_REDIRECT_URI")

    FRONTEND_URL: str = Field(default="http://localhost:3000", env="FRONTEND_URL")

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

settings = Settings()

