"""Privacy management routes for NASA DeltaPlant."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

try:
    from slowapi import Limiter
except Exception:  # pragma: no cover - optional dependency fallback
    class Limiter:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def limit(self, *args: Any, **kwargs: Any):
            def decorator(func):
                return func

            return decorator


limiter = Limiter(key_func=lambda request: request.client.host if request.client else "unknown")
USER_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{16,128}$")

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


def _require_session(request: Request) -> None:
    if getattr(request.state, "session_payload", None):
        return
    raise HTTPException(status_code=401, detail="Missing session context.")


def _require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("deltaplant_csrf")
    header_token = request.headers.get("X-CSRF-Token")
    if not request.app.state.orchestrator.consent_manager.validate_csrf(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")


def _secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https" and request.url.hostname not in {"localhost", "127.0.0.1"}


class ConsentRequest(BaseModel):
    user_token: str
    analytics: bool = Field(default=False)
    maps: bool = Field(default=False)
    voice: bool = Field(default=False)
    llm: bool = Field(default=False)

    @field_validator("user_token")
    @classmethod
    def validate_user_token(cls, value: str) -> str:
        if not USER_TOKEN_PATTERN.fullmatch(value):
            raise ValueError("Invalid user_token format")
        return value

    def categories(self) -> dict[str, bool]:
        return {
            "analytics": self.analytics,
            "maps": self.maps,
            "voice": self.voice,
            "llm": self.llm,
        }


@router.post("/consent")
@limiter.limit("10/minute")
async def consent(request: Request, payload: ConsentRequest) -> JSONResponse:
    _require_session(request)
    _require_csrf(request)
    ip_address = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    snapshot = request.app.state.orchestrator.consent_manager.grant_consent(
        user_token=payload.user_token,
        categories=payload.categories(),
        ip_address=ip_address,
    )
    response = JSONResponse(content=snapshot)
    response.set_cookie(
        "deltaplant_consent",
        json.dumps(snapshot["categories"], separators=(",", ":")),
        max_age=36 * 30 * 24 * 3600,
        httponly=False,
        secure=_secure_cookie(request),
        samesite="strict",
        path="/",
    )
    return response


@router.get("/consent-status")
@limiter.limit("20/minute")
async def consent_status(request: Request, user_token: str) -> JSONResponse:
    _require_session(request)
    if not USER_TOKEN_PATTERN.fullmatch(user_token):
        raise HTTPException(status_code=422, detail="Invalid user_token format")
    snapshot = request.app.state.orchestrator.consent_manager.get_status(user_token)
    return JSONResponse(content=snapshot)


@router.get("/export/{user_token}")
@limiter.limit("5/minute")
async def export_user_data(request: Request, user_token: str) -> JSONResponse:
    _require_session(request)
    _require_csrf(request)
    if not USER_TOKEN_PATTERN.fullmatch(user_token):
        raise HTTPException(status_code=422, detail="Invalid user_token format")
    payload = request.app.state.orchestrator.consent_manager.export_user_data(user_token)
    return JSONResponse(content=payload)


@router.delete("/delete/{user_token}")
@limiter.limit("5/minute")
async def delete_user_data(request: Request, user_token: str) -> JSONResponse:
    _require_session(request)
    _require_csrf(request)
    if not USER_TOKEN_PATTERN.fullmatch(user_token):
        raise HTTPException(status_code=422, detail="Invalid user_token format")
    deleted = request.app.state.orchestrator.consent_manager.delete_user_data(user_token)
    response = JSONResponse(content={"deleted": deleted})
    response.delete_cookie("deltaplant_consent", path="/")
    return response
