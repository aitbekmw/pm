from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.deps import get_db
from src.core.permissions import get_current_user
from src.users.models import User
from src.meetings import selectors
from src.projects import selectors as project_selectors
from src.meetings.models import Meeting


async def get_meeting_with_read_access(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Meeting:
    """Зависимость для проверки прав на чтение встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Admin всегда имеет доступ
    if current_user.role == "Admin":
        return meeting
        
    # Организатор всегда имеет доступ
    if meeting.organizer_id == current_user.id:
        return meeting
        
    # Проверка доступа через проект
    if meeting.project_id:
        has_access = await project_selectors.check_user_has_project_access(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if has_access:
            return meeting
            
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied"
    )


async def get_meeting_with_edit_access(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Meeting:
    """Зависимость для проверки прав на редактирование/удаление встречи"""
    meeting = await selectors.get_meeting_by_id(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found"
        )
    
    # Только организатор, Admin или Manager владелец проекта может изменять/удалять
    if meeting.organizer_id == current_user.id:
        return meeting
    
    if current_user.role == "Admin":
        return meeting
        
    if meeting.project_id and current_user.role == "Manager":
        can_edit = await project_selectors.check_user_can_edit_project(
            db, current_user.id, current_user.role, meeting.project_id
        )
        if can_edit:
            return meeting
            
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only organizer, Admin or Manager project owner can perform this action"
    )
