from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class FAQBase(BaseModel):
    question: str
    answer: str
    order: Optional[int] = 0
    is_active: Optional[bool] = True

class FAQCreate(FAQBase):
    pass

class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class FAQOut(FAQBase):
    id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
