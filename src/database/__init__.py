from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.core.config import settings


Base = declarative_base()

# Async engine using asyncpg
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.LOGGING_LEVEL == "DEBUG",
)

# Async session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)



# Dependency for FastAPI routes (async)
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
