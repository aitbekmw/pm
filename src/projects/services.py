from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone
from typing import Optional
import io
import uuid

from src.projects.models import Project, ProjectAccess
from src.projects.schemas import ProjectCreate, ProjectUpdate
from src.projects import selectors
from src.users.models import User
from src.core.storage import storage


async def create_project(
    db: AsyncSession, 
    data: ProjectCreate, 
    user_id: int,
    cover_bytes: Optional[bytes] = None,
    cover_filename: Optional[str] = None,
    cover_default: Optional[str] = None
) -> Project:
    """Создать новый проект
    
    Args:
        db: Database session
        data: Данные проекта (ProjectCreate)
        user_id: ID создателя проекта
        cover_bytes: Опциональные байты файла обложки
        cover_filename: Опциональное имя файла обложки
        cover_default: Опциональное имя дефолтной обложки (default-blue, default-red)
    """
    # Получить пользователя для наследования company_id
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalars().first()
    company_id = user.company_id if user else None

    project = Project(
        name=data.name,
        description=data.description,
        confluence_data=data.confluence_data,
        jira_data=data.jira_data,
        created_by=user_id,
        company_id=company_id,
        is_archived=False,
        cover=cover_default  # Установить дефолтную обложку если есть
    )
    db.add(project)
    await db.flush()
    
    # Автоматически добавить создателя как участника с ролью Manager
    creator_access = ProjectAccess(
        project_id=project.id,
        user_id=user_id,
        role="Manager",
        granted_at=datetime.now(timezone.utc)
    )
    db.add(creator_access)
    
    # Добавить пользователей из запроса
    users_to_notify = []
    if data.users:
        for user_data in data.users:
            # Пропускаем создателя, так как он уже добавлен
            if user_data.id == user_id:
                continue
            
            access = ProjectAccess(
                project_id=project.id,
                user_id=user_data.id,
                role=user_data.role,
                granted_at=datetime.now(timezone.utc)
            )
            db.add(access)
            users_to_notify.append(user_data.id)

    await db.commit()
    await db.refresh(project)
    
    # Загрузить обложку если она передана как файл
    if cover_bytes and cover_filename:
        updated_project = await upload_project_cover(
            db, project.id, cover_bytes, cover_filename
        )
        if updated_project:
            project = updated_project

    # Отправляем уведомления участникам, добавленным при создании проекта
    if users_to_notify:
        from src.notifications import services as notification_services
        for uid in users_to_notify:
            await notification_services.create_notification(
                db=db,
                user_id=uid,
                type="added_to_project",
                title="Вас добавили в проект",
                message=f"Вас добавили в проект {project.name}",
                project_id=project.id
            )

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
        
        # Перезагрузить объект с загрузкой связанного user
        result = await db.execute(
            select(ProjectAccess)
            .where(ProjectAccess.id == existing_access.id)
            .options(joinedload(ProjectAccess.user))
        )
        return result.scalars().one()
    
    # Создать новый доступ
    access = ProjectAccess(
        project_id=project_id,
        user_id=user_id,
        role=role,
        granted_at=datetime.now(timezone.utc)
    )
    db.add(access)
    await db.commit()
    
    # Отправка уведомления пользователю
    from src.notifications import services as notification_services
    project = await selectors.get_project_by_id(db, project_id)
    if project:
        await notification_services.create_notification(
            db=db,
            user_id=user_id,
            type="added_to_project",
            title="Вас добавили в проект",
            message=f"Вас добавили в проект {project.name}",
            project_id=project_id
        )
    
    # Перезагрузить объект с загрузкой связанного user
    result = await db.execute(
        select(ProjectAccess)
        .where(ProjectAccess.id == access.id)
        .options(joinedload(ProjectAccess.user))
    )
    return result.scalars().one()


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


async def upload_project_cover(
    db: AsyncSession,
    project_id: int,
    file_bytes: bytes,
    original_filename: str
) -> Optional[Project]:
    """
    Загрузить обложку проекта в S3

    Args:
        db: Database session
        project_id: ID проекта
        file_bytes: Байты файла изображения
        original_filename: Оригинальное имя файла

    Returns:
        Updated Project object или None если проект не найден
    """
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        return None

    # Удалить старую обложку если существует
    if project.cover:
        storage.delete_file(project.cover)

    # Генерируем уникальное имя для файла
    file_ext = original_filename.rsplit('.', 1)[-1] if '.' in original_filename else 'jpg'
    unique_filename = f"{uuid.uuid4()}.{file_ext}"

    # Определяем правильный content-type по расширению
    content_type_map = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp'
    }
    content_type = content_type_map.get(file_ext.lower(), 'image/jpeg')

    # Формируем путь: project_covers/project_name_id/filename
    project_folder = f"project_covers/{project.name.replace(' ', '_')}_{project_id}"
    object_name = f"{project_folder}/{unique_filename}"

    # Загружаем файл
    file_obj = io.BytesIO(file_bytes)
    uploaded_path = storage.upload_file(file_obj, object_name, content_type=content_type)

    if not uploaded_path:
        return None

    # Обновляем проект с путем к обложке
    project.cover = uploaded_path
    await db.commit()
    await db.refresh(project)

    return project


async def delete_project_cover(db: AsyncSession, project_id: int) -> Optional[Project]:
    """
    Удалить обложку проекта

    Args:
        db: Database session
        project_id: ID проекта

    Returns:
        Updated Project object или None если проект не найден
    """
    project = await selectors.get_project_by_id(db, project_id)
    if not project:
        return None

    # Удалить файл из S3 если существует и это не дефолтная обложка
    if project.cover and '/' in project.cover:
        storage.delete_file(project.cover)
    
    project.cover = None
    await db.commit()
    await db.refresh(project)

    return project



