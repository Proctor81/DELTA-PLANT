from typing import Any
from datetime import date, datetime, timedelta, timezone
import numpy as np
from types import SimpleNamespace
from nasa_delta_plant.area_diagnosis import AreaDiagnosisService
from chat.chat_engine import ChatEngine
from ai.voice_service import VoiceService
from ai.expiring_artifact_store import ExpiringArtifactStore, StoredArtifact
from nasa_delta_plant.area_diagnosis import FieldState

class _SyntheticTelegramContext:
    def __init__(self) -> None:
        self.application = SimpleNamespace(bot_data={})
        self.user_data: dict[str, Any] = {}



# Classe orchestrator compatibile con il bot Telegram
class NASADeltaPlantOrchestrator:
    def __init__(self) -> None:
        self.area_diagnosis = AreaDiagnosisService(chat_engine=ChatEngine())
        self.artifact_store = ExpiringArtifactStore()
        self.voice_service = VoiceService(chat_engine=self.area_diagnosis.chat_engine)

    async def analyze_area(
        self,
        geo_data: dict[str, Any],
        date_range: dict[str, str],
        user_token: str,
        crop_answers: list[str] | None,
        local_sensor_data: dict[str, Any] | None = None,
        enable_llm: bool = True,
    ) -> dict[str, Any]:
        """
        Analisi area: usa SEMPRE la logica DEMO HERO fallback per garantire allineamento assoluto con il sito.
        """
        from ai.demo_hero_fallback import build_demo_analysis_payload
        crop_answers = crop_answers or []
        payload = build_demo_analysis_payload(
            geo_data=geo_data,
            date_start=date_range["start"],
            date_end=date_range["end"],
            crop_answers=crop_answers,
            consent={"llm": enable_llm},
        )
        payload["processing_mode"] = "demo-hero-forced"
        payload["warnings"] = ["DEMO HERO forzato: tutti i dati sono generati dalla logica browser DEMO HERO per allineamento totale."]
        payload["pdf_tokens"] = {
            "farmer": "demo-farmer-report",
            "scientist": "demo-scientist-report",
            "expires_in_minutes": 0,
        }
        return payload


    async def analyze_nasa_only(
        self,
        geo_data: dict[str, Any],
        date_range: dict[str, str],
    ) -> dict[str, Any]:
        import logging
        logger = logging.getLogger("deltaplano.demo_hero")
        from bot.nasa_sar_dashboard import generate_dashboard
        from datetime import datetime, timedelta

        center = geo_data.get("center", {}) or {}
        latitude = float(center.get("lat", center.get("latitude", 0.0)) or 0.0)
        longitude = float(center.get("lng", center.get("lon", center.get("longitude", 0.0))) or 0.0)

        try:
            start = datetime.strptime(date_range["start"], "%Y-%m-%d").date()
            end = datetime.strptime(date_range["end"], "%Y-%m-%d").date()
        except Exception:
            end = datetime.utcnow().date()
            start = end - timedelta(days=6)

        try:
            dashboard = generate_dashboard(latitude, longitude, start=start, end=end)
            logger.warning(f"[DEBUG] LIVE NASA/OPEN-METEO dashboard: {dashboard}")
            return {
                "mode": "live-weather-openmeteo-nasa",
                "geo_summary": self.area_diagnosis.validate_geo_area(geo_data),
                "dashboard": dashboard,
            }
        except Exception as exc:
            logger.error("[DEBUG] analyze_nasa_only live dashboard fallita, uso fallback demo: %s", exc, exc_info=True)

        from ai.demo_hero_fallback import build_demo_analysis_payload

        payload = build_demo_analysis_payload(
            geo_data=geo_data,
            date_start=date_range["start"],
            date_end=date_range["end"],
            crop_answers=[],
            consent={"llm": False},
        )
        logger.warning(f"[DEBUG] DEMO HERO payload: {payload}")
        daily = []
        soil = payload["field_state"]["sar_features"]["soil_moisture_percent"]
        temp = 22.0 + ((geo_data.get("center", {}).get("lat", 0) % 7) - 3)
        humidity = 60.0 + ((geo_data.get("center", {}).get("lng", 0) % 11) - 5)
        rain = 2.0 + ((geo_data.get("center", {}).get("lat", 0) + geo_data.get("center", {}).get("lng", 0)) % 3)
        risk = payload["field_state"]["sar_features"]["disease_risk_composite"] / 100.0
        fallback_start = start
        for i in range(7):
            day = (fallback_start + timedelta(days=i)).strftime("%Y-%m-%d")
            daily.append({
                "date": day,
                "soil": soil,
                "temp": temp,
                "humidity": humidity,
                "rain": rain,
                "risk": risk,
            })
        if risk >= 0.8:
            weekly_label = "ALTO"
        elif risk >= 0.6:
            weekly_label = "MEDIO"
        elif risk >= 0.3:
            weekly_label = "BASSO"
        else:
            weekly_label = "NESSUNO"
        dashboard = {
            "dashboard": daily,
            "weekly_risk": risk,
            "weekly_label": weekly_label,
        }
        logger.warning(f"[DEBUG] DEMO HERO dashboard: {dashboard}")
        return {
            "mode": "demo-hero-forced",
            "geo_summary": self.area_diagnosis.validate_geo_area(geo_data),
            "dashboard": dashboard,
        }

    @staticmethod
    def _build_nasa_only_dashboard(power_data: dict[str, Any]) -> dict[str, Any]:
        # Replica la logica HERO DEMO: tabella 7 giorni, rischio settimanale, label
        daily = power_data.get("daily", []) or []
        recent_daily = daily[-7:]
        out = []
        prev_risk = 0.0
        for day in recent_daily:
            temp = day.get("T2M") or 0.0
            humidity = day.get("RH2M") or 0.0
            rain = day.get("PRECTOTCORR") or 0.0
            soil = day.get("soil_moisture_percent", 0.0)
            from nasa_delta_plant.utils.power_client import compute_fungal_risk_score
            risk = compute_fungal_risk_score(temp, humidity, rain, prev_risk)
            prev_risk = risk
            out.append({
                "date": day.get("day", "N/D"),
                "soil": soil,
                "temp": temp,
                "humidity": humidity,
                "rain": rain,
                "risk": risk,
            })
        risk_label = NASADeltaPlantOrchestrator._risk_label(prev_risk)
        return {"dashboard": out, "weekly_risk": prev_risk, "weekly_label": risk_label}

    @staticmethod
    def _risk_label(score: float) -> str:
        if score >= 0.8:
            return "ALTO"
        elif score >= 0.6:
            return "MEDIO"
        elif score >= 0.3:
            return "BASSO"
        else:
            return "NESSUNO"

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

    @staticmethod
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

    @staticmethod
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