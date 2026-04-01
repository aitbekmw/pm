import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs metadata about the HTTP request.
    Expected to run AFTER RequestIdMiddleware.
    """
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        
        # Exclude common noisy health check routes
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)
            
        try:
            response = await call_next(request)
            process_time_ms = (time.perf_counter() - start_time) * 1000
            
            logger.info(
                f"{request.method} {request.url.path} HTTP/{request.scope.get('http_version', '1.1')} "
                f"{response.status_code} {process_time_ms:.2f}ms",
                extra={
                    "http_method": request.method,
                    "url_path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(process_time_ms, 2),
                }
            )
            return response
        except Exception as e:
            process_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{request.method} {request.url.path} FAILED {process_time_ms:.2f}ms",
                extra={
                    "http_method": request.method,
                    "url_path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round(process_time_ms, 2),
                },
                exc_info=True
            )
            raise
