from arq import create_pool
from arq.connections import RedisSettings
from typing import Optional

from src.core.config import settings


# Парсинг Redis URL
def parse_redis_url(url: str) -> dict:
    """Парсить Redis URL в параметры подключения"""
    # Простой парсер для redis://host:port
    if url.startswith('redis://'):
        url = url[8:]
    
    if ':' in url:
        host, port = url.split(':')
        return {'host': host, 'port': int(port)}
    return {'host': url, 'port': 6379}


redis_settings = RedisSettings(**parse_redis_url(settings.REDIS_URL))


async def get_redis_pool():
    """Получить пул подключений к Redis"""
    return await create_pool(redis_settings)


async def enqueue_meeting_processing(meeting_id: int):
    """Добавить задачу обработки встречи в очередь"""
    redis = await get_redis_pool()
    job = await redis.enqueue_job('process_meeting', meeting_id)
    return job.job_id

