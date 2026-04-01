from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import io
import logging
import uuid
import os
import tempfile

from src.db.session import AsyncSessionLocal
from src.db.base import import_all_models
from src.meetings.models import Meeting, MeetingProcessing, Transcript, Summary, ActionItem
from src.core.storage import storage
from src.core.ai_services import ai_service
from src.core.pdf_generator import generate_meeting_pdf
from src.meetings import selectors
from arq.connections import RedisSettings
from src.core.config import settings
from src.core.logging import setup_logging

# Импортируем все модели для правильной инициализации ForeignKey
import_all_models()

logger = logging.getLogger(__name__)


async def process_meeting(ctx, meeting_id: int):
    """Фоновая задача для обработки встречи (транскрибация + суммаризация)"""
    async with AsyncSessionLocal() as db:
        # Получить встречу
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.audio_file_path:
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
                with open(tmp_path, "rb") as audio_file:
                    transcript_data = await ai_service.transcribe_audio(
                        audio_file, 
                        filename=meeting.audio_file_path.split('/')[-1]
                    )
                
                if not transcript_data:
                    raise Exception("Transcription failed")
                
                processing.progress = 50
                await db.commit()
                
                # Сохранить транскрипт
                transcript_text = transcript_data.get('text', '')
                if not transcript_text:
                    raise Exception("Transcript text is empty")
                
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
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            return {"success": True, "meeting_id": meeting_id}
            
        except Exception as e:
            logger.error(f"Error processing meeting {meeting_id}: {e}", exc_info=True)
            await db.rollback()
            processing.status = "failed"
            processing.error_message = str(e)
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"error": str(e), "meeting_id": meeting_id}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


async def process_meeting_from_subtitle(ctx, meeting_id: int):
    """Фоновая задача для обработки встречи из готового транскрипта (subtitle).
    Пропускает транскрибацию — сразу суммаризация + action items + PDF.
    """
    async with AsyncSessionLocal() as db:
        meeting = await selectors.get_meeting_by_id(db, meeting_id)
        if not meeting or not meeting.subtitle:
            logger.error(f"Meeting {meeting_id} not found or subtitle is empty")
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


async def startup(ctx):
    """Инициализация при запуске воркера"""
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

