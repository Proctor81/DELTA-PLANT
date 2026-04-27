"""
Middleware FastAPI per logging e CORS
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

logger = structlog.get_logger("api.middleware")

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info("Request", method=request.method, url=str(request.url))
        response = await call_next(request)
        logger.info("Response", status_code=response.status_code)
        return response
