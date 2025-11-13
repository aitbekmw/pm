from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from src.db.deps import get_db
from src.users.models import User
from src.core.permissions import get_current_user, require_manager_or_admin
from src.projects import schemas, services, selectors


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

