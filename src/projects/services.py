from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from datetime import datetime, timezone
from typing import Optional

from src.projects.models import Project, ProjectAccess
from src.projects.schemas import ProjectCreate, ProjectUpdate
from src.projects import selectors


async def create_project(
    db: AsyncSession, 
    data: ProjectCreate, 
    user_id: int
) -> Project:
    """Создать новый проект"""
    project = Project(
        name=data.name,
        description=data.description,
        confluence_data=data.confluence_data,
        jira_data=data.jira_data,
        created_by=user_id,
        is_archived=False
    )
    db.add(project)
    await db.flush()
    
    # Автоматически добавить создателя как участника
    access = ProjectAccess(
        project_id=project.id,
        user_id=user_id,
        role="Manager",
        granted_at=datetime.now(timezone.utc)
    )
    db.add(access)
    await db.commit()
    await db.refresh(project)
    
    return project


async def update_project(
    db: AsyncSession, 
    project_id: int, 
    data: ProjectUpdate
) -> Optional[Project]:
    """Обновить проект"""
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        return None
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    await db.commit()
    await db.refresh(project)
    return project


async def archive_project(db: AsyncSession, project_id: int) -> bool:
    """Архивировать проект"""
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        return False
    
    project.is_archived = True
    await db.commit()
    return True


async def unarchive_project(db: AsyncSession, project_id: int) -> bool:
    """Разархивировать проект"""
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        return False
    
    project.is_archived = False
    await db.commit()
    return True


async def delete_project(db: AsyncSession, project_id: int) -> bool:
    """Удалить проект"""
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        return False
    
    # Удалить все доступы
    await db.execute(
        delete(ProjectAccess).where(ProjectAccess.project_id == project_id)
    )
    
    # Удалить проект
    await db.delete(project)
    await db.commit()
    return True


async def grant_project_access(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    role: Optional[str] = None
) -> ProjectAccess:
    """Дать доступ пользователю к проекту"""
    # Проверить существует ли уже доступ
    existing_access = await selectors.get_user_project_access(db, user_id, project_id)
    
    if existing_access:
        # Обновить роль если указана
        if role:
            existing_access.role = role
            await db.commit()
            await db.refresh(existing_access)
        return existing_access
    
    # Создать новый доступ
    access = ProjectAccess(
        project_id=project_id,
        user_id=user_id,
        role=role,
        granted_at=datetime.now(timezone.utc)
    )
    db.add(access)
    await db.commit()
    await db.refresh(access)
    return access


async def revoke_project_access(
    db: AsyncSession,
    project_id: int,
    user_id: int
) -> bool:
    """Отозвать доступ пользователя к проекту"""
    result = await db.execute(
        delete(ProjectAccess).where(
            ProjectAccess.project_id == project_id,
            ProjectAccess.user_id == user_id
        )
    )
    await db.commit()
    return result.rowcount > 0

