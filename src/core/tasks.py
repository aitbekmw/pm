from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
import uuid
import os
import tempfile
import asyncio

from src.db.session import AsyncSessionLocal
from src.db.base import import_all_models
from src.meetings.models import Meeting, MeetingProcessing, Transcript, Summary, ActionItem
from src.core.storage import storage
from src.core.ai_services import ai_service, TranscriptionError
from src.core.pdf_generator import generate_meeting_pdf
from src.meetings import selectors
from arq.connections import RedisSettings
from src.core.config import settings
from src.core.logging import setup_logging
from src.core.telegram import start_bot_polling

import_all_models()

logger = logging.getLogger(__name__)


async def process_meeting(ctx, meeting_id: int):
    async with AsyncSessionLocal() as db:
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.audio_file_path:
            return {"error": "Meeting or audio not found"}

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
            return {"success": True, "message": "Already completed"}
        else:
            processing.status = "processing"
            processing.error_message = None
            await db.commit()

        tmp_path = None
        try:
            transcript_result = await db.execute(
                select(Transcript).where(Transcript.meeting_id == meeting_id)
            )
            transcript_obj = transcript_result.scalars().first()

            if transcript_obj:
                logger.info(f"Transcript already exists for meeting {meeting_id}. Skipping transcription.")
                formatted_transcript = transcript_obj.content
            else:
                processing.current_stage = "transcription"
                processing.progress = 10
                await db.commit()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp_path = tmp.name

                success = await storage.async_download_file_to_path(meeting.audio_file_path, tmp_path)
                if not success:
                    raise Exception("Failed to download audio file to disk")

                processing.progress = 20
                await db.commit()

                try:
                    with open(tmp_path, "rb") as audio_file:
                        transcript_data = await ai_service.transcribe_audio(
                            audio_file,
                            filename=meeting.audio_file_path.split('/')[-1]
                        )
                except TranscriptionError as te:
                    logger.warning(f"Transcription error for meeting {meeting_id}: {te} (reason={te.reason})")
                    raise

                if not transcript_data:
                    raise TranscriptionError(
                        "Транскрибация не вернула данных. Попробуйте загрузить файл повторно.",
                        reason="no_data"
                    )

                processing.progress = 50
                await db.commit()

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

                if not meeting.duration:
                    duration = transcript_data.get('duration')
                    if duration and isinstance(duration, (int, float)):
                        duration_minutes = float(duration)
                        if duration_minutes > 100:
                            duration_minutes = duration_minutes / 60
                        meeting.duration = int(round(duration_minutes))

                await db.commit()

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
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()

            return {"success": True, "meeting_id": meeting_id}

        except Exception as e:
            logger.error(f"Error processing meeting {meeting_id}: {e}", exc_info=True)
            await db.rollback()

            fail_status = "failed"
            if isinstance(e, TranscriptionError) and e.reason == "no_speech_detected":
                fail_status = "no_speech_detected"

            processing.status = fail_status
            processing.error_message = str(e)
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"error": str(e), "meeting_id": meeting_id}

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


async def process_meeting_from_subtitle(ctx, meeting_id: int):
    async with AsyncSessionLocal() as db:
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.subtitle:
            logger.error(f"Meeting {meeting_id} not found or subtitle is empty")
            return {"error": "Meeting or subtitle not found"}

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
            return {"success": True, "message": "Already completed"}
        else:
            processing.status = "processing"
            processing.error_message = None
            await db.commit()

        try:
            transcript_text = meeting.subtitle

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
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()

            return {"success": True, "meeting_id": meeting_id}

        except Exception as e:
            logger.error(f"Error processing meeting {meeting_id} from subtitle: {e}", exc_info=True)
            try:
                await db.rollback()
                processing.status = "failed"
                processing.error_message = str(e)
                processing.completed_at = datetime.now(timezone.utc)
                await db.commit()
            except Exception as commit_error:
                logger.error(f"Error updating processing status: {commit_error}", exc_info=True)
                await db.rollback()

            return {"error": str(e), "meeting_id": meeting_id}


async def send_meeting_reminder(ctx, meeting_id: int, minutes_before: int):
    """Напоминание о встрече в Telegram"""
    async with AsyncSessionLocal() as db:
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.project_id:
            return {"skipped": "No meeting or project"}

        from src.projects.models import Project
        project_result = await db.execute(select(Project).where(Project.id == meeting.project_id))
        project = project_result.scalars().first()

        if not project or not project.telegram_chat_id:
            return {"skipped": "No telegram_chat_id"}

        from src.core.telegram import send_telegram_message

        meeting_date = meeting.meeting_date
        date_str = meeting_date.strftime("%d.%m.%Y %H:%M") if isinstance(meeting_date, datetime) else str(meeting_date)

        text = (
            f"🔔 <b>Напоминание о встрече</b>\n\n"
            f"📅 <b>Название:</b> {meeting.title}\n"
            f"🕐 <b>Дата:</b> {date_str}\n"
            f"📁 <b>Проект:</b> {project.name}\n\n"
        )

        await send_telegram_message(project.telegram_chat_id, text)
        logger.info(f"Напоминание о встрече {meeting_id} отправлено за {minutes_before} мин")
        return {"success": True}


async def startup(ctx):
    """Инициализация при запуске воркера"""
    setup_logging()

    if settings.RUN_BOT:  # используем settings вместо os.getenv
        logger.info("ARQ Worker: запуск встроенного Telegram-бота...")
        asyncio.create_task(start_bot_polling())
    else:
        logger.info("ARQ Worker: запуск бота пропущен (RUN_BOT != true)")


async def shutdown(ctx):
    """Очистка при остановке воркера"""
    pass


class WorkerSettings:
    functions = [process_meeting, process_meeting_from_subtitle, send_meeting_reminder]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = 1200