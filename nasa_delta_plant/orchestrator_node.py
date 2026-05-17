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

import numpy as np

from chat.chat_engine import ChatEngine
from interface.telegram_bot import _prepare_telegram_voice_payload, text_to_speech_warm_male
from nasa_delta_plant.area_diagnosis import AreaDiagnosisService
from nasa_delta_plant.config import get_settings
from nasa_delta_plant.feature_extractor import FeatureExtractor
from nasa_delta_plant.integrator import FieldIntegrator, FieldState
from nasa_delta_plant.preprocessor import SARPreprocessor
from nasa_delta_plant.privacy import ConsentManager, CookieValidator, LLMUsageTracker, RetentionPolicy, RuntimePDFPolicy
from nasa_delta_plant.utils import NasaPowerClient, SentinelClient


SENTINEL_PIPELINE_TIMEOUT_SECONDS = 25.0


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
        processing_mode = "live"
        warnings: list[str] = []

        try:
            sentinel_payload = await asyncio.wait_for(
                self.sentinel_client.fetch(geo_data, start=start, end=end, max_results=2),
                timeout=SENTINEL_PIPELINE_TIMEOUT_SECONDS,
            )
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
        except (asyncio.TimeoutError, LookupError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
            processing_mode = "fallback"
            warnings.append(f"Sentinel pipeline fallback activated: {type(exc).__name__}: {exc}")
            field_state = self._build_climate_proxy_field_state(
                geo_area={**geo_data, **geo_summary},
                power_data=power_data,
                crop_answers=crop_answers,
                local_sensor_data=local_sensor_data,
                fallback_reason=warnings[-1],
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
            "processing_mode": processing_mode,
            "warnings": warnings,
            "pdf_tokens": {
                "farmer": farmer_token,
                "scientist": scientist_token,
                "expires_in_minutes": RetentionPolicy().runtime_pdf_ttl_minutes,
            },
            "llm_remaining_today": self.llm_usage_tracker.remaining_calls(user_token),
        }

    async def analyze_nasa_only(
        self,
        geo_data: dict[str, Any],
        date_range: dict[str, str],
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
        warnings: list[str] = []
        sar_context = await self._build_nasa_only_sar_context(
            geo_data=geo_data,
            power_data=power_data,
            start=start,
            end=end,
            warnings=warnings,
        )
        dashboard = self._build_nasa_only_dashboard(power_data, sar_context)

        return {
            "mode": "nasa-only",
            "geo_summary": geo_summary,
            "nasa_power": power_data,
            "sar_context": sar_context,
            "dashboard": dashboard,
            "warnings": warnings,
        }

    
    async def _build_nasa_only_sar_context(
        self,
        geo_data: dict[str, Any],
        power_data: dict[str, Any],
        start: date,
        end: date,
        warnings: list[str],
    ) -> dict[str, Any]:
        try:
            sentinel_payload = await asyncio.wait_for(
                self.sentinel_client.fetch(geo_data, start=start, end=end, max_results=2),
                timeout=SENTINEL_PIPELINE_TIMEOUT_SECONDS,
            )
            processed = self.preprocessor.preprocess(
                primary=sentinel_payload["primary"],
                secondary=sentinel_payload.get("secondary"),
            )
            features = self.feature_extractor.extract(processed, power_data)
            product = sentinel_payload["primary"].product
            return {
                "mode": "sar-live",
                "source": "Sentinel-1 SAR operational fallback",
                "soil_moisture_percent": round(float(features.soil_moisture_percent), 3),
                "product_name": product.name,
                "acquired_at": product.start_time.isoformat(),
            }
        except (asyncio.TimeoutError, LookupError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
            warnings.append(f"Sentinel soil-moisture fallback activated: {type(exc).__name__}: {exc}")
            climate_proxy = self._build_climate_proxy_soil_series(power_data)
            proxy_summary = climate_proxy["summary"]
            return {
                "mode": "climate-proxy",
                "source": "Climate proxy fallback",
                "soil_moisture_percent": round(float(proxy_summary.get("average_soil_moisture_percent", 0.0)), 3),
                "product_name": None,
                "acquired_at": None,
                "fallback_reason": warnings[-1],
            }

    
    def _build_climate_proxy_soil_series(power_data: dict[str, Any]) -> dict[str, Any]:
        daily = power_data.get("daily", []) or []
        recent_daily = daily[-7:]
        soil_series: list[dict[str, Any]] = []

        for index, day in enumerate(recent_daily):
            window = recent_daily[max(0, index - 6): index + 1]
            recent_precip = sum(float(item.get("PRECTOTCORR", 0.0)) for item in window)
            recent_et0 = sum(float(item.get("ET0", 0.0)) for item in window)
            water_stress_mean = (
                sum(float(item.get("water_stress_index", 0.0)) for item in window) / len(window)
                if window else 0.0
            )
            soil_moisture = float(
                np.clip(
                    58.0 + (recent_precip * 0.35) - (recent_et0 * 0.55) - (water_stress_mean * 25.0),
                    0.0,
                    100.0,
                )
            )
            soil_series.append(
                {
                    "day": day.get("day"),
                    "soil_moisture_percent": round(soil_moisture, 3),
                    "precip_mm": round(float(day.get("PRECTOTCORR", 0.0)), 3),
                    "et0_mm": round(float(day.get("ET0", 0.0)), 3),
                    "water_stress_index": round(float(day.get("water_stress_index", 0.0)), 3),
                }
            )

        values = [float(item["soil_moisture_percent"]) for item in soil_series]
        summary = {
            "days": len(soil_series),
            "latest_soil_moisture_percent": round(values[-1], 3) if values else 0.0,
            "average_soil_moisture_percent": round(float(np.mean(values)), 3) if values else 0.0,
            "min_soil_moisture_percent": round(min(values), 3) if values else 0.0,
            "max_soil_moisture_percent": round(max(values), 3) if values else 0.0,
            "trend_delta_percent": round(values[-1] - values[0], 3) if len(values) >= 2 else 0.0,
        }
        return {
            "soil_moisture_last_7_days": soil_series,
            "summary": summary,
        }

    
    def _build_nasa_only_dashboard(power_data: dict[str, Any], sar_context: dict[str, Any] | None = None) -> dict[str, Any]:
        climate_proxy = NASADeltaPlantOrchestrator._build_climate_proxy_soil_series(power_data)
        summary = dict(climate_proxy.get("summary", {}) or {})
        recent_daily = (power_data.get("daily", []) or [])[-7:]
        sar_context = sar_context or {}
        summary.update(
            {
                "sar_soil_moisture_percent": round(float(sar_context.get("soil_moisture_percent", 0.0) or 0.0), 3),
                "sar_source": str(sar_context.get("source", "Climate proxy fallback")),
                "sar_mode": str(sar_context.get("mode", "climate-proxy")),
                "sar_product_name": sar_context.get("product_name"),
                "sar_acquired_at": sar_context.get("acquired_at"),
                "weather_window_start": recent_daily[0].get("day") if recent_daily else None,
                "weather_window_end": recent_daily[-1].get("day") if recent_daily else None,
            }
        )
        climate_proxy["summary"] = summary
        climate_proxy["weather_last_7_days"] = recent_daily
        return climate_proxy

    def _build_climate_proxy_field_state(
        self,
        geo_area: dict[str, Any],
        power_data: dict[str, Any],
        crop_answers: list[str] | None,
        local_sensor_data: dict[str, Any] | None,
        fallback_reason: str,
    ) -> FieldState:
        power_daily = power_data.get("daily", [])
        power_summary = power_data.get("summary", {})
        recent_window = power_daily[-7:] if power_daily else []
        recent_precip = sum(float(day.get("PRECTOTCORR", 0.0)) for day in recent_window)
        recent_et0 = sum(float(day.get("ET0", 0.0)) for day in recent_window)
        water_stress_mean = float(power_summary.get("water_stress_mean", 0.0))
        water_stress_peak = float(power_summary.get("water_stress_peak", 0.0))
        fungal_peak = float(power_summary.get("fungal_risk_peak", 0.0))
        gdd_total = float(power_summary.get("gdd_total", 0.0))

        soil_moisture = float(np.clip(58.0 + (recent_precip * 0.35) - (recent_et0 * 0.55) - (water_stress_mean * 25.0), 0.0, 100.0))
        biomass_index = float(np.clip(34.0 + (gdd_total / 18.0) - (water_stress_mean * 22.0), 0.0, 100.0))
        canopy_structure = float(np.clip(38.0 + (gdd_total / 24.0) - (water_stress_peak * 18.0), 0.0, 100.0))
        crop_height = float(np.clip(18.0 + (biomass_index * 1.15) + (canopy_structure * 0.30), 5.0, 350.0))
        disease_risk = float(np.clip((fungal_peak * 62.0) + (soil_moisture * 0.18) + (water_stress_peak * 20.0), 0.0, 100.0))
        yield_forecast = float(np.clip(72.0 + (biomass_index * 0.18) - (disease_risk * 0.24) - (water_stress_mean * 20.0), 0.0, 100.0))

        sar_features = {
            "soil_moisture_percent": round(soil_moisture, 3),
            "biomass_index": round(biomass_index, 3),
            "crop_height_estimate_cm": round(crop_height, 3),
            "canopy_structure_metric": round(canopy_structure, 3),
            "disease_risk_composite": round(disease_risk, 3),
            "yield_forecast_index": round(yield_forecast, 3),
            "support_metrics": {
                "crop_class": None,
                "recent_precip_mm": round(recent_precip, 3),
                "recent_et0_mm": round(recent_et0, 3),
                "fallback_mode": "climate_proxy",
                "fallback_reason": fallback_reason,
            },
        }
        crop_resolution = self.area_diagnosis.crop_engine.resolve_from_answers(crop_answers, sar_features)
        probable_crop = crop_resolution.get("probable_crop")
        sar_features["support_metrics"]["crop_class"] = probable_crop

        confidence = 0.43
        if probable_crop:
            confidence += 0.08
        if crop_answers:
            confidence += min(len(crop_answers), 5) * 0.03
        if power_daily:
            confidence += 0.10
        confidence = float(np.clip(confidence, 0.0, 0.82))

        return FieldState(
            sar_features=sar_features,
            power_data=power_data,
            local_sensor_data=local_sensor_data,
            analysis_timestamp=datetime.now(timezone.utc).isoformat(),
            geo_area=geo_area,
            crop_class=probable_crop,
            confidence_score=round(confidence, 3),
            raw_sar_summary={
                "source": "climate_proxy_fallback",
                "available_channels": [],
                "polarimetric_mode": "fallback",
                "interpolation_method": "not_available",
                "insar_available": False,
                "fallback_mode": True,
                "fallback_reason": fallback_reason,
                "mean_soil_moisture_grid": round(soil_moisture, 3),
            },
        )

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