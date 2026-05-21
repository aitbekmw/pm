from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import logging
from sqlalchemy import select

from src.db.deps import get_db
from src.users.models import User
from src.core.permissions import get_current_user
from src.meetings import schemas, services, selectors, dependencies as meeting_deps
from src.projects import selectors as project_selectors
from src.core.queue import enqueue_meeting_processing, enqueue_meeting_processing_from_subtitle

from src.core.telegram import send_telegram_message
from src.projects.models import Project

router = APIRouter(prefix="/meetings", tags=["meetings"])
logger = logging.getLogger(__name__)


@router.post("/", response_model=schemas.MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
        title: str = Form(...),
        subtitle: Optional[str] = Form(None, description="Транскрипт из Google Meet"),
        project_id: Optional[int] = Form(None),
        meeting_date: Optional[datetime] = Form(None),
        comments: Optional[str] = Form(None),
        notes: Optional[str] = Form(None),
        duration: Optional[int] = Form(None, description="Длительность в секундах"),
        importance: str = Form("low", regex="^(low|middle|high)$", description="low, middle, high"),
        audio_file: Optional[UploadFile] = File(None),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Создание встречи с проверкой прав доступа текущего пользователя"""

    if project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

    data = schemas.MeetingCreate(
        title=title,
        subtitle=subtitle,
        project_id=project_id,
        meeting_date=meeting_date,
        comments=comments,
        notes=notes,
        duration=duration,
        importance=importance
    )

    meeting = await services.create_meeting(db, data, current_user.id, audio_file)

    if audio_file:
        await enqueue_meeting_processing(meeting.id)
    elif data.subtitle:
        await enqueue_meeting_processing_from_subtitle(meeting.id)

    if project_id:
        project_result = await db.execute(select(Project).where(Project.id == project_id))
        project = project_result.scalars().first()

        if project and project.telegram_chat_id:
            importance_mapping = {"high": "🔴 Высокий", "middle": "🟡 Средний", "low": "🟢 Низкий"}
            importance_text = importance_mapping.get(importance, "🟢 Низкий")
            date_str = meeting_date.strftime("%d.%m.%Y %H:%M") if meeting_date else "Не указана"

            message_text = (
                f"📅 <b>Загружена встреча:</b> {title}\n"
                f"❗ <b>Уровень важности:</b> {importance_text}\n\n"
                f"📁 <b>Проект:</b> {project.name}\n"
                f"🕐 <b>Время проведения:</b> {date_str}"
            )
            try:
                await send_telegram_message(chat_id=project.telegram_chat_id, text=message_text)
            except Exception as e:
                logger.error(f"TG Error: {e}")

    return meeting


@router.get("/my", response_model=dict)
async def get_my_meetings(
        q: Optional[str] = Query(None),
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        duration_from: Optional[int] = Query(None),
        duration_to: Optional[int] = Query(None),
        sort_date: Optional[str] = Query(None),
        sort_duration: Optional[str] = Query(None),
        sort_importance: Optional[str] = Query(None),
        skip: int = Query(0),
        limit: int = Query(50),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    sort_fields = []
    if sort_importance: sort_fields.append(f"importance_{sort_importance}")
    if sort_date: sort_fields.append(f"date_{sort_date}")
    if sort_duration: sort_fields.append(f"duration_{sort_duration}")
    sort_by = ",".join(sort_fields) if sort_fields else "date_desc"

    meetings, total = await selectors.get_meetings_with_filters(
        db, current_user.id, current_user.role, search_query=q,
        organizer_id=current_user.id, start_date=start_date, end_date=end_date,
        duration_from=duration_from, duration_to=duration_to, sort_by=sort_by,
        skip=skip, limit=limit, return_count=True
    )
    return {"count": total, "results": [schemas.MeetingListOutWithOrganizer.model_validate(m) for m in meetings]}





@router.get("/", response_model=dict)
async def get_meetings(
        q: Optional[str] = Query(None, min_length=1, description="Поиск по названию встречи"),
        project_id: Optional[int] = Query(None),
        organizer_id: Optional[int] = Query(None),
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        duration_from: Optional[int] = Query(None, ge=0, description="Минимальная длительность в секундах"),
        duration_to: Optional[int] = Query(None, ge=0, description="Максимальная длительность в секундах"),
        sort_date: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по дате"),
        sort_duration: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по длительности"),
        sort_importance: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по важности"),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить список встреч с фильтрацией и сортировкой."""
    sort_fields = []
    if sort_importance:
        sort_fields.append(f"importance_{sort_importance}")
    if sort_date:
        sort_fields.append(f"date_{sort_date}")
    if sort_duration:
        sort_fields.append(f"duration_{sort_duration}")

    sort_by = ",".join(sort_fields) if sort_fields else "date_desc"

    if project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        meetings, total = await selectors.get_project_meetings_with_filters(
            db,
            project_id,
            search_query=q,
            organizer_id=organizer_id,
            start_date=start_date,
            end_date=end_date,
            duration_from=duration_from,
            duration_to=duration_to,
            sort_by=sort_by,
            skip=skip,
            limit=limit,
            return_count=True
        )
    else:
        meetings, total = await selectors.get_meetings_with_filters(
            db,
            current_user.id,
            current_user.role,
            search_query=q,
            project_id=project_id,
            organizer_id=organizer_id,
            start_date=start_date,
            end_date=end_date,
            duration_from=duration_from,
            duration_to=duration_to,
            sort_by=sort_by,
            skip=skip,
            limit=limit,
            return_count=True
        )

    base_url = "http://localhost:8000/api/meetings/"
    next_url = f"{base_url}?skip={skip + limit}&limit={limit}" if skip + limit < total else None
    previous_url = f"{base_url}?skip={max(0, skip - limit)}&limit={limit}" if skip > 0 else None

    results = [schemas.MeetingListOutWithOrganizer.model_validate(meeting) for meeting in meetings]

    return {
        "count": total,
        "next": next_url,
        "previous": previous_url,
        "results": results
    }


@router.get("/uncategorized", response_model=List[schemas.MeetingListOutWithOrganizer])
async def get_uncategorized_meetings(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить некатегорированные встречи"""
    meetings = await selectors.get_uncategorized_meetings(
        db, current_user.id, current_user.role, skip, limit
    )
    return meetings


@router.get("/search", response_model=List[schemas.MeetingListOut])
async def search_meetings(
        q: str = Query(..., min_length=1),
        project_id: Optional[int] = Query(None),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Поиск встреч по названию"""
    if project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

    meetings = await selectors.search_meetings(
        db, q, project_id, current_user.id, current_user.role, skip, limit
    )
    return meetings


@router.get("/processing/status/active")
async def get_active_processing_status(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить статус обработки активного (в процессе) митинга без указания ID"""
    from datetime import datetime, timezone, timedelta

    processing = await selectors.get_active_processing_meeting(db, current_user.id)

    if not processing:
        return {
            "meeting_id": None,
            "meeting": None,
            "status": "not_started",
            "current_stage": None,
            "progress": 0,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "estimated_completion": None,
            "stage_info": None
        }

    meeting = await selectors.get_meeting_by_id(db, processing.meeting_id)

    estimated_completion = None
    if processing.status == "processing" and processing.started_at and processing.progress > 0:
        elapsed = (datetime.now(timezone.utc) - processing.started_at).total_seconds()
        if processing.progress > 0:
            total_estimated = (elapsed / processing.progress) * 100
            remaining = total_estimated - elapsed
            estimated_completion = datetime.now(timezone.utc) + timedelta(seconds=remaining)

    return {
        "meeting_id": processing.meeting_id,
        "meeting": schemas.MeetingOut.model_validate(meeting) if meeting else None,
        "status": processing.status,
        "current_stage": processing.current_stage,
        "progress": processing.progress or 0,
        "error_message": processing.error_message,
        "started_at": processing.started_at,
        "completed_at": processing.completed_at,
        "estimated_completion": estimated_completion,
        "stage_info": {
            "transcription": "Транскрибация аудио",
            "summarization": "Создание резюме встречи",
            "action_items": "Извлечение задач",
            "pdf_generation": "Генерация PDF документа"
        }.get(processing.current_stage, None)
    }


@router.get("/active/details")
async def get_active_meeting_details(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить полные детали активного (в процессе) митинга без указания ID"""
    processing = await selectors.get_active_processing_meeting(db, current_user.id)

    if not processing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Нет активной обработки"
        )

    meeting = await selectors.get_meeting_by_id(db, processing.meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )

    if meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this meeting"
        )

    transcript = await selectors.get_meeting_transcript(db, processing.meeting_id)
    summary = await selectors.get_meeting_summary(db, processing.meeting_id)
    notes = await selectors.get_meeting_notes(db, processing.meeting_id)
    action_items = await selectors.get_meeting_action_items(db, processing.meeting_id)

    return {
        "meeting": schemas.MeetingOut.model_validate(meeting),
        "transcript": schemas.TranscriptOut.model_validate(transcript) if transcript else None,
        "summary": schemas.SummaryOut.model_validate(summary) if summary else None,
        "notes": [schemas.NoteOut.model_validate(note) for note in notes],
        "action_items": [schemas.ActionItemOut.model_validate(item) for item in action_items],
        "processing": {
            "status": processing.status,
            "current_stage": processing.current_stage,
            "progress": processing.progress or 0,
            "error_message": processing.error_message,
            "started_at": processing.started_at,
            "completed_at": processing.completed_at
        }
    }


@router.get("/{meeting_id}", response_model=schemas.MeetingDetailsOut)
async def get_meeting(
        meeting: selectors.Meeting = Depends(meeting_deps.get_meeting_with_read_access),
        db: AsyncSession = Depends(get_db)
):
    """Получить детали встречи"""
    meeting_id = meeting.id
    transcript = await selectors.get_meeting_transcript(db, meeting_id)
    summary = await selectors.get_meeting_summary(db, meeting_id)
    action_items = await selectors.get_meeting_action_items(db, meeting_id)

    meeting_out = schemas.MeetingOut.model_validate(meeting)

    return schemas.MeetingDetailsOut(
        meeting=meeting_out,
        transcript=schemas.TranscriptOut.model_validate(transcript) if transcript else None,
        summary=schemas.SummaryOut.model_validate(summary) if summary else None,
        subtitle=meeting.subtitle,
        notes=meeting.notes,
        action_items=[schemas.ActionItemOut.model_validate(item) for item in action_items],
        pdf=meeting_out.pdf_file_path
    )


@router.put("/{meeting_id}", response_model=schemas.MeetingOut)
async def update_meeting(
        meeting_id: int,
        data: schemas.MeetingUpdate,
        meeting: selectors.Meeting = Depends(meeting_deps.get_meeting_with_edit_access),
        db: AsyncSession = Depends(get_db)
):
    """Обновить встречу"""
    updated_meeting = await services.update_meeting(db, meeting_id, data)
    return updated_meeting


@router.put("/{meeting_id}/transcript", response_model=schemas.TranscriptOut)
async def update_meeting_transcript(
        meeting_id: int,
        data: schemas.TranscriptUpdate,
        meeting: selectors.Meeting = Depends(meeting_deps.get_meeting_with_edit_access),
        db: AsyncSession = Depends(get_db)
):
    """Обновить транскрипт встречи"""
    transcript = await services.update_transcript(db, meeting_id, data.content)
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found for this meeting"
        )
    return transcript


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
        meeting: selectors.Meeting = Depends(meeting_deps.get_meeting_with_edit_access),
        db: AsyncSession = Depends(get_db)
):
    """Удалить встречу"""
    await services.delete_meeting(db, meeting.id)


