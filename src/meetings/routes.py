from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from src.db.deps import get_db
from src.users.models import User
from src.core.permissions import get_current_user
from src.meetings import schemas, services, selectors
from src.projects import selectors as project_selectors
from src.core.queue import enqueue_meeting_processing


router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.post("/", response_model=schemas.MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    title: str = Form(...),
    project_id: Optional[int] = Form(None),
    meeting_date: Optional[datetime] = Form(None),
    comments: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создать новую встречу с опциональной загрузкой аудио"""
    # Проверить доступ к проекту если указан
    if project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
    
    data = schemas.MeetingCreate(
        title=title,
        project_id=project_id,
        meeting_date=meeting_date,
        comments=comments
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
    
    return meeting


@router.get("/", response_model=List[schemas.MeetingListOut])
async def get_meetings(
    project_id: Optional[int] = Query(None),
    organizer_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    min_duration: Optional[int] = Query(None, ge=0, description="Минимальная длительность в минутах"),
    max_duration: Optional[int] = Query(None, ge=0, description="Максимальная длительность в минутах"),
    sort_by: str = Query("date_desc", regex="^(date_asc|date_desc|duration_asc|duration_desc)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список встреч с фильтрацией и сортировкой.
    
    Фильтрация по:
    - organizer_id: ID организатора встречи
    - start_date: начало периода (ISO 8601 формат)
    - end_date: конец периода (ISO 8601 формат)
    - min_duration / max_duration: диапазон длительности в минутах
    
    Сортировка:
    - date_desc: новые → старые (по умолчанию)
    - date_asc: старые → новые
    - duration_asc: от коротких → к длинным
    - duration_desc: от длинных → к коротким
    """
    if project_id:
        # Проверить доступ
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        meetings = await selectors.get_project_meetings_with_filters(
            db, 
            project_id,
            organizer_id=organizer_id,
            start_date=start_date,
            end_date=end_date,
            min_duration=min_duration,
            max_duration=max_duration,
            sort_by=sort_by,
            skip=skip,
            limit=limit
        )
    else:
        meetings = await selectors.get_meetings_with_filters(
            db,
            current_user.id,
            project_id=project_id,
            organizer_id=organizer_id,
            start_date=start_date,
            end_date=end_date,
            min_duration=min_duration,
            max_duration=max_duration,
            sort_by=sort_by,
            skip=skip,
            limit=limit
        )
    
    return meetings


@router.get("/uncategorized", response_model=List[schemas.MeetingListOut])
async def get_uncategorized_meetings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить некатегорированные встречи"""
    meetings = await selectors.get_uncategorized_meetings(
        db, current_user.id, skip, limit
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
            db, current_user.id, project_id
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
    
    meetings = await selectors.search_meetings(
        db, q, project_id, current_user.id, skip, limit
    )
    return meetings


@router.get("/{meeting_id}", response_model=schemas.MeetingDetailsOut)
async def get_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить детали встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Проверить доступ
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, meeting.project_id
        )
        if not has_access and meeting.organizer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this meeting"
            )
    elif meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this meeting"
        )
    
    # Получить связанные данные
    transcript = await selectors.get_meeting_transcript(db, meeting_id)
    summary = await selectors.get_meeting_summary(db, meeting_id)
    notes = await selectors.get_meeting_notes(db, meeting_id)
    action_items = await selectors.get_meeting_action_items(db, meeting_id)
    
    return schemas.MeetingDetailsOut(
        meeting=meeting,
        transcript=transcript,
        summary=summary,
        notes=notes,
        action_items=action_items
    )


@router.put("/{meeting_id}", response_model=schemas.MeetingOut)
async def update_meeting(
    meeting_id: int,
    data: schemas.MeetingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновить встречу"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Только организатор может изменять
    if meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organizer can update meeting"
        )
    
    updated_meeting = await services.update_meeting(db, meeting_id, data)
    return updated_meeting


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить встречу"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    if meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organizer can delete meeting"
        )
    
    await services.delete_meeting(db, meeting_id)


@router.post("/{meeting_id}/move", response_model=schemas.MeetingOut)
async def move_meeting(
    meeting_id: int,
    project_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Переместить встречу в другой проект"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    if meeting.organizer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organizer can move meeting"
        )
    
    # Проверить доступ к новому проекту
    if project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, project_id
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить временную ссылку для скачивания аудио"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Проверить доступ
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, meeting.project_id
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
    
    url = await services.get_audio_download_url(db, meeting_id)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found"
        )
    
    return {"url": url, "expires_in": 3600}


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
            db, current_user.id, meeting.project_id
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
            db, current_user.id, meeting.project_id
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
            db, current_user.id, meeting.project_id
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
    """Получить статус обработки встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    processing = await selectors.get_meeting_processing(db, meeting_id)
    if not processing:
        return {
            "status": "not_started",
            "message": "Processing has not been started"
        }
    
    return {
        "status": processing.status,
        "current_stage": processing.current_stage,
        "progress": processing.progress,
        "error_message": processing.error_message,
        "started_at": processing.started_at,
        "completed_at": processing.completed_at
    }

