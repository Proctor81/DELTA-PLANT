from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

import api.main as api_main


class FakeCookieValidator:
    def __init__(self) -> None:
        self.feature_calls = []

    def feature_allowed(self, user_token: str, feature: str, cookie_value: str | None) -> bool:
        self.feature_calls.append((user_token, feature, cookie_value))
        if not cookie_value:
            return False if feature in {"llm", "voice", "maps", "analytics"} else True
        categories = json.loads(cookie_value)
        return bool(categories.get(feature, False)) if feature != "api" else True

    def merged_consent(self, user_token: str, cookie_value: str | None) -> dict[str, bool]:
        categories = {
            "necessary": True,
            "analytics": False,
            "maps": False,
            "voice": False,
            "llm": False,
        }
        if cookie_value:
            categories.update(json.loads(cookie_value))
        return categories


class FakeConsentManager:
    def __init__(self) -> None:
        self._csrf = "csrf-test-token"
        self._store: dict[str, dict] = {}

    def issue_csrf_token(self) -> str:
        return self._csrf

    def validate_csrf(self, cookie_token: str | None, header_token: str | None) -> bool:
        return bool(cookie_token) and cookie_token == header_token == self._csrf

    def grant_consent(self, user_token: str, categories: dict[str, bool], ip_address: str | None = None) -> dict:
        snapshot = {
            "user_token_hash": f"hash:{user_token}",
            "categories": {"necessary": True, **categories},
            "created_at": "2026-05-16T00:00:00+00:00",
            "updated_at": "2026-05-16T00:00:00+00:00",
            "revoked_at": None,
            "ip_hash": ip_address,
            "history": [{"action": "grant"}],
        }
        self._store[user_token] = snapshot
        return snapshot

    def revoke_consent(self, user_token: str) -> dict:
        snapshot = self._store.get(
            user_token,
            {
                "user_token_hash": f"hash:{user_token}",
                "categories": {"necessary": True, "analytics": False, "maps": False, "voice": False, "llm": False},
                "created_at": "2026-05-16T00:00:00+00:00",
                "updated_at": "2026-05-16T00:00:00+00:00",
                "revoked_at": None,
                "ip_hash": None,
                "history": [],
            },
        )
        snapshot["categories"].update({"analytics": False, "maps": False, "voice": False, "llm": False})
        snapshot["revoked_at"] = "2026-05-16T00:05:00+00:00"
        self._store[user_token] = snapshot
        return snapshot

    def get_status(self, user_token: str) -> dict:
        return self._store.get(
            user_token,
            {
                "user_token_hash": f"hash:{user_token}",
                "categories": {"necessary": True, "analytics": False, "maps": False, "voice": False, "llm": False},
                "created_at": "2026-05-16T00:00:00+00:00",
                "updated_at": "2026-05-16T00:00:00+00:00",
                "revoked_at": None,
                "ip_hash": None,
                "history": [],
            },
        )

    def export_user_data(self, user_token: str) -> dict:
        return self.get_status(user_token)

    def delete_user_data(self, user_token: str) -> bool:
        return self._store.pop(user_token, None) is not None


@dataclass
class FakeStoredArtifact:
    data: bytes
    content_type: str
    filename: str


