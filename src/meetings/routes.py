from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import logging

from src.db.deps import get_db
from src.users.models import User
from src.core.permissions import get_current_user
from src.meetings import schemas, services, selectors, dependencies as meeting_deps
from src.projects import selectors as project_selectors
from src.core.queue import enqueue_meeting_processing, enqueue_meeting_processing_from_subtitle


router = APIRouter(prefix="/meetings", tags=["meetings"])
logger = logging.getLogger(__name__)


@router.post("/", response_model=schemas.MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    title: str = Form(...),
    subtitle: Optional[str] = Form(None, description="Транскрипт из Google Meet (для саммаризации)"),
    project_id: Optional[int] = Form(None),
    meeting_date: Optional[datetime] = Form(None),
    comments: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    duration: Optional[int] = Form(None, description="Длительность в секундах"),
    importance: str = Form("low", regex="^(low|middle|high)$", description="Важность встречи: low, middle, high"),
    audio_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создать новую встречу с опциональной загрузкой аудио
    
    При загрузке аудиофайла автоматически запускается обработка:
    - Транскрибация аудио
    - Суммаризация транскрипта
    - Извлечение action items
    """
    # Проверить доступ к проекту если указан
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
    
    audio_content = None
    audio_filename = None
    
    if audio_file:
        audio_content = await audio_file.read()
        audio_filename = audio_file.filename
        # Преобразовать в file-like object
        import io
        audio_content = io.BytesIO(audio_content)
    
    meeting = await services.create_meeting(
        db, data, current_user.id, audio_content, audio_filename
    )
    
    # Автоматически запустить обработку если загружено аудио
    if audio_file:
        job_id = await enqueue_meeting_processing(meeting.id)
        logger.info(f"Meeting {meeting.id} processing started automatically after file upload, job_id={job_id}")
    # Если аудио нет, но есть subtitle — запускаем саммаризацию из готового транскрипта
    elif data.subtitle:
        job_id = await enqueue_meeting_processing_from_subtitle(meeting.id)
        logger.info(f"Meeting {meeting.id} subtitle processing started, job_id={job_id}")

    return meeting


@router.get("/my", response_model=dict)
async def get_my_meetings(
    q: Optional[str] = Query(None, min_length=1, description="Поиск по названию встречи"),
    start_date: Optional[datetime] = Query(None, description="Начало периода (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Конец периода (ISO 8601)"),
    duration_from: Optional[int] = Query(None, ge=0, description="Минимальная длительность в секундах (или null если нет нижней границы)"),
    duration_to: Optional[int] = Query(None, ge=0, description="Максимальная длительность в секундах (или null если нет верхней границы)"),
    sort_date: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по дате"),
    sort_duration: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по длительности"),
    sort_importance: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по важности"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить встречи **только текущего пользователя** (где он является организатором).

    Не включает встречи других участников проектов — только те, что создал сам пользователь.

    Фильтрация:
    - q: поиск по названию
    - start_date / end_date: диапазон дат (ISO 8601)
    - duration_from / duration_to: диапазон длительности в секундах (null если нет границы)

    Сортировка (можно комбинировать):
    - sort_date=asc|desc
    - sort_duration=asc|desc
    - sort_importance=asc|desc

    Ответ:
    {
        "count": 10,
        "next": "...",
        "previous": null,
        "results": [...]
    }
    """
    sort_fields = []
    if sort_importance:
        sort_fields.append(f"importance_{sort_importance}")
    if sort_date:
        sort_fields.append(f"date_{sort_date}")
    if sort_duration:
        sort_fields.append(f"duration_{sort_duration}")
    sort_by = ",".join(sort_fields) if sort_fields else "date_desc"

    meetings, total = await selectors.get_meetings_with_filters(
        db,
        current_user.id,
        current_user.role,
        search_query=q,
        organizer_id=current_user.id,   # ← только мои встречи
        start_date=start_date,
        end_date=end_date,
        duration_from=duration_from,
        duration_to=duration_to,
        sort_by=sort_by,
        skip=skip,
        limit=limit,
        return_count=True
    )

    base_url = "http://localhost:8000/api/meetings/my"
    next_url = f"{base_url}?skip={skip + limit}&limit={limit}" if skip + limit < total else None
    previous_url = f"{base_url}?skip={max(0, skip - limit)}&limit={limit}" if skip > 0 else None

    results = [schemas.MeetingListOutWithOrganizer.model_validate(m) for m in meetings]
    return {"count": total, "next": next_url, "previous": previous_url, "results": results}


@router.get("/", response_model=dict)
async def get_meetings(
        q: Optional[str] = Query(None, min_length=1, description="Поиск по названию встречи"),
        project_id: Optional[int] = Query(None),
        organizer_id: Optional[int] = Query(None),
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        duration_from: Optional[int] = Query(None, ge=0,
                                              description="Минимальная длительность в секундах (или null если нет нижней границы)"),
        duration_to: Optional[int] = Query(None, ge=0,
                                              description="Максимальная длительность в секундах (или null если нет верхней границы)"),
        sort_date: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по дате"),
        sort_duration: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по длительности"),
        sort_importance: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по важности"),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """
    Получить список встреч с фильтрацией и сортировкой.

    Фильтрация по:
    - q: поиск по названию встречи
    - project_id: ID проекта
    - organizer_id: ID организатора встречи
    - start_date: начало периода (ISO 8601 формат)
    - end_date: конец периода (ISO 8601 формат)
    - duration_from / duration_to: диапазон длительности в секундах (null если нет границы)

    Сортировка (несколько полей одновременно):
    - sort_date=asc|desc: сортировка по дате
    - sort_duration=asc|desc: сортировка по длительности
    - sort_importance=asc|desc: сортировка по важности (low->high или high->low)
    - Можно использовать оба параметра одновременно: ?sort_importance=desc&sort_date=desc

    Ответ в формате DRF (Django REST Framework):
    {
        "count": 100,
        "next": "http://localhost:8000/api/meetings/?skip=50&limit=50",
        "previous": "http://localhost:8000/api/meetings/?skip=0&limit=50",
        "results": [...]
    }
    """
    # Построить sort_by из отдельных параметров
    sort_fields = []
    if sort_importance:
        sort_fields.append(f"importance_{sort_importance}")
    if sort_date:
        sort_fields.append(f"date_{sort_date}")
    if sort_duration:
        sort_fields.append(f"duration_{sort_duration}")

    sort_by = ",".join(sort_fields) if sort_fields else "date_desc"

    if project_id:
        # Проверить доступ
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

    # Формируем URLs для next/previous
    base_url = "http://localhost:8000/api/meetings/"
    next_url = None
    previous_url = None

    if skip + limit < total:
        next_skip = skip + limit
        next_url = f"{base_url}?skip={next_skip}&limit={limit}"

    if skip > 0:
        previous_skip = max(0, skip - limit)
        previous_url = f"{base_url}?skip={previous_skip}&limit={limit}"

    # Преобразуем Meeting объекты в Pydantic models с информацией об организаторе
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
    """Получить статус обработки активного (в процессе) митинга без указания ID
    
    Возвращает встречу, которая в данный момент обрабатывается (статус 'processing').
    Если активной обработки нет, возвращает not_started.
    
    Автоматически очищает статусы, которые активны более 20 минут (предполагается, что процесс оборвался).
    
    Ответ:
    {
      "meeting_id": 1,
      "meeting": { полные данные встречи },
      "status": "processing",
      "current_stage": "transcription",
      "progress": 35,
      "error_message": null,
      "started_at": "2025-10-27T12:00:00Z",
      "completed_at": null,
      "estimated_completion": "2025-10-27T12:05:00Z",
      "stage_info": "Транскрибация аудио"
    }
    """
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
    
    # Вычисляем приблизительное время завершения
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
    """Получить полные детали активного (в процессе) митинга без указания ID
    
    Возвращает полную информацию о встречей в процессе (включая транскрипт, резюме, заметки и задачи).
    
    Ответ:
    {
      "meeting": { полные данные встречи },
      "transcript": { текст и временные метки },
      "summary": { резюме },
      "notes": [ список заметок ],
      "action_items": [ список задач ],
      "processing": { информация об обработке }
    }
    """
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
    
    # Проверить доступ
    if meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this meeting"
        )
    
    # Получить связанные данные
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
    # Получить связанные данные
    transcript = await selectors.get_meeting_transcript(db, meeting_id)
    summary = await selectors.get_meeting_summary(db, meeting_id)
    action_items = await selectors.get_meeting_action_items(db, meeting_id)
    
    # Создать объект MeetingOut для получения PDF URL
    meeting_out = schemas.MeetingOut.model_validate(meeting)
    
    return schemas.MeetingDetailsOut(
        meeting=meeting_out,
        transcript=schemas.TranscriptOut.model_validate(transcript) if transcript else None,
        summary=schemas.SummaryOut.model_validate(summary) if summary else None,
        subtitle=meeting.subtitle,
        notes=meeting.notes,
        action_items=[schemas.ActionItemOut.model_validate(item) for item in action_items],
        pdf=meeting_out.pdf_file_path  # URL уже сериализован через field_serializer
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
    # Проверить доступ к новому проекту
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
    
    # Получить обе ссылки
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


# Notes endpoints
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
    
    # Проверить доступ
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    notes = await selectors.get_meeting_notes(db, meeting_id)
    return notes


# Action Items endpoints
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Проверить доступ
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Проверить доступ
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    if not meeting.audio_file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting has no audio file"
        )
    
    # Добавить в очередь
    job_id = await enqueue_meeting_processing(meeting_id)
    
    return {
        "message": "Processing started",
        "job_id": job_id,
        "meeting_id": meeting_id
    }


@router.get("/{meeting_id}/processing-status")
async def get_processing_status(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить статус обработки встречи
    
    Возвращает:
    - status: "not_started", "processing", "completed", "failed"
    - current_stage: "transcription", "summarization", "action_items"
    - progress: 0-100 (процент выполнения)
    - error_message: текст ошибки (если есть)
    - started_at: время начала обработки
    - completed_at: время завершения
    - estimated_completion: приблизительное время завершения
    
    Пример:
    GET /api/meetings/1/processing-status
    
    Ответ:
    {
      "meeting_id": 1,
      "meeting": { полные данные встречи },
      "status": "processing",
      "current_stage": "transcription",
      "progress": 35,
      "error_message": null,
      "started_at": "2025-10-27T12:00:00Z",
      "completed_at": null,
      "estimated_completion": "2025-10-27T12:05:00Z",
      "stage_info": "Транскрибация аудио"
    }
    """
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
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
    
    # Проверяем, не застрял ли статус обработки более 20 минут
    if processing.status == "processing" and processing.started_at:
        from datetime import datetime, timezone
        elapsed_minutes = (datetime.now(timezone.utc) - processing.started_at).total_seconds() / 60
        
        if elapsed_minutes > 20:
            # Автоматически очищаем застрявший статус
            processing.status = "failed"
            processing.error_message = f"Обработка прервана: процесс не отвечал более 20 минут"
            processing.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(processing)
    
    # Вычисляем приблизительное время завершения
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
    """Получить информацию о длительности встречи
    
    Возвращает:
    - duration: Длительность в секундах (может быть None если не установлена)
    - duration_formatted: Длительность в формате ЧЧ:ММ:СС
    - duration_minutes: Длительность в минутах (округлено)
    - audio_file_size: Размер аудио файла в байтах
    - source: Источник информации ("manual", "transcription", "unknown")
    
    Пример:
    GET /api/meetings/1/duration
    
    Ответ:
    {
      "meeting_id": 1,
      "duration": 2700,
      "duration_formatted": "00:45:00",
      "duration_minutes": 45,
      "audio_file_size": 3456789,
      "source": "transcription"
    }
    """
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Проверяем доступ
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this meeting"
            )
    elif meeting.organizer_id != current_user.id:
        # Если встреча не в проекте, может быть доступна всем аутентифицированным пользователям
        pass
    
    # Определяем источник информации о длительности
    source = "unknown"
    processing = await selectors.get_meeting_processing(db, meeting_id)
    if meeting.duration:
        # Если есть транскрипт, длительность из него
        transcript = await selectors.get_meeting_transcript(db, meeting_id)
        if transcript:
            source = "transcription"
        else:
            source = "manual"
    
    duration_formatted = None
    duration_minutes = None
    if meeting.duration:
        # Форматируем в ЧЧ:ММ:СС
        hours = meeting.duration // 3600
        minutes = (meeting.duration % 3600) // 60
        seconds = meeting.duration % 60
        duration_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        # Округляем до минут
        duration_minutes = round(meeting.duration / 60)
    
    return {
        "meeting_id": meeting_id,
        "duration": meeting.duration,  # В секундах
        "duration_formatted": duration_formatted,
        "duration_minutes": duration_minutes,
        "audio_file_size": meeting.audio_file_size,
        "source": source,
        "processing_status": processing.status if processing else "not_started"
    }


@router.put("/{meeting_id}/duration")
async def update_meeting_duration(
    meeting_id: int,
    duration_seconds: int = Query(..., ge=1, description="Длительность встречи в секундах (минимум 1 секунда)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновить длительность встречи вручную
    
    Параметры:
    - duration_seconds: Длительность в секундах (целое число, минимум 1)
    
    Пример:
    PUT /api/meetings/1/duration?duration_seconds=2700
    
    Ответ:
    {
      "meeting_id": 1,
      "duration": 2700,
      "duration_formatted": "00:45:00",
      "duration_minutes": 45,
      "message": "Duration updated successfully"
    }
    """
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Только организатор, Admin или Manager владелец проекта может обновлять длительность
    if meeting.organizer_id == current_user.id:
        pass  # Организатор может обновлять
    elif current_user.role == "Admin":
        pass  # Admin может обновлять все встречи
    elif meeting.project_id and current_user.role == "Manager":
        # Manager может обновлять встречи своих проектов
        can_edit = await project_selectors.check_user_can_edit_project(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if not can_edit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organizer, Admin or Manager project owner can update meeting duration"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organizer, Admin or Manager project owner can update meeting duration"
        )
    
    # Обновляем длительность
    old_duration = meeting.duration
    meeting.duration = duration_seconds
    await db.commit()
    await db.refresh(meeting)
    
    # Форматируем новую длительность
    hours = meeting.duration // 3600
    minutes = (meeting.duration % 3600) // 60
    secs = meeting.duration % 60
    duration_formatted = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    duration_minutes = round(meeting.duration / 60)
    
    # Форматируем старую длительность если была
    old_duration_formatted = None
    if old_duration:
        old_hours = old_duration // 3600
        old_minutes = (old_duration % 3600) // 60
        old_secs = old_duration % 60
        old_duration_formatted = f"{old_hours:02d}:{old_minutes:02d}:{old_secs:02d}"
    
    return {
        "meeting_id": meeting_id,
        "duration": meeting.duration,  # В секундах
        "duration_formatted": duration_formatted,
        "duration_minutes": duration_minutes,
        "previous_duration": old_duration,
        "previous_duration_formatted": old_duration_formatted,
        "message": f"Duration updated successfully from {old_duration_formatted or old_duration} to {duration_formatted}"
    }

