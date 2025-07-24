# src/database/init_db.py
from src.database import Base, engine
from src.meeting import models  # ✅ safe here — won't cause circular import

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

