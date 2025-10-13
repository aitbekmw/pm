from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional

from src.projects.models import Project, ProjectAccess
from src.meetings.models import Meeting


async def get_project_by_id(db: AsyncSession, project_id: int) -> Optional[Project]:
    """Получить проект по ID"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalars().first()


async def get_user_projects(
    db: AsyncSession, 
    user_id: int, 
    include_archived: bool = False
) -> list[Project]:
    """Получить все проекты пользователя"""
    query = (
        select(Project)
        .join(ProjectAccess, ProjectAccess.project_id == Project.id)
        .where(ProjectAccess.user_id == user_id)
    )
    
    if not include_archived:
        query = query.where(Project.is_archived == False)
    
    result = await db.execute(query.order_by(Project.created_at.desc()))
    return list(result.scalars().all())


async def get_project_members_count(db: AsyncSession, project_id: int) -> int:
    """Получить количество участников проекта"""
    result = await db.execute(
        select(func.count(ProjectAccess.id))
        .where(ProjectAccess.project_id == project_id)
    )
    return result.scalar() or 0


async def get_project_meetings_count(db: AsyncSession, project_id: int) -> int:
    """Получить количество встреч проекта"""
    result = await db.execute(
        select(func.count(Meeting.id))
        .where(Meeting.project_id == project_id)
    )
    return result.scalar() or 0


async def check_user_has_project_access(
    db: AsyncSession, 
    user_id: int, 
    project_id: int
) -> bool:
    """Проверить имеет ли пользователь доступ к проекту"""
    result = await db.execute(
        select(ProjectAccess)
        .where(
            and_(
                ProjectAccess.user_id == user_id,
                ProjectAccess.project_id == project_id
            )
        )
    )
    return result.scalars().first() is not None


async def get_project_access(
    db: AsyncSession, 
    project_id: int
) -> list[ProjectAccess]:
    """Получить список доступов к проекту"""
    result = await db.execute(
        select(ProjectAccess)
        .where(ProjectAccess.project_id == project_id)
    )
    return list(result.scalars().all())


async def get_user_project_access(
    db: AsyncSession,
    user_id: int,
    project_id: int
) -> Optional[ProjectAccess]:
    """Получить доступ пользователя к проекту"""
    result = await db.execute(
        select(ProjectAccess)
        .where(
            and_(
                ProjectAccess.user_id == user_id,
                ProjectAccess.project_id == project_id
            )
        )
    )
    return result.scalars().first()

