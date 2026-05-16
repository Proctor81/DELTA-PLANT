"""Top-level orchestration for the NASA DeltaPlant analysis pipeline."""

from __future__ import annotations

import asyncio
import secrets
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from chat.chat_engine import ChatEngine
from interface.telegram_bot import _prepare_telegram_voice_payload, text_to_speech_warm_male
from nasa_delta_plant.area_diagnosis import AreaDiagnosisService
from nasa_delta_plant.config import get_settings
from nasa_delta_plant.feature_extractor import FeatureExtractor
from nasa_delta_plant.integrator import FieldIntegrator
from nasa_delta_plant.preprocessor import SARPreprocessor
from nasa_delta_plant.privacy import ConsentManager, CookieValidator, LLMUsageTracker, RetentionPolicy, RuntimePDFPolicy
from nasa_delta_plant.utils import NasaPowerClient, SentinelClient


@dataclass(slots=True)
class StoredArtifact:
    data: bytes
    content_type: str
    filename: str
    expires_at: datetime


class ExpiringArtifactStore:
    def __init__(self, retention: RetentionPolicy | None = None) -> None:
        self.retention = retention or RetentionPolicy()
        self._lock = threading.RLock()
        self._store: dict[str, StoredArtifact] = {}

    def put(self, data: bytes, content_type: str, filename: str) -> str:
        with self._lock:
            self._purge_locked()
            token = secrets.token_urlsafe(24)
            self._store[token] = StoredArtifact(
                data=data,
                content_type=content_type,
                filename=filename,
                expires_at=self.retention.pdf_expiry(),
            )
            return token

    def get(self, token: str) -> StoredArtifact | None:
        with self._lock:
            self._purge_locked()
            artifact = self._store.get(token)
            if artifact is None:
                return None
            if artifact.expires_at <= datetime.now(timezone.utc):
                self._store.pop(token, None)
                return None
            return artifact

    def _purge_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [token for token, artifact in self._store.items() if artifact.expires_at <= now]
        for token in expired:
            self._store.pop(token, None)


class _SyntheticTelegramContext:
    def __init__(self) -> None:
        self.application = SimpleNamespace(bot_data={})
        self.user_data: dict[str, Any] = {}


class VoiceService:
    def __init__(self, chat_engine: ChatEngine | None = None) -> None:
        self.chat_engine = chat_engine

    async def synthesize(self, text: str, language: str = "it", output_format: str = "ogg") -> tuple[bytes, str, str]:
        text_for_voice = await self._prepare_text(text, language)
        context = _SyntheticTelegramContext()
        audio = await text_to_speech_warm_male(context, text_for_voice)
        if output_format.lower() == "ogg":
            audio = await _prepare_telegram_voice_payload(audio)
            return audio.getvalue(), "audio/ogg", "voice.ogg"
        return audio.getvalue(), self._content_type(audio), Path(getattr(audio, "name", "voice.wav")).name or "voice.wav"

    async def _prepare_text(self, text: str, language: str) -> str:
        if language.lower() != "en" or self.chat_engine is None:
            return text
        translation = await asyncio.to_thread(
            self.chat_engine.chat_internal,
            f"Translate this agronomic message to concise English without adding new facts:\n\n{text}",
        )
        return translation.strip() or text

    @staticmethod
    def _content_type(audio: BytesIO) -> str:
        suffix = Path(getattr(audio, "name", "voice.wav")).suffix.lower()
        if suffix == ".mp3":
            return "audio/mpeg"
        if suffix == ".ogg":
            return "audio/ogg"
        return "audio/wav"


class NASADeltaPlantOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.chat_engine = ChatEngine()
        self.power_client = NasaPowerClient(self.settings)
        self.sentinel_client = SentinelClient(self.settings)
        self.preprocessor = SARPreprocessor()
        self.feature_extractor = FeatureExtractor()
        self.integrator = FieldIntegrator()
        self.consent_manager = ConsentManager(self.settings)
        self.cookie_validator = CookieValidator(self.consent_manager)
        self.llm_usage_tracker = LLMUsageTracker(self.consent_manager)
        self.area_diagnosis = AreaDiagnosisService(chat_engine=self.chat_engine)
        self.pdf_policy = RuntimePDFPolicy()
        self.artifact_store = ExpiringArtifactStore()
        self.voice_service = VoiceService(chat_engine=self.chat_engine)

    async def analyze_area(
        self,
        geo_data: dict[str, Any],
        date_range: dict[str, str],
        user_token: str,
        crop_answers: list[str] | None,
        local_sensor_data: dict[str, Any] | None = None,
        enable_llm: bool = True,
    ) -> dict[str, Any]:
        geo_summary = self.area_diagnosis.validate_geo_area(geo_data)
        start = date.fromisoformat(date_range["start"])
        end = date.fromisoformat(date_range["end"])
        centroid = geo_summary["centroid"]

        power_data = await self.power_client.fetch(
            latitude=float(centroid["lat"]),
            longitude=float(centroid["lon"]),
            start=start,
            end=end,
        )
        sentinel_payload = await self.sentinel_client.fetch(geo_data, start=start, end=end, max_results=2)
        processed = self.preprocessor.preprocess(
            primary=sentinel_payload["primary"],
            secondary=sentinel_payload.get("secondary"),
        )
        preliminary_features = self.feature_extractor.extract(processed, power_data)
        crop_resolution = self.area_diagnosis.crop_engine.resolve_from_answers(crop_answers, preliminary_features.as_dict())
        features = self.feature_extractor.extract(processed, power_data, crop_class=crop_resolution.get("probable_crop"))
        field_state = self.integrator.fuse(
            features=features,
            processed_sar=processed,
            power_data=power_data,
            geo_area={**geo_data, **geo_summary},
            local_sensor_data=local_sensor_data,
            crop_class=crop_resolution.get("probable_crop"),
        )

        llm_allowed = enable_llm and self.llm_usage_tracker.try_consume(user_token)
        diagnosis = self.area_diagnosis.diagnose(field_state, crop_answers=crop_answers, allow_llm=llm_allowed)
        pdf_farmer = self.pdf_policy.build_farmer_pdf(field_state.as_dict(), diagnosis)
        pdf_scientist = self.pdf_policy.build_scientist_pdf(field_state.as_dict(), diagnosis)
        farmer_token = self.artifact_store.put(pdf_farmer, "application/pdf", "deltaplant_farmer_report.pdf")
        scientist_token = self.artifact_store.put(pdf_scientist, "application/pdf", "deltaplant_scientist_report.pdf")

        return {
            "field_state": field_state.as_dict(),
            "diagnosis": diagnosis,
            "pdf_tokens": {
                "farmer": farmer_token,
                "scientist": scientist_token,
                "expires_in_minutes": RetentionPolicy().runtime_pdf_ttl_minutes,
            },
            "llm_remaining_today": self.llm_usage_tracker.remaining_calls(user_token),
        }

    def get_pdf_artifact(self, token: str) -> StoredArtifact | None:
        return self.artifact_store.get(token)

    async def synthesize_voice(self, text: str, language: str = "it", output_format: str = "ogg") -> tuple[bytes, str, str]:
        return await self.voice_service.synthesize(text=text, language=language, output_format=output_format)

    def handle_crop_question(
        self,
        session_id: str,
        question_number: int,
        answer: str | None,
        sar_signature: dict[str, Any],
    ) -> dict[str, Any]:
        return self.area_diagnosis.crop_engine.ask(
            session_id=session_id,
            question_number=question_number,
            answer=answer,
            sar_signature=sar_signature,
        )