class FakeOrchestrator:
    def __init__(self) -> None:
        self.cookie_validator = FakeCookieValidator()
        self.consent_manager = FakeConsentManager()
        self.analysis_calls = []
        self.crop_calls = []
        self.voice_calls = []
        self.artifacts = {
            "report-token": FakeStoredArtifact(
                data=b"%PDF-1.4 fake pdf",
                content_type="application/pdf",
                filename="report.pdf",
            )
        }

    async def analyze_area(
        self,
        geo_data: dict,
        date_range: dict,
        user_token: str,
        crop_answers: list[str],
        local_sensor_data: dict | None,
        enable_llm: bool,
    ) -> dict:
        self.analysis_calls.append(
            {
                "geo_data": geo_data,
                "date_range": date_range,
                "user_token": user_token,
                "crop_answers": crop_answers,
                "local_sensor_data": local_sensor_data,
                "enable_llm": enable_llm,
            }
        )
        return {
            "field_state": {
                "sar_features": {
                    "soil_moisture_percent": 61.2,
                    "biomass_index": 72.1,
                    "disease_risk_composite": 34.8,
                    "yield_forecast_index": 78.3,
                },
                "raw_sar_summary": {
                    "source": "Sentinel-1",
                    "available_channels": ["VV", "VH"],
                    "interpolation_method": "ordinary_kriging",
                    "polarimetric_mode": "pseudo-dual-pol-vv-vh",
                    "insar_available": False,
                },
            },
            "diagnosis": {
                "probable_crop": "Tomato_healthy",
                "candidate_crops": ["Tomato_healthy", "Tomato_Early_blight"],
                "water_stress_level": "low",
                "disease_risk_level": "low",
                "confidence_score": 0.88,
                "irrigation_recommendation": "Irrigate lightly.",
                "drainage_recommendation": "No drainage action needed.",
                "anomalies": [],
                "report_farmer": "Farmer report",
                "report_scientist": "Scientist report",
                "llm_used": enable_llm,
            },
            "pdf_tokens": {"farmer": "report-token", "scientist": "report-token", "expires_in_minutes": 60},
            "llm_remaining_today": 0 if enable_llm else 1,
        }

    def handle_crop_question(self, session_id: str, question_number: int, answer: str | None, sar_signature: dict) -> dict:
        self.crop_calls.append(
            {
                "session_id": session_id,
                "question_number": question_number,
                "answer": answer,
                "sar_signature": sar_signature,
            }
        )
        if question_number == 0:
            return {
                "next_question": {
                    "number": 1,
                    "id": "growth_form",
                    "prompt": "Quale architettura ha la coltura dominante nell'area?",
                    "options": ["tree", "vine", "herbaceous"],
                },
                "candidate_crops": ["Tomato_healthy"],
                "probable_crop": "Tomato_healthy",
                "confidence": 0.52,
            }
        return {
            "next_question": None,
            "candidate_crops": ["Tomato_healthy"],
            "probable_crop": "Tomato_healthy",
            "confidence": 0.84,
        }

    async def synthesize_voice(self, text: str, language: str = "it", output_format: str = "ogg") -> tuple[bytes, str, str]:
        self.voice_calls.append({"text": text, "language": language, "output_format": output_format})
        return b"voice-bytes", "audio/ogg", "voice.ogg"

    def get_pdf_artifact(self, token: str) -> FakeStoredArtifact | None:
        return self.artifacts.get(token)


@pytest.fixture
def nasa_client(monkeypatch):
    fake_orchestrator = FakeOrchestrator()
    monkeypatch.setattr(api_main, "orchestrator", fake_orchestrator)
    monkeypatch.setattr(api_main.app.state, "orchestrator", fake_orchestrator)
    with TestClient(api_main.app, base_url="http://localhost") as client:
        yield client, fake_orchestrator


def test_health_sets_security_headers_and_session_cookies(nasa_client):
    client, _ = nasa_client

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "deltaplant_session" in client.cookies
    assert "deltaplant_csrf" in client.cookies


def test_area_analysis_uses_llm_consent_state(nasa_client):
    client, fake_orchestrator = nasa_client
    user_token = "dp_user_token_1234567890"
    client.get("/api/health")
    client.cookies.set(
        "deltaplant_consent",
        json.dumps({"necessary": True, "llm": True, "voice": False, "maps": False, "analytics": False}),
    )

    response = client.post(
        "/api/nisar/area-analysis",
        json={
            "geo_data": {"type": "circle", "center": {"lat": 45.46, "lng": 9.19}, "radius": 250.0},
            "date_range": {"start": "2026-04-01", "end": "2026-04-30"},
            "user_token": user_token,
            "crop_answers": ["herbaceous"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["diagnosis"]["probable_crop"] == "Tomato_healthy"
    assert fake_orchestrator.analysis_calls[0]["enable_llm"] is True
    assert fake_orchestrator.cookie_validator.feature_calls[-1][1] == "llm"


def test_privacy_consent_roundtrip_and_cookie_preferences(nasa_client):
    client, _ = nasa_client
    user_token = "dp_user_token_1234567890"
    client.get("/api/health")

    consent_response = client.post(
        "/api/privacy/consent",
        headers={"X-CSRF-Token": client.cookies["deltaplant_csrf"]},
        json={
            "user_token": user_token,
            "analytics": False,
            "maps": True,
            "voice": True,
            "llm": True,
        },
    )

    assert consent_response.status_code == 200
    assert consent_response.json()["categories"]["voice"] is True
    assert "deltaplant_consent" in client.cookies

    preferences_response = client.get(f"/api/cookies/preferences?user_token={user_token}")

    assert preferences_response.status_code == 200
    effective = preferences_response.json()["effective"]
    assert effective["maps"] is True
    assert effective["voice"] is True
    assert effective["llm"] is True


def test_pdf_download_handles_missing_and_present_tokens(nasa_client):
    client, _ = nasa_client
    client.get("/api/health")

    missing_response = client.get("/api/nisar/pdf/missing-token")
    assert missing_response.status_code == 404

    response = client.get("/api/nisar/pdf/report-token")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")