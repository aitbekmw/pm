from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import io
import logging
import uuid
import os
import tempfile
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from src.db.session import AsyncSessionLocal
from src.db.base import import_all_models
from src.meetings.models import Meeting, MeetingProcessing, Transcript, Summary, ActionItem
from src.core.storage import storage
from src.core.ai_services import ai_service, RetryableAIServiceError, TranscriptionError
from src.core.pdf_generator import generate_meeting_pdf
from src.core.queue import processing_queue_lock_key
from src.meetings import selectors
from arq import Retry
from arq.connections import RedisSettings
from src.core.config import settings
from src.core.logging import setup_logging

# Импортируем все модели для правильной инициализации ForeignKey
import_all_models()

logger = logging.getLogger(__name__)


def init_worker_sentry() -> None:
    if not settings.SENTRY_ARQ_DSN or sentry_sdk.is_initialized():
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_ARQ_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=True,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            SqlalchemyIntegration(),
        ],
    )
    sentry_sdk.set_tag("service", "worker")


def processing_running_lock_key(function_name: str, meeting_id: int) -> str:
    return f"meeting-processing:running:{function_name}:{meeting_id}"


async def acquire_running_lock(ctx, function_name: str, meeting_id: int) -> str | None:
    redis = ctx["redis"]
    lock_key = processing_running_lock_key(function_name, meeting_id)
    token = uuid.uuid4().hex
    acquired = await redis.set(
        lock_key,
        token,
        ex=settings.MEETING_PROCESSING_LOCK_TTL_SECONDS,
        nx=True,
    )
    if not acquired:
        logger.info(
            "Meeting %s already running for %s. Skipping duplicate job.",
            meeting_id,
            function_name,
        )
        return None
    return token


async def release_processing_locks(
    ctx,
    function_name: str,
    meeting_id: int,
    running_token: str | None,
    release_queue_lock: bool,
) -> None:
    redis = ctx["redis"]
    running_key = processing_running_lock_key(function_name, meeting_id)
    queue_key = processing_queue_lock_key(function_name, meeting_id)

    if running_token:
        current_token = await redis.get(running_key)
        if current_token in {running_token, running_token.encode()}:
            await redis.delete(running_key)

    if release_queue_lock:
        await redis.delete(queue_key)


async def refresh_queue_lock(ctx, function_name: str, meeting_id: int) -> None:
    await ctx["redis"].set(
        processing_queue_lock_key(function_name, meeting_id),
        "retrying",
        ex=settings.MEETING_PROCESSING_LOCK_TTL_SECONDS,
    )


def is_retryable_processing_error(error: Exception) -> bool:
    return isinstance(error, RetryableAIServiceError) or (
        isinstance(error, TranscriptionError) and error.retry_after is not None
    )


def processing_retry_delay(ctx, error: Exception) -> int:
    job_try = max(1, int(ctx.get("job_try") or 1))

    if isinstance(error, RetryableAIServiceError):
        base_delay = error.retry_after
        max_delay = settings.GEMINI_RETRY_MAX_DEFER_SECONDS
    elif isinstance(error, TranscriptionError):
        base_delay = error.retry_after or settings.WHISPER_RETRY_DEFER_SECONDS
        max_delay = settings.WHISPER_RETRY_MAX_DEFER_SECONDS
    else:
        base_delay = settings.GEMINI_RETRY_DEFER_SECONDS
        max_delay = settings.GEMINI_RETRY_MAX_DEFER_SECONDS

    return min(max_delay, max(1, base_delay) * (2 ** max(0, job_try - 1)))


async def mark_processing_retrying(
    ctx,
    db: AsyncSession,
    processing: MeetingProcessing,
    function_name: str,
    meeting_id: int,
    error: Exception,
) -> int:
    delay = processing_retry_delay(ctx, error)
    await db.rollback()
    processing.status = "processing"
    processing.error_message = f"Внешний сервис временно недоступен, повтор через {delay} секунд: {error}"
    processing.started_at = datetime.now(timezone.utc)
    processing.completed_at = None
    await db.commit()
    await refresh_queue_lock(ctx, function_name, meeting_id)
    return delay


async def mark_processing_failed(
    db: AsyncSession,
    processing: MeetingProcessing,
    error: Exception,
) -> None:
    await db.rollback()

    status = "failed"
    if isinstance(error, TranscriptionError) and error.reason == "no_speech_detected":
        status = "no_speech_detected"

    processing.status = status
    processing.error_message = str(error)
    processing.completed_at = datetime.now(timezone.utc)
    await db.commit()


