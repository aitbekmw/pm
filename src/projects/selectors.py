from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import Optional
from sqlalchemy.orm import joinedload

from src.projects.models import Project, ProjectAccess
from src.meetings.models import Meeting


async def get_project_by_id(db: AsyncSession, project_id: int) -> Optional[Project]:
    """Получить проект по ID"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalars().first()


async def get_user_projects(
    db: AsyncSession, 
    user_id: int,
    user_role: str,
    include_archived: bool = False
) -> list[Project]:
    """Получить все проекты пользователя
    
    Manager видит все проекты.
    PM видит только свои проекты (где он создатель или имеет роль PM).
    Остальные видят только проекты, куда их добавили.
    """
    if user_role == "Manager":
        # Manager видит все проекты
        query = select(Project)
        if not include_archived:
            query = query.where(Project.is_archived == False)
        result = await db.execute(query.order_by(Project.created_at.desc()))
        return list(result.scalars().all())
    elif user_role == "PM":
        # PM видит только свои проекты (где он создатель или имеет роль PM в ProjectAccess)
        # Используем подзапрос вместо JOIN с DISTINCT, чтобы избежать проблем с JSON полями
        pm_access_subquery = (
            select(ProjectAccess.project_id)
            .where(
                and_(
                    ProjectAccess.user_id == user_id,
                    ProjectAccess.role == "PM"
                )
            )
        )
        
        query = (
            select(Project)
            .where(
                or_(
                    Project.created_by == user_id,
                    Project.id.in_(pm_access_subquery)
                )
            )
        )
        if not include_archived:
            query = query.where(Project.is_archived == False)
        result = await db.execute(query.order_by(Project.created_at.desc()))
        return list(result.scalars().all())
    else:
        # Остальные видят только проекты, куда их добавили
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
    user_role: str,
    project_id: int
) -> bool:
    """Проверить имеет ли пользователь доступ к проекту (на чтение)
    
    Manager всегда имеет доступ ко всем проектам.
    PM имеет доступ к своим проектам (где он создатель или имеет роль PM).
    Остальные имеют доступ только к проектам, куда их добавили.
    """
    if user_role == "Manager":
        # Manager видит все проекты
        return True
    
    # Проверяем существование проекта
    project = await get_project_by_id(db, project_id)
    if not project:
        return False
    
    if user_role == "PM":
        # PM видит проекты, где он создатель или имеет роль PM в ProjectAccess
        if project.created_by == user_id:
            return True
        
        access = await get_user_project_access(db, user_id, project_id)
        if access and access.role == "PM":
            return True
        return False
    else:
        # Остальные видят только проекты, куда их добавили
        access = await get_user_project_access(db, user_id, project_id)
        return access is not None


async def check_user_can_edit_project(
    db: AsyncSession,
    user_id: int,
    user_role: str,
    project_id: int
) -> bool:
    """Проверить может ли пользователь редактировать/удалять проект
    
    Manager может редактировать все проекты.
    PM может редактировать только свои проекты (где он создатель или имеет роль PM).
    Остальные не могут редактировать проекты.
    """
    if user_role == "Manager":
        # Manager может редактировать все проекты
        return True
    
    if user_role != "PM":
        # Только PM или Manager могут редактировать
        return False
    
    # PM может редактировать только свои проекты
    project = await get_project_by_id(db, project_id)
    if not project:
        return False
    
    # Проверяем, является ли пользователь создателем проекта
    if project.created_by == user_id:
        return True
    
    # Проверяем, имеет ли пользователь роль PM в ProjectAccess
    access = await get_user_project_access(db, user_id, project_id)
    if access and access.role == "PM":
        return True
    
    return False


async def check_user_can_grant_access(
    db: AsyncSession,
    user_id: int,
    user_role: str,
    project_id: int
) -> bool:
    """Проверить может ли пользователь выдавать доступ к проекту
    
    Manager может выдавать доступ ко всем проектам.
    PM может выдавать доступ только к своим проектам (где он создатель или имеет роль PM).
    Остальные не могут выдавать доступ.
    """
    return await check_user_can_edit_project(db, user_id, user_role, project_id)


async def get_project_access(
    db: AsyncSession, 
    project_id: int
) -> list[ProjectAccess]:
    """Получить список доступов к проекту"""
    result = await db.execute(
        select(ProjectAccess)
        .where(ProjectAccess.project_id == project_id)
        .options(joinedload(ProjectAccess.user))
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
