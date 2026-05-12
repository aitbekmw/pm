from dataclasses import dataclass
import logging

from arq import create_pool
from arq.connections import RedisSettings
from src.core.config import settings


redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnqueueResult:
    job_id: str | None
    already_queued: bool = False


def processing_queue_lock_key(function_name: str, meeting_id: int) -> str:
    return f"meeting-processing:queue:{function_name}:{meeting_id}"


async def get_redis_pool():
    """Получить пул подключений к Redis"""
    return await create_pool(redis_settings)


async def enqueue_meeting_processing(meeting_id: int):
    """Добавить задачу обработки встречи в очередь"""
    return await _enqueue_meeting_job("process_meeting", meeting_id)


async def enqueue_meeting_processing_from_subtitle(meeting_id: int):
    """Добавить задачу обработки встречи из готового транскрипта (subtitle) в очередь"""
    return await _enqueue_meeting_job("process_meeting_from_subtitle", meeting_id)


async def _enqueue_meeting_job(function_name: str, meeting_id: int) -> EnqueueResult:
    redis = await get_redis_pool()
    lock_key = processing_queue_lock_key(function_name, meeting_id)
    lock_ttl = settings.MEETING_PROCESSING_LOCK_TTL_SECONDS

    try:
        acquired = await redis.set(lock_key, "queued", ex=lock_ttl, nx=True)
        if not acquired:
            logger.info(
                "Meeting %s already has queued/running job for %s",
                meeting_id,
                function_name,
            )
            return EnqueueResult(job_id=None, already_queued=True)

        try:
            job = await redis.enqueue_job(
                function_name,
                meeting_id,
                _expires=lock_ttl,
            )
        except Exception:
            await redis.delete(lock_key)
            raise

        if not job:
            await redis.delete(lock_key)
            return EnqueueResult(job_id=None, already_queued=True)

        return EnqueueResult(job_id=job.job_id)
    finally:
        await redis.aclose()
