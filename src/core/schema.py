from typing import List, Any, Dict, Union
from pydantic import BaseModel


class Pagination(BaseModel):
    total: int
    per_page: int
    current_page: int
    last_page: int


class SuccessResponse(BaseModel):
    status: str = "success"
    data: Union[List[Any], Dict] = {}
    pagination: Pagination | None = None
    message: str = ""


class ErrorDetails(BaseModel):
    field: str | None = None
    issue: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: dict = {
        "code": str,
        "message": str,
        "details": ErrorDetails | None
    }
