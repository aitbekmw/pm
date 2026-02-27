from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class CompanyBase(BaseModel):
    name: str
    slug: str


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None


class CompanyRead(CompanyBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
