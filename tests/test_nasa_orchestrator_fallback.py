from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

from ai.expiring_artifact_store import ExpiringArtifactStore
from nasa_delta_plant.orchestrator_node import NASADeltaPlantOrchestrator


def test_expiring_artifact_store_put_and_get():
    store = ExpiringArtifactStore()

    token = store.put(b"%PDF test", "application/pdf", "report.pdf")
    artifact = store.get(token)

    assert artifact is not None
    assert artifact.data == b"%PDF test"
    assert artifact.content_type == "application/pdf"
    assert artifact.filename == "report.pdf"


def test_orchestrator_returns_demo_hero_payload_for_area_analysis():
    orchestrator = cast(Any, NASADeltaPlantOrchestrator.__new__(NASADeltaPlantOrchestrator))
    orchestrator.settings = SimpleNamespace()

    async def fake_power_fetch(**kwargs):
        return {
            "daily": [
                {"PRECTOTCORR": 3.2, "ET0": 2.0},
                {"PRECTOTCORR": 0.8, "ET0": 2.3},
            ],
            "summary": {
                "water_stress_mean": 0.21,
                "water_stress_peak": 0.34,
                "fungal_risk_peak": 0.27,
                "gdd_total": 420.0,
                "et0_mean": 2.15,
            },
        }

    async def fake_sentinel_fetch(*args, **kwargs):
        raise ModuleNotFoundError("compression")

    class FakeCropEngine:
        def resolve_from_answers(self, answers, sar_signature):
            return {"probable_crop": "Tomato_healthy", "confidence": 0.62}

    class FakeAreaDiagnosis:
        def __init__(self):
            self.crop_engine = FakeCropEngine()

        def validate_geo_area(self, geo_data):
            return {
                "centroid": {"lat": 45.46, "lon": 9.19},
                "area_hectares": 19.635,
                "bounds": [9.18, 45.45, 9.20, 45.47],
            }

        def diagnose(self, field_state, crop_answers, allow_llm):
            assert field_state.raw_sar_summary["fallback_mode"] is True
            return {
                "probable_crop": field_state.crop_class,
                "candidate_crops": [field_state.crop_class],
                "water_stress_level": "low",
                "disease_risk_level": "low",
                "confidence_score": field_state.confidence_score,
                "irrigation_recommendation": "Apply a light irrigation pulse.",
                "drainage_recommendation": "Drainage is currently acceptable.",
                "anomalies": [],
                "report_farmer": "Farmer report",
                "report_scientist": "Scientist report",
                "llm_used": allow_llm,
            }

    orchestrator.power_client = SimpleNamespace(fetch=fake_power_fetch)
    orchestrator.sentinel_client = SimpleNamespace(fetch=fake_sentinel_fetch)
    orchestrator.preprocessor = SimpleNamespace(preprocess=lambda **kwargs: (_ for _ in ()).throw(AssertionError("preprocess should not run")))
    orchestrator.feature_extractor = SimpleNamespace(extract=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("extract should not run")))
    orchestrator.integrator = SimpleNamespace(fuse=lambda **kwargs: (_ for _ in ()).throw(AssertionError("fuse should not run")))
    orchestrator.area_diagnosis = FakeAreaDiagnosis()
    orchestrator.llm_usage_tracker = SimpleNamespace(
        try_consume=lambda user_token: True,
        remaining_calls=lambda user_token: 3,
    )
    orchestrator.pdf_policy = SimpleNamespace(
        build_farmer_pdf=lambda field_state, diagnosis: b"%PDF farmer",
        build_scientist_pdf=lambda field_state, diagnosis: b"%PDF scientist",
    )
    orchestrator.artifact_store = SimpleNamespace(
        put=lambda data, content_type, filename: f"token:{filename}",
    )

    result = asyncio.run(
        orchestrator.analyze_area(
            geo_data={"type": "circle", "center": {"lat": 45.46, "lng": 9.19}, "radius": 250.0},
            date_range={"start": "2026-04-01", "end": "2026-04-30"},
            user_token="dp_user_token_1234567890",
            crop_answers=["herbaceous"],
            enable_llm=False,
        )
    )

    assert result["processing_mode"] == "demo-hero-forced"
    assert "DEMO HERO forzato" in result["warnings"][0]
    assert result["field_state"]["raw_sar_summary"]["source"] == "Browser demo fallback"
    assert result["diagnosis"]["probable_crop"] == "Tomato_healthy"
    assert result["pdf_tokens"]["farmer"] == "demo-farmer-report"


def test_analyze_nasa_only_prefers_live_dashboard(monkeypatch):
    orchestrator = cast(Any, NASADeltaPlantOrchestrator.__new__(NASADeltaPlantOrchestrator))
    orchestrator.area_diagnosis = SimpleNamespace(
        validate_geo_area=lambda geo_data: {
            "centroid": {"lat": 41.9028, "lon": 12.4964},
            "radius_m": 50,
        }
    )

    monkeypatch.setattr(
        "bot.nasa_sar_dashboard.generate_dashboard",
        lambda lat, lon, start=None, end=None: {
            "dashboard": [
                {
                    "date": "2026-05-25",
                    "soil": 28.8,
                    "temp": 24.5,
                    "humidity": 41.0,
                    "rain": 0.0,
                    "risk": 0.24,
                }
            ],
            "weekly_risk": 0.24,
            "weekly_label": "BASSO",
            "summary": {
                "sar_soil_moisture_percent": 28.8,
                "weather_window_start": "2026-05-19",
                "weather_window_end": "2026-05-25",
            },
        },
    )

    result = asyncio.run(
        orchestrator.analyze_nasa_only(
            geo_data={"type": "circle", "center": {"lat": 41.9028, "lng": 12.4964}, "radius": 50},
            date_range={"start": "2026-05-19", "end": "2026-05-25"},
        )
    )

    assert result["mode"] == "live-weather-openmeteo-nasa"
    assert result["dashboard"]["dashboard"][0]["date"] == "2026-05-25"
    assert result["dashboard"]["weekly_label"] == "BASSO"