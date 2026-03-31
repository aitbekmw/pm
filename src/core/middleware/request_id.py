import uuid
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

REQUEST_ID_CTX_KEY = "request_id"

# The context variable storing the actual Request ID
_request_id_ctx_var: ContextVar[str] = ContextVar(REQUEST_ID_CTX_KEY, default="-")

def get_request_id() -> str:
    """Retrieves the current request ID from context."""
    return _request_id_ctx_var.get()

class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that reads X-Request-ID from headers or generates a new one.
    Stores it in contextvars for logging.
    """
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract from header or generate a new UUID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Set contextvar
        token = _request_id_ctx_var.set(request_id)
        
        try:
            # Pass downward
            response = await call_next(request)
            
            # Make sure it's returned to the client
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _request_id_ctx_var.reset(token)
