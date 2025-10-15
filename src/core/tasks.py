from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import io

from src.db.session import AsyncSessionLocal
from src.meetings.models import Meeting, MeetingProcessing, Transcript, Summary
from src.core.storage import storage
from src.core.ai_services import ai_service
from src.meetings import selectors
from arq.connections import RedisSettings
from src.core.config import settings


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
            transcript_text = transcript_data.get('text', '')
            transcript_obj = Transcript(
                meeting_id=meeting_id,
                content=transcript_text,
                timestamps=transcript_data
            )
            db.add(transcript_obj)
            await db.commit()
            
            # Обновить длительность встречи если её не было
            if not meeting.duration and transcript_data.get('duration'):
                meeting.duration = int(transcript_data.get('duration'))
                await db.commit()
            
            # Шаг 2: Суммаризация
            processing.current_stage = "summarization"
            processing.progress = 60
            await db.commit()
            
            summary_text = await ai_service.summarize_transcript(
                transcript_text,
                meeting.title
            )
            
            if not summary_text:
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
                for item in action_items:
                    action_item = ActionItem(
                        meeting_id=meeting_id,
                        title=item.get('title', 'Untitled'),
                        description=item.get('description'),
                        status='pending'
                    )
                    db.add(action_item)
                await db.commit()
            
            # Завершить обработку
            processing.status = "completed"
            processing.current_stage = "completed"
            processing.progress = 100
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            return {
                "success": True,
                "meeting_id": meeting_id,
                "transcript_length": len(transcript_text),
                "action_items_count": len(action_items) if action_items else 0
            }
            
        except Exception as e:
            # Обработка ошибок
            processing.status = "failed"
            processing.error_message = str(e)
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
            return {
                "error": str(e),
                "meeting_id": meeting_id
            }


async def startup(ctx):
    """Инициализация при запуске воркера"""
    pass


async def shutdown(ctx):
    """Очистка при остановке воркера"""
    pass


# Конфигурация ARQ воркера
class WorkerSettings:
    functions = [process_meeting]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

