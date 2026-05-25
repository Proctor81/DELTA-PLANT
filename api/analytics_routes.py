"""First-party analytics ingestion routes for DELTA Plant website."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field


USER_TOKEN_PATTERN = r"^[A-Za-z0-9._:-]{16,128}$"
SESSION_PATTERN = r"^[A-Za-z0-9._:-]{6,128}$"
EVENT_TYPE_PATTERN = r"^[a-z0-9_:-]{3,32}$"


class AnalyticsEventRequest(BaseModel):
    user_token: str = Field(min_length=16, max_length=128, pattern=USER_TOKEN_PATTERN)
    session_id: str | None = Field(default=None, min_length=6, max_length=128, pattern=SESSION_PATTERN)
    event_type: str = Field(min_length=3, max_length=32, pattern=EVENT_TYPE_PATTERN)
    event_label: str | None = Field(default=None, max_length=96)
    page_path: str = Field(min_length=1, max_length=400)
    page_title: str | None = Field(default=None, max_length=160)
    referrer: str | None = Field(default=None, max_length=400)
    language: str | None = Field(default=None, max_length=24)
    timezone: str | None = Field(default=None, max_length=64)
    device_type: str | None = Field(default=None, max_length=24)
    viewport: str | None = Field(default=None, max_length=32)
    screen: str | None = Field(default=None, max_length=32)
    engaged_seconds: float | None = Field(default=None, ge=0)
    event_data: dict[str, Any] = Field(default_factory=dict)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(request: Request, payload: AnalyticsEventRequest) -> dict[str, Any]:
    consent_cookie = request.cookies.get("deltaplant_consent")
    if not request.app.state.orchestrator.cookie_validator.feature_allowed(
        payload.user_token,
        "analytics",
        consent_cookie,
    ):
        raise HTTPException(status_code=403, detail="Analytics tracking requires explicit consent.")

    tracker = getattr(request.app.state, "analytics_tracker", None)
    if tracker is None:
        tracker = getattr(request.app.state.orchestrator, "website_analytics_tracker", None)
    if tracker is None:
        raise HTTPException(status_code=503, detail="Analytics tracker unavailable.")

    session_payload = getattr(request.state, "session_payload", None) or {}
    result = tracker.record_event(
        payload.model_dump(),
        session_id=payload.session_id or session_payload.get("sub"),
    )
    return result