@router.post("/{meeting_id}/move", response_model=schemas.MeetingOut)
async def move_meeting(
        meeting_id: int,
        project_id: Optional[int] = None,
        meeting: selectors.Meeting = Depends(meeting_deps.get_meeting_with_edit_access),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Переместить встречу в другой проект"""
    if project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to target project"
            )

    updated_meeting = await services.move_meeting_to_project(db, meeting_id, project_id)
    return updated_meeting


@router.get("/{meeting_id}/audio-url")
async def get_audio_url(
        meeting_id: int,
        meeting: selectors.Meeting = Depends(meeting_deps.get_meeting_with_read_access),
        db: AsyncSession = Depends(get_db)
):
    """Получить временные ссылки для скачивания аудио"""
    url = await services.get_audio_download_url(db, meeting_id, as_attachment=False)
    download_url = await services.get_audio_download_url(db, meeting_id, as_attachment=True)

    if not url or not download_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found"
        )

    return {
        "url": url,
        "download_url": download_url,
        "expires_in": 3600
    }


@router.post("/{meeting_id}/notes", response_model=schemas.NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
        meeting_id: int,
        data: schemas.NoteCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Создать заметку для встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )

    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    note = await services.create_note(db, meeting_id, data.content, current_user.id)
    return note


@router.get("/{meeting_id}/notes", response_model=List[schemas.NoteOut])
async def get_notes(
        meeting_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить все заметки встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    notes = await selectors.get_meeting_notes(db, meeting_id)
    return notes


@router.post("/{meeting_id}/action-items", response_model=schemas.ActionItemOut, status_code=status.HTTP_201_CREATED)
async def create_action_item(
        meeting_id: int,
        data: schemas.ActionItemCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Создать action item для встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    action_item = await services.create_action_item(
        db, meeting_id, data.title, data.description, data.assignee_id, data.due_date
    )
    return action_item


@router.get("/{meeting_id}/action-items", response_model=List[schemas.ActionItemOut])
async def get_action_items(
        meeting_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить все action items встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    action_items = await selectors.get_meeting_action_items(db, meeting_id)
    return action_items


@router.post("/{meeting_id}/process")
async def start_meeting_processing(
        meeting_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Запустить обработку встречи (транскрибация + суммаризация)"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not meeting.audio_file_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting has no audio file")

    job_id = await enqueue_meeting_processing(meeting_id)
    return {"message": "Processing started", "job_id": job_id, "meeting_id": meeting_id}


@router.get("/{meeting_id}/processing-status")
async def get_processing_status(
        meeting_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить статус обработки встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    processing = await selectors.get_meeting_processing(db, meeting_id)
    if not processing:
        return {
            "meeting_id": meeting_id,
            "meeting": schemas.MeetingOut.model_validate(meeting) if meeting else None,
            "status": "not_started",
            "current_stage": None,
            "progress": 0,
            "error_message": None,
            "started_at": None,
            "completed_at": None,
            "estimated_completion": None,
            "stage_info": None
        }

    if processing.status == "processing" and processing.started_at:
        from datetime import datetime, timezone
        elapsed_minutes = (datetime.now(timezone.utc) - processing.started_at).total_seconds() / 60

        if elapsed_minutes > 20:
            processing.status = "failed"
            processing.error_message = f"Обработка прервана: процесс не отвечал более 20 минут"
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(processing)

    estimated_completion = None
    if processing.status == "processing" and processing.started_at and processing.progress > 0:
        from datetime import datetime, timezone, timedelta
        elapsed = (datetime.now(timezone.utc) - processing.started_at).total_seconds()
        if processing.progress > 0:
            total_estimated = (elapsed / processing.progress) * 100
            remaining = total_estimated - elapsed
            estimated_completion = datetime.now(timezone.utc) + timedelta(seconds=remaining)

    return {
        "meeting_id": meeting_id,
        "meeting": schemas.MeetingOut.model_validate(meeting) if meeting else None,
        "status": processing.status,
        "current_stage": processing.current_stage,
        "progress": processing.progress or 0,
        "error_message": processing.error_message,
        "started_at": processing.started_at,
        "completed_at": processing.completed_at,
        "estimated_completion": estimated_completion,
        "stage_info": {
            "transcription": "Транскрибация аудио",
            "summarization": "Создание резюме встречи",
            "action_items": "Извлечение задач",
            "pdf_generation": "Генерация PDF документа"
        }.get(processing.current_stage, None)
    }


@router.get("/{meeting_id}/duration")
async def get_meeting_duration(
        meeting_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Получить информацию о длительности встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this meeting")

    return {"meeting_id": meeting_id, "duration": meeting.duration}