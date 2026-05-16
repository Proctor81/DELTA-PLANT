"""Primary analysis routes for NASA DeltaPlant."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

try:
    import bleach
except Exception:  # pragma: no cover - optional dependency fallback
    class _BleachFallback:
        @staticmethod
        def clean(text: str, **_: Any) -> str:
            return text.replace("<", "").replace(">", "")

    bleach = _BleachFallback()

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
TEXT_PATTERN = re.compile(r"^[\w\s\.,;:!?()/%+'\-\u00C0-\u024F]{0,2000}$", re.UNICODE)
PROMPT_INJECTION_PATTERN = re.compile(r"ignore previous|system prompt|<script|```|role:|assistant:|developer:", re.IGNORECASE)

router = APIRouter(prefix="/api/nisar", tags=["nasa-deltaplant"])


def _require_session(request: Request) -> dict[str, Any]:
    payload = getattr(request.state, "session_payload", None)
    if payload:
        return payload
    token = request.cookies.get("deltaplant_session")
    if not token:
        raise HTTPException(status_code=401, detail="Missing session token.")
    try:
        return request.app.state.decode_session_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session token.") from exc


def _sanitize_text(value: str, max_length: int = 2000) -> str:
    cleaned = bleach.clean(value, tags=[], attributes={}, protocols=[], strip=True)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:max_length]
    if PROMPT_INJECTION_PATTERN.search(cleaned):
        raise HTTPException(status_code=422, detail="Unsafe text input detected.")
    if cleaned and not TEXT_PATTERN.fullmatch(cleaned):
        raise HTTPException(status_code=422, detail="Unsupported text characters detected.")
    return cleaned


class DateRangePayload(BaseModel):
    start: str
    end: str

    @model_validator(mode="after")
    def validate_order(self) -> "DateRangePayload":
        if self.start > self.end:
            raise ValueError("date_range.start must be before date_range.end")
        return self


class AreaAnalysisRequest(BaseModel):
    geo_data: dict[str, Any]
    date_range: DateRangePayload
    user_token: str
    crop_answers: list[str] = Field(default_factory=list)
    local_sensor_data: dict[str, Any] | None = None

    @field_validator("user_token")
    @classmethod
    def validate_user_token(cls, value: str) -> str:
        if not USER_TOKEN_PATTERN.fullmatch(value):
            raise ValueError("Invalid user_token format")
        return value

    @field_validator("crop_answers")
    @classmethod
    def sanitize_answers(cls, value: list[str]) -> list[str]:
        return [_sanitize_text(answer, max_length=80) for answer in value[:5]]


class CropQuestionRequest(BaseModel):
    question_number: int = Field(ge=0, le=5)
    answer: str | None = None
    sar_signature: dict[str, Any] = Field(default_factory=dict)

    @field_validator("answer")
    @classmethod
    def sanitize_answer(cls, value: str | None) -> str | None:
        return _sanitize_text(value, max_length=80) if value else value


class VoiceRequest(BaseModel):
    report_text: str
    language: str = Field(default="it")
    format: str = Field(default="ogg")
    user_token: str

    @field_validator("report_text")
    @classmethod
    def sanitize_report_text(cls, value: str) -> str:
        return _sanitize_text(value, max_length=2000)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"it", "en"}:
            raise ValueError("language must be 'it' or 'en'")
        return normalized

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"ogg", "wav", "mp3"}:
            raise ValueError("format must be ogg, wav or mp3")
        return normalized

    @field_validator("user_token")
    @classmethod
    def validate_voice_user_token(cls, value: str) -> str:
        if not USER_TOKEN_PATTERN.fullmatch(value):
            raise ValueError("Invalid user_token format")
        return value


@router.post("/area-analysis")
@limiter.limit("5/minute")
async def area_analysis(request: Request, payload: AreaAnalysisRequest) -> JSONResponse:
    _require_session(request)
    consent_cookie = request.cookies.get("deltaplant_consent")
    llm_enabled = request.app.state.orchestrator.cookie_validator.feature_allowed(payload.user_token, "llm", consent_cookie)
    try:
        result = await request.app.state.orchestrator.analyze_area(
            geo_data=payload.geo_data,
            date_range=payload.date_range.model_dump(),
            user_token=payload.user_token,
            crop_answers=payload.crop_answers,
            local_sensor_data=payload.local_sensor_data,
            enable_llm=llm_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return JSONResponse(content=result)


@router.post("/crop-question")
@limiter.limit("20/minute")
async def crop_question(request: Request, payload: CropQuestionRequest) -> JSONResponse:
    session = _require_session(request)
    result = request.app.state.orchestrator.handle_crop_question(
        session_id=str(session.get("sub")),
        question_number=payload.question_number,
        answer=payload.answer,
        sar_signature=payload.sar_signature,
    )
    return JSONResponse(content=result)


@router.post("/voice")
@limiter.limit("10/minute")
async def voice(request: Request, payload: VoiceRequest) -> StreamingResponse:
    _require_session(request)
    consent_cookie = request.cookies.get("deltaplant_consent")
    voice_allowed = request.app.state.orchestrator.cookie_validator.feature_allowed(payload.user_token, "voice", consent_cookie)
    if not voice_allowed:
        raise HTTPException(status_code=403, detail="Voice synthesis requires explicit consent.")

    audio_bytes, content_type, filename = await request.app.state.orchestrator.synthesize_voice(
        text=payload.report_text,
        language=payload.language,
        output_format=payload.format,
    )
    return StreamingResponse(
        BytesIO(audio_bytes),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/pdf/{token}")
@limiter.limit("30/minute")
async def download_pdf(request: Request, token: str) -> StreamingResponse:
    _require_session(request)
    artifact = request.app.state.orchestrator.get_pdf_artifact(token)
    if artifact is None:
        raise HTTPException(status_code=404, detail="PDF token expired or not found.")

    return StreamingResponse(
        BytesIO(artifact.data),
        media_type=artifact.content_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )

