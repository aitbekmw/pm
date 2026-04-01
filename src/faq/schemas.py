from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class FAQBase(BaseModel):
    category_id: Optional[int] = None
    question: str
    answer: str
    order: Optional[int] = 0
    is_active: Optional[bool] = True

class FAQCreate(FAQBase):
    pass

class FAQUpdate(BaseModel):
    category_id: Optional[int] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class FAQOut(FAQBase):
    id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

class FAQCategoryBase(BaseModel):
    name: str
    order: Optional[int] = 0
    is_active: Optional[bool] = True

class FAQCategoryOut(FAQCategoryBase):
    id: int
    items: List[FAQOut] = []
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class FAQPublicItem(BaseModel):
    id: int
    question: str
    answer: str

    model_config = ConfigDict(from_attributes=True)


class FAQCategoryPublicOut(BaseModel):
    id: int
    name: str
    items: List[FAQPublicItem] = []

    model_config = ConfigDict(from_attributes=True)
