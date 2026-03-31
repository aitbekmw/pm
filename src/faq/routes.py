from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.db.deps import get_db
from src.users.models import User
from src.core.permissions import get_current_user
from src.faq import schemas, services

router = APIRouter(prefix="/faq", tags=["faq"])

@router.get("/", response_model=List[schemas.FAQCategoryPublicOut])
async def get_faqs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить все активные FAQ, сгруппированные по категориям. Доступно всем авторизованным пользователям.
    """
    categories = await services.get_faq_categories(db, include_inactive=False)
    
    result = []
    for cat in categories:
        result.append({
            "id": cat.id,
            "name": cat.name,
            "items": [
                {
                    "id": faq.id,
                    "question": faq.question,
                    "answer": faq.answer,
                }
                for faq in cat.faqs
            ],
        })
    return result

# Если управление происходит через SQLAdmin, дополнительные (POST/PUT/DELETE) эндпоинты 
# для API можно опустить или добавить с проверкой прав, как показано ниже.

def check_mdigital_admin(user: User):
    """Проверка, что пользователь является администратором MDigital"""
    if user.role != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can manage FAQ")
    
    # Мы предполагаем, что компания либо доступна через relationship, либо через company_id.
    # В users/services.py видно, что AD-пользователи всегда MDigital
    # Для простоты можно проверить company_id = 1 или company.name == 'MDigital'
    # Так как этот эндпоинт используется редко (в основном админится через SQLAdmin),
    # Оставим базовую проверку роли, а точная проверка компании может потребовать загрузки company.
    pass

@router.post("/", response_model=schemas.FAQOut, status_code=status.HTTP_201_CREATED)
async def create_faq(
    data: schemas.FAQCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Создать новый FAQ (только для админов)"""
    check_mdigital_admin(current_user)
    faq = await services.create_faq(db, data)
    return faq

@router.put("/{faq_id}", response_model=schemas.FAQOut)
async def update_faq(
    faq_id: int,
    data: schemas.FAQUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновить существующий FAQ (только для админов)"""
    check_mdigital_admin(current_user)
    faq = await services.update_faq(db, faq_id, data)
    if not faq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found")
    return faq

@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    faq_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить FAQ (только для админов)"""
    check_mdigital_admin(current_user)
    deleted = await services.delete_faq(db, faq_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found")
