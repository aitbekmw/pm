
from fastapi import Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from .responses import error_response


async def general_exception_handler(request: Request, e: Exception):
    return error_response(
        code="INTERNAL_SERVER_ERROR",
        message=str(e) or "An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


async def http_exception_handler(request: Request, e: HTTPException):
    return error_response(
        code=e.detail or "HTTP_ERROR",
        message="An HTTP error occurred",
        status_code=e.status_code
    )


async def validation_exception_handler(request: Request, e: RequestValidationError):
    errors = e.errors()
    detail_messages = [
        {"field": err.get("loc")[-1], "issue": err.get("msg")}
        for err in errors
    ]

    return error_response(
        code="VALIDATION_ERROR",
        message="Validation failed for one or more fields",
        details=detail_messages,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )

