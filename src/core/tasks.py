from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import io
import logging
import uuid

from src.db.session import AsyncSessionLocal
from src.db.base import import_all_models
from src.meetings.models import Meeting, MeetingProcessing, Transcript, Summary
from src.core.storage import storage
from src.core.ai_services import ai_service
from src.core.pdf_generator import generate_meeting_pdf
from src.meetings import selectors
from arq.connections import RedisSettings
from src.core.config import settings
import uuid
import io

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
                current_stage="transcription",
                progress=0,
                started_at=datetime.now(timezone.utc)
            )
            db.add(processing)
            await db.commit()
        else:
            processing.status = "processing"
            processing.current_stage = "transcription"
            processing.progress = 0
            processing.started_at = datetime.now(timezone.utc)
            processing.error_message = None
            await db.commit()
        
        try:
            # Шаг 1: Транскрибация
            processing.current_stage = "transcription"
            processing.progress = 10
            await db.commit()
            
            # Скачать аудио из S3
            audio_data = storage.download_file(meeting.audio_file_path)
            if not audio_data:
                raise Exception("Failed to download audio file")
            
            processing.progress = 20
            await db.commit()
            
            # Транскрибировать
            audio_file = io.BytesIO(audio_data)
            transcript_data = await ai_service.transcribe_audio(
                audio_file, 
                filename=meeting.audio_file_path.split('/')[-1]
            )
            
            if not transcript_data:
                raise Exception("Transcription failed")
            
            processing.progress = 50
            await db.commit()
            
            # Сохранить транскрипт
            # Убеждаемся, что transcript_data - это словарь
            if not isinstance(transcript_data, dict):
                raise Exception(f"Invalid transcript data format: expected dict, got {type(transcript_data)}")
            
            transcript_text = transcript_data.get('text', '')
            if not transcript_text:
                raise Exception("Transcript text is empty")
            
            # Форматирование транскрипта
            processing.current_stage = "transcription_formatting"
            processing.progress = 55
            await db.commit()
            
            formatted_transcript = await ai_service.format_transcript(transcript_text)
            
            transcript_obj = Transcript(
                meeting_id=meeting_id,
                content=formatted_transcript,
                timestamps=transcript_data
            )
            db.add(transcript_obj)
            await db.commit()
            
            # Обновить длительность встречи если её не было
            # Duration может быть в секундах или минутах в зависимости от источника
            if not meeting.duration:
                duration = transcript_data.get('duration')
                
                if duration:
                    # Если это float или очень большое число, вероятно в секундах
                    if isinstance(duration, (int, float)):
                        duration_minutes = float(duration)
                        
                        # Если duration > 1000 секунд (~16+ минут), это вероятно секунды
                        if duration_minutes > 100:
                            duration_minutes = duration_minutes / 60
                        
                        meeting.duration = int(round(duration_minutes))
                        logger.info(f"Updated meeting duration: {meeting.duration} minutes (from {duration})")
                        await db.commit()
            
            # Шаг 2: Суммаризация
            processing.current_stage = "summarization"
            processing.progress = 60
            await db.commit()
            
            logger.info(f"Starting summarization for meeting {meeting_id}...")
            logger.debug(f"Transcript length: {len(transcript_text)} characters")
            
            summary_text = await ai_service.summarize_transcript(
                transcript_text,
                meeting.title
            )
            
            logger.debug(f"Summarization result: {summary_text[:100] if summary_text else 'None'}...")
            
            if not summary_text:
                logger.error(f"Summarization returned None or empty for meeting {meeting_id}")
                logger.error(f"Meeting ID: {meeting_id}, Title: {meeting.title}, Transcript length: {len(transcript_text)}")
                raise Exception("Summarization failed")
            
            processing.progress = 80
            await db.commit()
            
            # Сохранить суммаризацию
            summary_obj = Summary(
                meeting_id=meeting_id,
                content=summary_text
            )
            db.add(summary_obj)
            await db.commit()
            
            # Шаг 3: Извлечение action items
            processing.current_stage = "action_items"
            processing.progress = 90
            await db.commit()
            
            action_items = await ai_service.extract_action_items(transcript_text)
            
            if action_items:
                from src.meetings.models import ActionItem
                # Убеждаемся, что action_items - это список
                if isinstance(action_items, list):
                    for item in action_items:
                        if isinstance(item, dict):
                            action_item = ActionItem(
                                meeting_id=meeting_id,
                                title=item.get('title', 'Untitled'),
                                description=item.get('description'),
                                status='pending'
                            )
                            db.add(action_item)
                    await db.commit()
            
            # Шаг 4: Генерация PDF
            processing.current_stage = "pdf_generation"
            processing.progress = 95
            await db.commit()
            
            logger.info(f"Starting PDF generation for meeting {meeting_id}...")
            
            # Получить заметки для PDF
            notes_list = await selectors.get_meeting_notes(db, meeting_id)
            notes_data = []
            for note in notes_list:
                notes_data.append({
                    'content': note.content or '',
                    'created_at': note.created_at
                })
            
            # Получить имя организатора
            organizer_name = None
            if meeting.organizer:
                organizer_name = f"{meeting.organizer.first_name} {meeting.organizer.last_name}".strip()
            
            # Генерировать PDF
            pdf_buffer = generate_meeting_pdf(
                title=meeting.title,
                meeting_date=meeting.meeting_date,
                duration=meeting.duration,
                transcript=formatted_transcript,
                summary=summary_text,
                notes=notes_data,
                organizer_name=organizer_name
            )
            
            # Загрузить PDF в S3
            pdf_path = f"meetings/{uuid.uuid4()}.pdf"
            pdf_buffer.seek(0)  # Вернуться в начало буфера
            pdf_file_obj = io.BytesIO(pdf_buffer.read())
            pdf_s3_path = storage.upload_file(pdf_file_obj, pdf_path, content_type="application/pdf")
            
            if pdf_s3_path:
                meeting.pdf_file_path = pdf_s3_path
                await db.commit()
                logger.info(f"PDF uploaded to S3: {pdf_s3_path}")
            else:
                logger.error(f"Failed to upload PDF to S3 for meeting {meeting_id}")
            
            # Завершить обработку
            processing.status = "completed"
            processing.current_stage = "completed"
            processing.progress = 100
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            logger.info(f"Meeting {meeting_id} processing completed successfully")
            return {
                "success": True,
                "meeting_id": meeting_id,
                "transcript_length": len(transcript_text),
                "action_items_count": len(action_items) if action_items else 0
            }
            
        except Exception as e:
            # Обработка ошибок
            logger.error(f"Error processing meeting {meeting_id}: {e}", exc_info=True)
            try:
                # Откатываем транзакцию перед обновлением статуса
                await db.rollback()
                
                # Обновляем статус обработки
                processing.status = "failed"
                processing.error_message = str(e)
                processing.completed_at = datetime.now(timezone.utc)
                await db.commit()
            except Exception as commit_error:
                logger.error(f"Error updating processing status: {commit_error}", exc_info=True)
                await db.rollback()
            
            return {
                "error": str(e),
                "meeting_id": meeting_id
            }


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
                current_stage="summarization",
                progress=10,
                started_at=datetime.now(timezone.utc)
            )
            db.add(processing)
            await db.commit()
        else:
            processing.status = "processing"
            processing.current_stage = "summarization"
            processing.progress = 10
            processing.started_at = datetime.now(timezone.utc)
            processing.error_message = None
            await db.commit()

        try:
            transcript_text = meeting.subtitle

            # Форматирование
            processing.current_stage = "transcription_formatting"
            processing.progress = 20
            await db.commit()
            
            formatted_transcript = await ai_service.format_transcript(transcript_text)

            # Сохраняем транскрипт из subtitle (отформатированный)
            transcript_obj = Transcript(
                meeting_id=meeting_id,
                content=formatted_transcript,
                timestamps=None
            )
            db.add(transcript_obj)
            await db.commit()

            processing.progress = 30
            await db.commit()

            # Суммаризация
            processing.current_stage = "summarization"
            processing.progress = 40
            await db.commit()

            logger.info(f"Starting summarization from subtitle for meeting {meeting_id}...")
            summary_text = await ai_service.summarize_transcript(transcript_text, meeting.title)

            if not summary_text:
                raise Exception("Summarization failed")

            summary_obj = Summary(
                meeting_id=meeting_id,
                content=summary_text
            )
            db.add(summary_obj)
            await db.commit()

            processing.progress = 70
            await db.commit()

            # Action items
            processing.current_stage = "action_items"
            processing.progress = 80
            await db.commit()

            action_items = await ai_service.extract_action_items(transcript_text)
            if action_items:
                from src.meetings.models import ActionItem
                if isinstance(action_items, list):
                    for item in action_items:
                        if isinstance(item, dict):
                            action_item = ActionItem(
                                meeting_id=meeting_id,
                                title=item.get('title', 'Untitled'),
                                description=item.get('description'),
                                status='pending'
                            )
                            db.add(action_item)
                    await db.commit()

            # PDF
            processing.current_stage = "pdf_generation"
            processing.progress = 90
            await db.commit()

            logger.info(f"Starting PDF generation for meeting {meeting_id}...")

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
            pdf_buffer.seek(0)
            pdf_file_obj = io.BytesIO(pdf_buffer.read())
            pdf_s3_path = storage.upload_file(pdf_file_obj, pdf_path, content_type="application/pdf")

            if pdf_s3_path:
                meeting.pdf_file_path = pdf_s3_path
                await db.commit()
                logger.info(f"PDF uploaded to S3: {pdf_s3_path}")
            else:
                logger.error(f"Failed to upload PDF to S3 for meeting {meeting_id}")

            processing.status = "completed"
            processing.current_stage = "completed"
            processing.progress = 100
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(f"Meeting {meeting_id} subtitle processing completed successfully")
            return {
                "success": True,
                "meeting_id": meeting_id,
                "transcript_length": len(transcript_text),
                "action_items_count": len(action_items) if action_items else 0
            }

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
    pass


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

