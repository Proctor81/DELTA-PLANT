"""Cookie preference helper routes for NASA DeltaPlant."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from api.cookie_utils import cookie_policy_for_request

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

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


def _require_session(request: Request) -> None:
    if getattr(request.state, "session_payload", None):
        return
    raise HTTPException(status_code=401, detail="Missing session context.")


def _require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("deltaplant_csrf")
    header_token = request.headers.get("X-CSRF-Token")
    if not request.app.state.orchestrator.consent_manager.validate_csrf(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")


class UserTokenRequest(BaseModel):
    user_token: str

    @field_validator("user_token")
    @classmethod
    def validate_user_token(cls, value: str) -> str:
        if not USER_TOKEN_PATTERN.fullmatch(value):
            raise ValueError("Invalid user_token format")
        return value


def _set_cookie(response: JSONResponse, request: Request, categories: dict[str, bool]) -> JSONResponse:
    response.set_cookie(
        "deltaplant_consent",
        json.dumps(categories, separators=(",", ":")),
        max_age=36 * 30 * 24 * 3600,
        httponly=False,
        **cookie_policy_for_request(request),
    )
    return response


@router.get("/preferences")
@limiter.limit("30/minute")
async def preferences(request: Request, user_token: str) -> JSONResponse:
    _require_session(request)
    if not USER_TOKEN_PATTERN.fullmatch(user_token):
        raise HTTPException(status_code=422, detail="Invalid user_token format")
    stored = request.app.state.orchestrator.consent_manager.get_status(user_token)
    merged = request.app.state.orchestrator.cookie_validator.merged_consent(
        user_token,
        request.cookies.get("deltaplant_consent"),
    )
    return JSONResponse(content={"stored": stored, "effective": merged})


@router.post("/accept-all")
@limiter.limit("10/minute")
async def accept_all(request: Request, payload: UserTokenRequest) -> JSONResponse:
    _require_session(request)
    _require_csrf(request)
    snapshot = request.app.state.orchestrator.consent_manager.grant_consent(
        payload.user_token,
        {"analytics": True, "maps": True, "voice": True, "llm": True},
        ip_address=request.headers.get("x-forwarded-for") or (request.client.host if request.client else None),
    )
    return _set_cookie(JSONResponse(content=snapshot), request, snapshot["categories"])


@router.post("/reject-all")
@limiter.limit("10/minute")
async def reject_all(request: Request, payload: UserTokenRequest) -> JSONResponse:
    _require_session(request)
    _require_csrf(request)
    snapshot = request.app.state.orchestrator.consent_manager.revoke_consent(payload.user_token)
    return _set_cookie(JSONResponse(content=snapshot), request, snapshot["categories"])