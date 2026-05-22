from datetime import datetime

from arq import create_pool
from arq.connections import RedisSettings
from src.core.config import settings

# Глобальная переменная для хранения пула
_redis_pool = None

async def get_redis_pool():
    """
    Возвращает существующий пул подключений к Redis или создает новый.
    Это предотвращает создание множества соединений и утечки ресурсов.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    return _redis_pool

async def enqueue_meeting_processing(meeting_id: int):
    """Добавить задачу обработки встречи в очередь"""
    redis = await get_redis_pool()
    job = await redis.enqueue_job('process_meeting', meeting_id)
    return job.job_id

async def enqueue_meeting_processing_from_subtitle(meeting_id: int):
    """Добавить задачу обработки встречи из готового транскрипта в очередь"""
    redis = await get_redis_pool()
    job = await redis.enqueue_job('process_meeting_from_subtitle', meeting_id)
    return job.job_id

async def enqueue_meeting_reminder(meeting_id: int, minutes: int, defer_until: datetime):
    """Добавить задачу напоминания в очередь"""
    redis = await get_redis_pool()
    job = await redis.enqueue_job(
        "send_meeting_reminder",
        meeting_id,
        minutes,
        _defer_until=defer_until
    )
    return job.job_id