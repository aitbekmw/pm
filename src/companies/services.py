from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
import re

from src.companies.models import Company
from src.companies.schemas import CompanyCreate, CompanyUpdate

DEFAULT_COMPANIES = [
    "MDigital",
    "MInvest",
    "MMarket",
]


def _slugify(name: str) -> str:
    """Преобразует название компании в slug: 'MDigital' → 'mdigital'"""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def seed_default_companies(db: AsyncSession) -> None:
    """
    Добавляет в таблицу companies отсутствующие компании из DEFAULT_COMPANIES.
    Запускается при каждом старте приложения, но вставляет только новые записи.
    """
    for name in DEFAULT_COMPANIES:
        slug = _slugify(name)
        existing = await db.execute(select(Company).where(Company.slug == slug))
        if existing.scalars().first() is None:
            db.add(Company(name=name, slug=slug))

    await db.commit()


async def get_company_id_by_slug(db: AsyncSession, slug: str) -> Optional[int]:
    """Возвращает ID компании по slug, или None если не найдена"""
    result = await db.execute(select(Company.id).where(Company.slug == slug))
    return result.scalar()


async def create_company(db: AsyncSession, data: CompanyCreate) -> Company:
    """Create a new company"""
    company = Company(
        name=data.name,
        slug=data.slug
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


async def get_company(db: AsyncSession, company_id: int) -> Optional[Company]:
    """Get company by ID"""
    result = await db.execute(select(Company).where(Company.id == company_id))
    return result.scalars().first()


async def get_company_by_slug(db: AsyncSession, slug: str) -> Optional[Company]:
    """Get company by slug"""
    result = await db.execute(select(Company).where(Company.slug == slug))
    return result.scalars().first()


async def get_companies(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Company]:
    """Get list of companies"""
    result = await db.execute(
        select(Company)
        .offset(skip)
        .limit(limit)
        .order_by(Company.name)
    )
    return list(result.scalars().all())


async def update_company(db: AsyncSession, company_id: int, data: CompanyUpdate) -> Optional[Company]:
    """Update company details"""
    company = await get_company(db, company_id)
    if not company:
        return None
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)
    
    await db.commit()
    await db.refresh(company)
    return company
