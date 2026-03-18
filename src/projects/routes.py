from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from src.db.deps import get_db
from src.users.models import User
from src.core.permissions import get_current_user, require_manager_or_admin
from src.projects import schemas, services, selectors
from src.meetings import schemas as meeting_schemas, selectors as meeting_selectors


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=schemas.ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: schemas.ProjectCreate,
    current_user: User = Depends(require_manager_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Создать новый проект (только Manager или Admin)"""
    project = await services.create_project(db, data, current_user.id)
    
    # Добавить счетчики
    members_count = await selectors.get_project_members_count(db, project.id)
    meetings_count = await selectors.get_project_meetings_count(db, project.id)
    
    project_out = schemas.ProjectOut.model_validate(project)
    project_out.members_count = members_count
    project_out.meetings_count = meetings_count
    
    return project_out


@router.get("/", response_model=List[schemas.ProjectListOut])
async def get_projects(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить список проектов пользователя"""
    projects = await selectors.get_user_projects(db, current_user.id, current_user.role, include_archived)
    
    result = []
    for project in projects:
        members_count = await selectors.get_project_members_count(db, project.id)
        meetings_count = await selectors.get_project_meetings_count(db, project.id)
        
        project_data = schemas.ProjectListOut.model_validate(project)
        project_data.members_count = members_count
        project_data.meetings_count = meetings_count
        result.append(project_data)
    
    return result


@router.get("/archived", response_model=List[schemas.ProjectListOut])
async def get_archived_projects(
    q: Optional[str] = Query(None, min_length=1, description="Поисковый запрос по названию проекта"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить список архивированных проектов
    
    Если указан параметр q, выполняется поиск по названию среди архивированных проектов.
    """
    if q:
        # Использовать поиск с включением архивов
        projects = await selectors.search_projects(
            db, q, current_user.id, current_user.role, include_archived=True
        )
        # Фильтруем только архивированные
        archived_projects = [p for p in projects if p.is_archived]
    else:
        # Получить все архивированные проекты
        projects = await selectors.get_user_projects(db, current_user.id, current_user.role, include_archived=True)
        archived_projects = [p for p in projects if p.is_archived]
    
    result = []
    for project in archived_projects:
        members_count = await selectors.get_project_members_count(db, project.id)
        meetings_count = await selectors.get_project_meetings_count(db, project.id)
        
        project_data = schemas.ProjectListOut.model_validate(project)
        project_data.members_count = members_count
        project_data.meetings_count = meetings_count
        result.append(project_data)
    
    return result


@router.get("/{project_id}/meetings", response_model=dict)
async def get_project_meetings(
    project_id: int,
    q: Optional[str] = Query(None, min_length=1, description="Поиск по названию встречи"),
    organizer_id: Optional[int] = Query(None, description="Фильтр по организатору встречи"),
    start_date: Optional[datetime] = Query(None, description="Начало периода (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="Конец периода (ISO 8601)"),
    min_duration: Optional[float] = Query(None, ge=0, description="Минимальная длительность в минутах"),
    max_duration: Optional[float] = Query(None, ge=0, description="Максимальная длительность в минутах"),
    sort_date: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по дате"),
    sort_duration: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по длительности"),
    sort_importance: Optional[str] = Query(None, regex="^(asc|desc)$", description="Сортировка по важности"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить встречи **внутри проекта**.

    Возвращает все встречи, привязанные к данному проекту.
    Доступно всем участникам проекта (Admin видит встречи всех проектов).

    Фильтрация:
    - q: поиск по названию встречи
    - organizer_id: фильтр по конкретному организатору
    - start_date / end_date: диапазон дат (ISO 8601)
    - min_duration / max_duration: диапазон длительности в минутах

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
    # Проверить доступ к проекту
    has_access = await selectors.check_user_has_project_access(
        db, current_user.id, current_user.role, project_id
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project"
        )

    sort_fields = []
    if sort_importance:
        sort_fields.append(f"importance_{sort_importance}")
    if sort_date:
        sort_fields.append(f"date_{sort_date}")
    if sort_duration:
        sort_fields.append(f"duration_{sort_duration}")
    sort_by = ",".join(sort_fields) if sort_fields else "date_desc"

    meetings, total = await meeting_selectors.get_project_meetings_with_filters(
        db,
        project_id=project_id,
        search_query=q,
        organizer_id=organizer_id,
        start_date=start_date,
        end_date=end_date,
        min_duration=min_duration,
        max_duration=max_duration,
        sort_by=sort_by,
        skip=skip,
        limit=limit,
        return_count=True
    )

    base_url = f"http://localhost:8000/api/projects/{project_id}/meetings"
    next_url = f"{base_url}?skip={skip + limit}&limit={limit}" if skip + limit < total else None
    previous_url = f"{base_url}?skip={max(0, skip - limit)}&limit={limit}" if skip > 0 else None

    results = [meeting_schemas.MeetingListOutWithOrganizer.model_validate(m) for m in meetings]
    return {"count": total, "next": next_url, "previous": previous_url, "results": results}


@router.get("/{project_id}", response_model=schemas.ProjectOut)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить детали проекта"""
    # Проверить доступ
    has_access = await selectors.check_user_has_project_access(db, current_user.id, current_user.role, project_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project"
        )
    
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    members_count = await selectors.get_project_members_count(db, project.id)
    meetings_count = await selectors.get_project_meetings_count(db, project.id)
    
    project_out = schemas.ProjectOut.model_validate(project)
    project_out.members_count = members_count
    project_out.meetings_count = meetings_count
    
    return project_out


@router.put("/{project_id}", response_model=schemas.ProjectOut)
async def update_project(
    project_id: int,
    data: schemas.ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновить проект (только Admin или Manager владелец проекта)"""
    # Проверить права на редактирование
    can_edit = await selectors.check_user_can_edit_project(db, current_user.id, current_user.role, project_id)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can edit project"
        )
    
    project = await services.update_project(db, project_id, data)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    members_count = await selectors.get_project_members_count(db, project.id)
    meetings_count = await selectors.get_project_meetings_count(db, project.id)
    
    project_out = schemas.ProjectOut.model_validate(project)
    project_out.members_count = members_count
    project_out.meetings_count = meetings_count
    
    return project_out


@router.post("/{project_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Архивировать проект (только Admin или Manager владелец проекта)"""
    can_edit = await selectors.check_user_can_edit_project(db, current_user.id, current_user.role, project_id)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can archive project"
        )
    
    success = await services.archive_project(db, project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )


@router.post("/{project_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
async def unarchive_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Разархивировать проект (только Admin или Manager владелец проекта)"""
    can_edit = await selectors.check_user_can_edit_project(db, current_user.id, current_user.role, project_id)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can unarchive project"
        )
    
    success = await services.unarchive_project(db, project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить проект (только Admin или Manager владелец проекта)"""
    can_edit = await selectors.check_user_can_edit_project(db, current_user.id, current_user.role, project_id)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can delete project"
        )
    
    success = await services.delete_project(db, project_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )


@router.post("/{project_id}/access", response_model=schemas.ProjectAccessOutWithUser)
async def grant_access(
    project_id: int,
    data: schemas.ProjectAccessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Дать доступ пользователю к проекту (только Admin или Manager владелец проекта)"""
    can_grant = await selectors.check_user_can_grant_access(db, current_user.id, current_user.role, project_id)
    if not can_grant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can grant access"
        )
    
    # Проверить существует ли проект
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    access = await services.grant_project_access(db, project_id, data.user_id, data.role)
    return access


@router.get("/{project_id}/access", response_model=List[schemas.ProjectAccessOutWithUser])
async def get_project_access(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Получить список доступов к проекту (только для Admin или пользователей с доступом к проекту)"""
    # Admin видит все доступы
    if current_user.role == "Admin":
        accesses = await selectors.get_project_access(db, project_id)
        return accesses
    
    # Остальные видят доступы только к проектам, куда их добавили
    has_access = await selectors.check_user_has_project_access(db, current_user.id, current_user.role, project_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project"
        )
    
    accesses = await selectors.get_project_access(db, project_id)
    return accesses


@router.delete("/{project_id}/access/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_access(
    project_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Отозвать доступ пользователя к проекту (только Admin или Manager владелец проекта)"""
    can_grant = await selectors.check_user_can_grant_access(db, current_user.id, current_user.role, project_id)
    if not can_grant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can revoke access"
        )
    
    success = await services.revoke_project_access(db, project_id, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access not found"
        )


@router.post("/{project_id}/cover", response_model=schemas.ProjectCoverUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_project_cover(
    project_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Загрузить обложку проекта (только Admin или Manager владелец проекта)

    Загружает изображение в качестве обложки проекта в S3.
    Файл сохраняется в папке project_covers/{project_name}_{project_id}/
    """
    # Проверить права на редактирование
    can_edit = await selectors.check_user_can_edit_project(db, current_user.id, current_user.role, project_id)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can upload cover"
        )

    # Проверить существует ли проект
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    # Проверить размер файла (максимум 10MB)
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size too large. Maximum size is 10MB"
        )

    # Проверить формат файла
    allowed_formats = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    if file.content_type not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file format. Allowed: JPEG, PNG, GIF, WebP"
        )

    # Загрузить обложку
    updated_project = await services.upload_project_cover(
        db, project_id, file_bytes, file.filename or "cover.jpg"
    )

    if not updated_project:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload cover"
        )

    return schemas.ProjectCoverUploadResponse(
        id=updated_project.id,
        cover=updated_project.cover,
        message="Cover uploaded successfully"
    )


@router.delete("/{project_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_cover(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить обложку проекта (только Admin или Manager владелец проекта)

    Удаляет обложку проекта из S3 и очищает поле cover в БД.
    """
    # Проверить права на редактирование
    can_edit = await selectors.check_user_can_edit_project(db, current_user.id, current_user.role, project_id)
    if not can_edit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only Admin or Manager project owner can delete cover"
        )

    # Проверить существует ли проект
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    # Удалить обложку
    await services.delete_project_cover(db, project_id)

