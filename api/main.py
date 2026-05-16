"""FastAPI entrypoint for NASA DeltaPlant."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.cookie_routes import router as cookie_router
from api.nisar_routes import router as nisar_router
from api.privacy_routes import router as privacy_router
from nasa_delta_plant.config import get_settings
from nasa_delta_plant.orchestrator_node import NASADeltaPlantOrchestrator

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
except Exception:  # pragma: no cover - optional dependency fallback
    class RateLimitExceeded(Exception):
        pass

    class Limiter:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def limit(self, *args: Any, **kwargs: Any):
            def decorator(func):
                return func

            return decorator

    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded."})

    def get_remote_address(request: Request) -> str:
        return request.client.host if request.client else "unknown"


settings = get_settings()
orchestrator = NASADeltaPlantOrchestrator()
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="NASA DeltaPlant API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.state.orchestrator = orchestrator
app.state.limiter = limiter


def _build_session_payload() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "sub": secrets.token_urlsafe(18),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }


def create_session_token(payload: dict[str, Any] | None = None) -> str:
    token_payload = payload or _build_session_payload()
    return jwt.encode(token_payload, settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_session_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm])


app.state.create_session_token = create_session_token
app.state.decode_session_token = decode_session_token

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://deltaplant.ai",
        "https://www.deltaplant.ai",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "deltaplant.ai", "www.deltaplant.ai"],
)


@app.middleware("http")
async def session_cookie_middleware(request: Request, call_next):
    cookie_name = "deltaplant_session"
    csrf_cookie_name = "deltaplant_csrf"
    secure_cookie = request.url.scheme == "https" and request.url.hostname not in {"localhost", "127.0.0.1"}

    session_token = request.cookies.get(cookie_name)
    request.state.session_payload = None
    request.state.new_session_token = None

    if session_token:
        try:
            request.state.session_payload = decode_session_token(session_token)
        except JWTError:
            request.state.session_payload = _build_session_payload()
            request.state.new_session_token = create_session_token(request.state.session_payload)
    else:
        request.state.session_payload = _build_session_payload()
        request.state.new_session_token = create_session_token(request.state.session_payload)

    csrf_token = request.cookies.get(csrf_cookie_name)
    if not csrf_token:
        request.state.new_csrf_token = orchestrator.consent_manager.issue_csrf_token()
    else:
        request.state.new_csrf_token = None

    response = await call_next(request)

    if request.state.new_session_token:
        response.set_cookie(
            cookie_name,
            request.state.new_session_token,
            max_age=7 * 24 * 3600,
            httponly=True,
            secure=secure_cookie,
            samesite="strict",
            path="/",
        )
    if request.state.new_csrf_token:
        response.set_cookie(
            csrf_cookie_name,
            request.state.new_csrf_token,
            max_age=24 * 3600,
            httponly=False,
            secure=secure_cookie,
            samesite="strict",
            path="/",
        )
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "nasa-deltaplant",
        "session": bool(getattr(request.state, "session_payload", None)),
    }


app.include_router(nisar_router)
app.include_router(privacy_router)
app.include_router(cookie_router)