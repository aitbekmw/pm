from arq import create_pool
from arq.connections import RedisSettings
from src.core.config import settings


redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)


async def get_redis_pool():
    """Получить пул подключений к Redis"""
    return await create_pool(redis_settings)


async def enqueue_meeting_processing(meeting_id: int):
    """Добавить задачу обработки встречи в очередь"""
    redis = await get_redis_pool()
    job = await redis.enqueue_job('process_meeting', meeting_id)
    return job.job_id


async def enqueue_meeting_processing_from_subtitle(meeting_id: int):
    """Добавить задачу обработки встречи из готового транскрипта (subtitle) в очередь"""
    redis = await get_redis_pool()
    job = await redis.enqueue_job('process_meeting_from_subtitle', meeting_id)
    return job.job_id

