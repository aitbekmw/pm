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
    
    Admin видит все проекты.
    Manager видит проекты, где он создатель или куда его добавили.
    Остальные видят только проекты, куда их добавили.
    """
    if user_role == "Admin":
        # Admin видит все проекты
        query = select(Project)
        if not include_archived:
            query = query.where(Project.is_archived == False)
        result = await db.execute(query.order_by(Project.created_at.desc()))
        return list(result.scalars().all())
    elif user_role == "Manager":
        # Manager видит проекты, где он создатель или куда его добавили (любая запись в ProjectAccess)
        # Используем подзапрос вместо JOIN с DISTINCT, чтобы избежать проблем с JSON полями
        manager_access_subquery = (
            select(ProjectAccess.project_id)
            .where(ProjectAccess.user_id == user_id)
        )
        
        query = (
            select(Project)
            .where(
                or_(
                    Project.created_by == user_id,
                    Project.id.in_(manager_access_subquery)
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
    
    Admin всегда имеет доступ ко всем проектам.
    Manager имеет доступ к проектам, где он создатель или куда его добавили.
    Остальные имеют доступ только к проектам, куда их добавили.
    """
    if user_role == "Admin":
        # Admin видит все проекты
        return True
    
    # Проверяем существование проекта
    project = await get_project_by_id(db, project_id)
    if not project:
        return False
    
    if user_role == "Manager":
        # Manager видит проекты, где он создатель или куда его добавили (любая запись в ProjectAccess)
        if project.created_by == user_id:
            return True
        
        access = await get_user_project_access(db, user_id, project_id)
        return access is not None
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
    
    Admin может редактировать все проекты.
    Manager может редактировать только свои проекты (где он создатель или имеет роль Manager).
    Остальные не могут редактировать проекты.
    """
    if user_role == "Admin":
        # Admin может редактировать все проекты
        return True
    
    if user_role != "Manager":
        # Только Manager или Admin могут редактировать
        return False
    
    # Manager может редактировать только свои проекты
    project = await get_project_by_id(db, project_id)
    if not project:
        return False
    
    # Проверяем, является ли пользователь создателем проекта
    if project.created_by == user_id:
        return True
    
    # Проверяем, имеет ли пользователь роль Manager в ProjectAccess
    access = await get_user_project_access(db, user_id, project_id)
    if access and access.role == "Manager":
        return True
    
    return False


async def check_user_can_grant_access(
    db: AsyncSession,
    user_id: int,
    user_role: str,
    project_id: int
) -> bool:
    """Проверить может ли пользователь выдавать доступ к проекту
    
    Admin может выдавать доступ ко всем проектам.
    Manager может выдавать доступ только к своим проектам (где он создатель или имеет роль Manager).
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


async def search_projects(
    db: AsyncSession,
    query: str,
    user_id: int,
    user_role: str,
    include_archived: bool = False
) -> list[Project]:
    """Поиск проектов по названию
    
    Учитывает права доступа пользователя:
    - Admin видит все проекты
    - Manager видит проекты, где он создатель или куда его добавили
    - Остальные видят только проекты, куда их добавили
    
    Args:
        query: Поисковый запрос (поиск по имени проекта)
        user_id: ID пользователя
        user_role: Роль пользователя
        include_archived: Включать ли архивированные проекты в поиск
    """
    search_filter = Project.name.ilike(f"%{query}%")
    
    if user_role == "Admin":
        # Admin видит все проекты
        query_obj = select(Project).where(search_filter)
        if not include_archived:
            query_obj = query_obj.where(Project.is_archived == False)
        result = await db.execute(query_obj.order_by(Project.created_at.desc()))
        return list(result.scalars().all())
    elif user_role == "Manager":
        # Manager видит проекты, где он создатель или куда его добавили (любая запись в ProjectAccess)
        manager_access_subquery = (
            select(ProjectAccess.project_id)
            .where(ProjectAccess.user_id == user_id)
        )
        
        query_obj = (
            select(Project)
            .where(
                and_(
                    search_filter,
                    or_(
                        Project.created_by == user_id,
                        Project.id.in_(manager_access_subquery)
                    )
                )
            )
        )
        if not include_archived:
            query_obj = query_obj.where(Project.is_archived == False)
        result = await db.execute(query_obj.order_by(Project.created_at.desc()))
        return list(result.scalars().all())
    else:
        # Остальные видят только проекты, куда их добавили
        query_obj = (
            select(Project)
            .join(ProjectAccess, ProjectAccess.project_id == Project.id)
            .where(
                and_(
                    ProjectAccess.user_id == user_id,
                    search_filter
                )
            )
        )
        if not include_archived:
            query_obj = query_obj.where(Project.is_archived == False)
        result = await db.execute(query_obj.order_by(Project.created_at.desc()))
        return list(result.scalars().all())
