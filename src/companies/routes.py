from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.db.deps import get_db
from src.core.permissions import get_current_user, require_manager_or_admin
from src.users.models import User
from src.companies import services
from src.companies.schemas import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(tags=["Companies"])


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin)
):
    """
    Create a new company.
    Only Managers or Admins can create companies.
    """
    existing_company = await services.get_company_by_slug(db, data.slug)
    if existing_company:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this slug already exists"
        )
    
    return await services.create_company(db, data)


@router.get("/companies", response_model=List[CompanyRead])
async def get_companies(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of companies.
    """
    return await services.get_companies(db, skip, limit)


@router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get company details by ID.
    """
    company = await services.get_company(db, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    return company
