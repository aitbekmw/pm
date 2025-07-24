
from fastapi import status
from fastapi.responses import JSONResponse


def error_response(code: str, message: str, details=None, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "error": {
                "code": code,
                "message": message,
                "details": details or {}
            }
        },
    )


def success_response(data=None, message="Request processed successfully", status_code=status.HTTP_200_OK):
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "success",
            "data": data if data is not None else [],
            "message": message
        }
    )