async def process_meeting(ctx, meeting_id: int):
    """Фоновая задача для обработки встречи (транскрибация + суммаризация)"""
    function_name = "process_meeting"
    running_token = await acquire_running_lock(ctx, function_name, meeting_id)
    if not running_token:
        return {"success": True, "message": "Already running", "meeting_id": meeting_id}

    release_queue_lock = True
    async with AsyncSessionLocal() as db:
        # Получить встречу
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.audio_file_path:
            await release_processing_locks(
                ctx, function_name, meeting_id, running_token, release_queue_lock
            )
            return {"error": "Meeting or audio not found"}
        
        # Создать или обновить статус обработки
        processing_result = await db.execute(
            select(MeetingProcessing).where(MeetingProcessing.meeting_id == meeting_id)
        )
        processing = processing_result.scalars().first()
        
        if not processing:
            processing = MeetingProcessing(
                meeting_id=meeting_id,
                status="processing",
                current_stage="initializing",
                progress=0,
                started_at=datetime.now(timezone.utc)
            )
            db.add(processing)
            await db.commit()
        elif processing.status == "completed":
            logger.info(f"Meeting {meeting_id} already processed. Skipping.")
            await release_processing_locks(
                ctx, function_name, meeting_id, running_token, release_queue_lock
            )
            return {"success": True, "message": "Already completed"}
        else:
            processing.status = "processing"
            processing.error_message = None
            await db.commit()
        
        tmp_path = None
        try:
            # Шаг 1: Транскрибация (проверяем, есть ли уже транскрипт)
            transcript_result = await db.execute(
                select(Transcript).where(Transcript.meeting_id == meeting_id)
            )
            transcript_obj = transcript_result.scalars().first()
            
            if transcript_obj:
                logger.info(f"Transcript already exists for meeting {meeting_id}. Skipping transcription.")
                formatted_transcript = transcript_obj.content
                transcript_text = formatted_transcript # Fallback if timestamps not needed
            else:
                processing.current_stage = "transcription"
                processing.progress = 10
                await db.commit()
                
                # Скачать аудио из S3 на диск
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp_path = tmp.name
                
                success = await storage.async_download_file_to_path(meeting.audio_file_path, tmp_path)
                if not success:
                    raise Exception("Failed to download audio file to disk")
                
                processing.progress = 20
                await db.commit()
                
                # Транскрибировать
                try:
                    with open(tmp_path, "rb") as audio_file:
                        transcript_data = await ai_service.transcribe_audio(
                            audio_file, 
                            filename=meeting.audio_file_path.split('/')[-1]
                        )
                except TranscriptionError as te:
                    logger.warning(f"Transcription error for meeting {meeting_id}: {te} (reason={te.reason})")
                    raise  # Пробрасываем — сообщение сохранится в error_message
                
                if not transcript_data:
                    raise TranscriptionError(
                        "Транскрибация не вернула данных. Попробуйте загрузить файл повторно.",
                        reason="no_data"
                    )
                
                processing.progress = 50
                await db.commit()
                
                # Сохранить транскрипт
                transcript_text = transcript_data.get('text', '')
                if not transcript_text:
                    raise TranscriptionError(
                        "В аудиозаписи не обнаружена речь. Убедитесь, что файл содержит голосовые данные.",
                        reason="no_speech_detected"
                    )
                
                processing.current_stage = "transcription_formatting"
                processing.progress = 55
                await db.commit()
                
                formatted_transcript = await ai_service.format_transcript(transcript_text)
                
                segments = transcript_data.get('segments', [])
                if segments:
                    updated_segments = await ai_service.format_segments(segments)
                    transcript_data['segments'] = updated_segments
                
                transcript_obj = Transcript(
                    meeting_id=meeting_id,
                    content=formatted_transcript,
                    timestamps=transcript_data
                )
                db.add(transcript_obj)
                
                # Обновить длительность
                if not meeting.duration:
                    duration = transcript_data.get('duration')
                    if duration and isinstance(duration, (int, float)):
                        duration_minutes = float(duration)
                        if duration_minutes > 100:
                            duration_minutes = duration_minutes / 60
                        meeting.duration = int(round(duration_minutes))
                
                await db.commit()
            
            # Шаг 2: Суммаризация (проверяем, есть ли уже суммаризация)
            summary_result = await db.execute(
                select(Summary).where(Summary.meeting_id == meeting_id)
            )
            summary_obj = summary_result.scalars().first()
            
            if summary_obj:
                logger.info(f"Summary already exists for meeting {meeting_id}. Skipping summarization.")
                summary_text = summary_obj.content
            else:
                processing.current_stage = "summarization"
                processing.progress = 60
                await db.commit()
                
                summary_text = await ai_service.summarize_transcript(formatted_transcript, meeting.title)
                if not summary_text:
                    raise Exception("Summarization failed")
                
                summary_obj = Summary(meeting_id=meeting_id, content=summary_text)
                db.add(summary_obj)
                await db.commit()

            # Шаг 3: Извлечение action items (только если их еще нет)
            ai_result = await db.execute(
                select(ActionItem).where(ActionItem.meeting_id == meeting_id)
            )
            if not ai_result.scalars().first():
                processing.current_stage = "action_items"
                processing.progress = 90
                await db.commit()
                
                action_items = await ai_service.extract_action_items(formatted_transcript)
                if action_items and isinstance(action_items, list):
                    for item in action_items:
                        if isinstance(item, dict):
                            db.add(ActionItem(
                                meeting_id=meeting_id,
                                title=item.get('title', 'Untitled'),
                                description=item.get('description'),
                                status='pending'
                            ))
                    await db.commit()

            # Шаг 4: Генерация PDF (только если его еще нет)
            if not meeting.pdf_file_path:
                processing.current_stage = "pdf_generation"
                processing.progress = 95
                await db.commit()
                
                notes_list = await selectors.get_meeting_notes(db, meeting_id)
                notes_data = [{'content': n.content or '', 'created_at': n.created_at} for n in notes_list]
                
                organizer_name = None
                if meeting.organizer:
                    organizer_name = f"{meeting.organizer.first_name} {meeting.organizer.last_name}".strip()
                
                pdf_buffer = generate_meeting_pdf(
                    title=meeting.title,
                    meeting_date=meeting.meeting_date,
                    duration=meeting.duration,
                    transcript=formatted_transcript,
                    summary=summary_text,
                    notes=notes_data,
                    organizer_name=organizer_name
                )
                
                pdf_path = f"meetings/{uuid.uuid4()}.pdf"
                pdf_s3_path, _ = storage.upload_file(pdf_buffer, pdf_path, content_type="application/pdf")
                
                if pdf_s3_path:
                    meeting.pdf_file_path = pdf_s3_path
                    await db.commit()
            
            processing.status = "completed"
            processing.current_stage = "completed"
            processing.progress = 100
            processing.error_message = None
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            return {"success": True, "meeting_id": meeting_id}
            
        except (RetryableAIServiceError, TranscriptionError) as e:
            if (
                is_retryable_processing_error(e)
                and int(ctx.get("job_try") or 1) < settings.WORKER_MAX_TRIES
            ):
                logger.warning(
                    "Retryable processing error for meeting %s: %s",
                    meeting_id,
                    e,
                )
                release_queue_lock = False
                delay = await mark_processing_retrying(
                    ctx, db, processing, function_name, meeting_id, e
                )
                raise Retry(defer=delay)

            logger.error(f"Error processing meeting {meeting_id}: {e}", exc_info=True)
            await mark_processing_failed(db, processing, e)
            return {"error": str(e), "meeting_id": meeting_id}

        except Exception as e:
            logger.error(f"Error processing meeting {meeting_id}: {e}", exc_info=True)
            await mark_processing_failed(db, processing, e)
            return {"error": str(e), "meeting_id": meeting_id}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            await release_processing_locks(
                ctx, function_name, meeting_id, running_token, release_queue_lock
            )


async def process_meeting_from_subtitle(ctx, meeting_id: int):
    """Фоновая задача для обработки встречи из готового транскрипта (subtitle).
    Пропускает транскрибацию — сразу суммаризация + action items + PDF.
    """
    function_name = "process_meeting_from_subtitle"
    running_token = await acquire_running_lock(ctx, function_name, meeting_id)
    if not running_token:
        return {"success": True, "message": "Already running", "meeting_id": meeting_id}

    release_queue_lock = True
    async with AsyncSessionLocal() as db:
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.subtitle:
            logger.error(f"Meeting {meeting_id} not found or subtitle is empty")
            await release_processing_locks(
                ctx, function_name, meeting_id, running_token, release_queue_lock
            )
            return {"error": "Meeting or subtitle not found"}

        # Создать или обновить статус обработки
        processing_result = await db.execute(
            select(MeetingProcessing).where(MeetingProcessing.meeting_id == meeting_id)
        )
        processing = processing_result.scalars().first()

        if not processing:
            processing = MeetingProcessing(
                meeting_id=meeting_id,
                status="processing",
                current_stage="initializing",
                progress=0,
                started_at=datetime.now(timezone.utc)
            )
            db.add(processing)
            await db.commit()
        elif processing.status == "completed":
            await release_processing_locks(
                ctx, function_name, meeting_id, running_token, release_queue_lock
            )
            return {"success": True, "message": "Already completed"}
        else:
            processing.status = "processing"
            processing.error_message = None
            await db.commit()

        try:
            transcript_text = meeting.subtitle
            
            # 1. Transcript
            transcript_result = await db.execute(
                select(Transcript).where(Transcript.meeting_id == meeting_id)
            )
            transcript_obj = transcript_result.scalars().first()
            if not transcript_obj:
                processing.current_stage = "transcription_formatting"
                processing.progress = 20
                await db.commit()
                
                formatted_transcript = await ai_service.format_transcript(transcript_text)
                transcript_obj = Transcript(meeting_id=meeting_id, content=formatted_transcript)
                db.add(transcript_obj)
                await db.commit()
            else:
                formatted_transcript = transcript_obj.content

            # 2. Summary
            summary_result = await db.execute(select(Summary).where(Summary.meeting_id == meeting_id))
            summary_obj = summary_result.scalars().first()
            if not summary_obj:
                processing.current_stage = "summarization"
                processing.progress = 40
                await db.commit()
                
                summary_text = await ai_service.summarize_transcript(transcript_text, meeting.title)
                if not summary_text:
                    raise Exception("Summarization failed")
                
                summary_obj = Summary(meeting_id=meeting_id, content=summary_text)
                db.add(summary_obj)
                await db.commit()
            else:
                summary_text = summary_obj.content

            # 3. Action Items
            ai_result = await db.execute(select(ActionItem).where(ActionItem.meeting_id == meeting_id))
            if not ai_result.scalars().first():
                processing.current_stage = "action_items"
                processing.progress = 80
                await db.commit()
                
                action_items = await ai_service.extract_action_items(transcript_text)
                if action_items and isinstance(action_items, list):
                    for item in action_items:
                        if isinstance(item, dict):
                            db.add(ActionItem(
                                meeting_id=meeting_id,
                                title=item.get('title', 'Untitled'),
                                description=item.get('description'),
                                status='pending'
                            ))
                    await db.commit()

            # 4. PDF
            if not meeting.pdf_file_path:
                processing.current_stage = "pdf_generation"
                processing.progress = 90
                await db.commit()
                
                notes_list = await selectors.get_meeting_notes(db, meeting_id)
                notes_data = [{'content': n.content or '', 'created_at': n.created_at} for n in notes_list]
                
                organizer_name = None
                if meeting.organizer:
                    organizer_name = f"{meeting.organizer.first_name} {meeting.organizer.last_name}".strip()
                
                pdf_buffer = generate_meeting_pdf(
                    title=meeting.title,
                    meeting_date=meeting.meeting_date,
                    duration=meeting.duration,
                    transcript=formatted_transcript,
                    summary=summary_text,
                    notes=notes_data,
                    organizer_name=organizer_name
                )
                
                pdf_path = f"meetings/{uuid.uuid4()}.pdf"
                pdf_s3_path, _ = storage.upload_file(pdf_buffer, pdf_path, content_type="application/pdf")
                if pdf_s3_path:
                    meeting.pdf_file_path = pdf_s3_path
                    await db.commit()

            processing.status = "completed"
            processing.current_stage = "completed"
            processing.progress = 100
            processing.error_message = None
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()

            return {"success": True, "meeting_id": meeting_id}

        except RetryableAIServiceError as e:
            if int(ctx.get("job_try") or 1) < settings.WORKER_MAX_TRIES:
                logger.warning(
                    "Retryable subtitle processing error for meeting %s: %s",
                    meeting_id,
                    e,
                )
                release_queue_lock = False
                delay = await mark_processing_retrying(
                    ctx, db, processing, function_name, meeting_id, e
                )
                raise Retry(defer=delay)

            logger.error(f"Error processing meeting {meeting_id} from subtitle: {e}", exc_info=True)
            await mark_processing_failed(db, processing, e)
            return {"error": str(e), "meeting_id": meeting_id}

        except Exception as e:
            logger.error(f"Error processing meeting {meeting_id} from subtitle: {e}", exc_info=True)
            try:
                await mark_processing_failed(db, processing, e)
            except Exception as commit_error:
                logger.error(f"Error updating processing status: {commit_error}", exc_info=True)
                await db.rollback()

            return {"error": str(e), "meeting_id": meeting_id}
        finally:
            await release_processing_locks(
                ctx, function_name, meeting_id, running_token, release_queue_lock
            )


async def startup(ctx):
    """Инициализация при запуске воркера"""
    init_worker_sentry()
    setup_logging()


async def shutdown(ctx):
    """Очистка при остановке воркера"""
    pass


# Конфигурация ARQ воркера
class WorkerSettings:
    functions = [process_meeting, process_meeting_from_subtitle]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = 1200
    max_jobs = settings.WORKER_MAX_JOBS
    queue_read_limit = settings.WORKER_MAX_JOBS
    max_tries = settings.WORKER_MAX_TRIES
