from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Sequence
import logging

from src.faq.models import FAQ
from src.faq.schemas import FAQCreate, FAQUpdate

logger = logging.getLogger(__name__)

async def get_faqs(db: AsyncSession, include_inactive: bool = False) -> Sequence[FAQ]:
    """Получить список всех FAQ, отсортированных по порядку"""
    stmt = select(FAQ)
    if not include_inactive:
        stmt = stmt.where(FAQ.is_active == True)
    stmt = stmt.order_by(FAQ.order.asc(), FAQ.id.desc())
    
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_faq_by_id(db: AsyncSession, faq_id: int) -> FAQ | None:
    """Получить FAQ по ID"""
    result = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    return result.scalars().first()

async def create_faq(db: AsyncSession, faq_in: FAQCreate) -> FAQ:
    """Создать новый FAQ"""
    db_faq = FAQ(
        question=faq_in.question,
        answer=faq_in.answer,
        order=faq_in.order,
        is_active=faq_in.is_active
    )
    db.add(db_faq)
    await db.commit()
    await db.refresh(db_faq)
    return db_faq

async def update_faq(db: AsyncSession, faq_id: int, faq_in: FAQUpdate) -> FAQ | None:
    """Обновить существующий FAQ"""
    db_faq = await get_faq_by_id(db, faq_id)
    if not db_faq:
        return None
        
    update_data = faq_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_faq, field, value)
        
    await db.commit()
    await db.refresh(db_faq)
    return db_faq

async def delete_faq(db: AsyncSession, faq_id: int) -> bool:
    """Удалить FAQ"""
    db_faq = await get_faq_by_id(db, faq_id)
    if not db_faq:
        return False
        
    await db.delete(db_faq)
    await db.commit()
    return True
