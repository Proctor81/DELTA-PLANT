from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from nasa_delta_plant.privacy.cookie_validator import CookieValidator


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

    def hash_identifier(self, value: str) -> str:
        return f"hash:{value}"


class FakeWebsiteAnalyticsTracker:
    def __init__(self) -> None:
        self.events = []
        self.report_calls = []

    def record_event(self, payload: dict, session_id: str | None = None) -> dict:
        stored = {**payload, "session_id": session_id}
        self.events.append(stored)
        return {
            "accepted": True,
            "event_id": len(self.events),
            "event_type": payload["event_type"],
            "page_path": payload["page_path"],
            "created_at": "2026-05-25T12:00:00+00:00",
        }

    def build_report(self, days: int = 30, recent_limit: int = 12) -> dict:
        self.report_calls.append({"days": days, "recent_limit": recent_limit})
        return {
            "window_days": days,
            "generated_at": "2026-05-25T12:00:00+00:00",
            "storage_path": "/tmp/fake.sqlite",
            "totals": {
                "total_events": 3,
                "unique_visitors": 2,
                "unique_sessions": 2,
                "page_views": 2,
                "session_starts": 1,
                "cta_clicks": 0,
                "outbound_clicks": 0,
                "hero_dashboard_runs": 0,
                "contact_submissions": 0,
                "avg_engagement_seconds": 4.5,
            },
            "consent_overview": None,
            "event_breakdown": [{"event_type": "page_view", "count": 2}],
            "top_pages": [{"page_path": "/", "count": 2}],
            "top_referrers": [],
            "top_campaigns": [],
            "device_breakdown": [],
            "language_breakdown": [],
            "daily": [{"day": "2026-05-25", "events": 3, "visitors": 2}],
            "recent_events": [
                {
                    "created_at": "2026-05-25T12:00:00+00:00",
                    "event_type": "page_view",
                    "event_label": "home",
                    "page_path": "/",
                    "referrer_host": None,
                    "device_type": "desktop",
                    "language": "en-US",
                    "engaged_seconds": None,
                }
            ][:recent_limit],
        }


@dataclass
class FakeStoredArtifact:
    data: bytes
    content_type: str
    filename: str


class FakeOrchestrator:
    def __init__(self) -> None:
        self.cookie_validator = FakeCookieValidator()
        self.consent_manager = FakeConsentManager()
        self.website_analytics_tracker = FakeWebsiteAnalyticsTracker()
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

    async def analyze_nasa_only(self, geo_data: dict, date_range: dict) -> dict:
        return {
            "mode": "nasa-only",
            "geo_summary": {
                "centroid": {"lat": 45.46, "lon": 9.19},
                "radius_m": 50.0,
            },
            "nasa_power": {
                "daily": [
                    {"day": "2026-04-24", "PRECTOTCORR": 1.2, "ET0": 2.5, "water_stress_index": 0.32},
                    {"day": "2026-04-25", "PRECTOTCORR": 0.8, "ET0": 2.2, "water_stress_index": 0.28},
                ]
            },
            "dashboard": {
                "soil_moisture_last_7_days": [
                    {"day": "2026-04-24", "soil_moisture_percent": 54.8},
                    {"day": "2026-04-25", "soil_moisture_percent": 56.1},
                ],
                "summary": {
                    "days": 2,
                    "latest_soil_moisture_percent": 56.1,
                    "average_soil_moisture_percent": 55.45,
                    "min_soil_moisture_percent": 54.8,
                    "max_soil_moisture_percent": 56.1,
                    "trend_delta_percent": 1.3,
                },
            },
            "warnings": [],
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
    monkeypatch.setattr(api_main.app.state, "analytics_tracker", fake_orchestrator.website_analytics_tracker)
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


def test_subdomain_health_shares_cookie_domain_and_allows_root_origin(monkeypatch):
    fake_orchestrator = FakeOrchestrator()
    monkeypatch.setattr(api_main, "orchestrator", fake_orchestrator)
    monkeypatch.setattr(api_main.app.state, "orchestrator", fake_orchestrator)

    with TestClient(api_main.app, base_url="https://api.deltaplant.ai") as client:
        response = client.get("/api/health", headers={"Origin": "https://deltaplant.ai"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://deltaplant.ai"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("Domain=.deltaplant.ai" in header for header in set_cookie_headers)


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


def test_nasa_only_returns_dashboard_payload(nasa_client):
    client, _ = nasa_client
    client.get("/api/health")

    response = client.post(
        "/api/nisar/nasa-only",
        json={
            "geo_data": {"type": "circle", "center": {"lat": 45.46, "lng": 9.19}, "radius": 50.0},
            "date_range": {"start": "2026-04-24", "end": "2026-04-30"},
            "user_token": "dp_user_token_1234567890",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "nasa-only"
    assert payload["dashboard"]["summary"]["days"] == 2
    assert payload["dashboard"]["soil_moisture_last_7_days"][0]["soil_moisture_percent"] == 54.8


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


def test_cookie_accept_export_delete_and_reject_flow(nasa_client):
    client, _ = nasa_client
    user_token = "dp_user_token_1234567890"
    client.get("/api/health")
    csrf_token = client.cookies["deltaplant_csrf"]

    accept_response = client.post(
        "/api/cookies/accept-all",
        headers={"X-CSRF-Token": csrf_token},
        json={"user_token": user_token},
    )

    assert accept_response.status_code == 200
    accepted_categories = accept_response.json()["categories"]
    assert accepted_categories["analytics"] is True
    assert accepted_categories["maps"] is True
    assert accepted_categories["voice"] is True
    assert accepted_categories["llm"] is True

    export_response = client.get(
        f"/api/privacy/export/{user_token}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert export_response.status_code == 200
    exported_categories = export_response.json()["categories"]
    assert exported_categories["voice"] is True
    assert exported_categories["llm"] is True

    delete_response = client.delete(
        f"/api/privacy/delete/{user_token}",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    status_after_delete = client.get(f"/api/privacy/consent-status?user_token={user_token}")

    assert status_after_delete.status_code == 200
    deleted_categories = status_after_delete.json()["categories"]
    assert deleted_categories["necessary"] is True
    assert deleted_categories["analytics"] is False
    assert deleted_categories["maps"] is False
    assert deleted_categories["voice"] is False
    assert deleted_categories["llm"] is False

    reject_response = client.post(
        "/api/cookies/reject-all",
        headers={"X-CSRF-Token": csrf_token},
        json={"user_token": user_token},
    )

    assert reject_response.status_code == 200
    rejected_categories = reject_response.json()["categories"]
    assert rejected_categories["necessary"] is True
    assert rejected_categories["analytics"] is False
    assert rejected_categories["maps"] is False
    assert rejected_categories["voice"] is False
    assert rejected_categories["llm"] is False


def test_analytics_event_requires_consent_and_is_recorded(nasa_client):
    client, fake_orchestrator = nasa_client
    user_token = "dp_user_token_1234567890"
    client.get("/api/health")

    denied = client.post(
        "/api/analytics/events",
        json={
            "user_token": user_token,
            "event_type": "page_view",
            "page_path": "/",
            "page_title": "DELTA Plant",
            "event_data": {"utm_source": "github"},
        },
    )
    assert denied.status_code == 403

    client.cookies.set(
        "deltaplant_consent",
        json.dumps({"necessary": True, "analytics": True, "maps": False, "voice": False, "llm": False}),
    )

    accepted = client.post(
        "/api/analytics/events",
        json={
            "user_token": user_token,
            "event_type": "cta_click",
            "event_label": "hero_open_bot",
            "page_path": "/?utm_source=github",
            "page_title": "DELTA Plant",
            "referrer": "https://github.com/proctor81/delta-plant",
            "device_type": "desktop",
            "language": "en-US",
            "event_data": {"utm_source": "github", "cta": "open_bot"},
        },
    )

    assert accepted.status_code == 202
    payload = accepted.json()
    assert payload["accepted"] is True
    assert payload["event_type"] == "cta_click"
    assert fake_orchestrator.website_analytics_tracker.events[-1]["event_label"] == "hero_open_bot"
    assert fake_orchestrator.website_analytics_tracker.events[-1]["session_id"]


def test_cookie_validator_accepts_urlencoded_browser_cookie():
    consent_manager = FakeConsentManager()
    validator = CookieValidator(consent_manager)
    user_token = "dp_user_token_1234567890"

    consent_manager.grant_consent(
        user_token,
        {"analytics": True, "maps": False, "voice": False, "llm": False},
    )
    encoded_cookie = quote(
        json.dumps(
            {"necessary": True, "analytics": True, "maps": False, "voice": False, "llm": False},
            separators=(",", ":"),
        )
    )

    merged = validator.merged_consent(user_token, encoded_cookie)

    assert merged["analytics"] is True
    assert validator.feature_allowed(user_token, "analytics", encoded_cookie) is True


def test_admin_analytics_report_requires_admin_bearer_scope(nasa_client):
    client, fake_orchestrator = nasa_client

    denied = client.get("/api/analytics/report")

    assert denied.status_code == 401

    allowed_token = api_main.create_session_token(
        {
            "sub": "delta-admin",
            "scope": "admin:analytics:read",
            "iss": "delta-admin-panel",
            "iat": 1780891200,
            "exp": 4102444800,
        }
    )
    allowed = client.get(
        "/api/analytics/report?days=7&recent_limit=5",
        headers={"Authorization": f"Bearer {allowed_token}"},
    )

    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["report_source"] == "remote_api"
    assert payload["totals"]["total_events"] == 3
    assert fake_orchestrator.website_analytics_tracker.report_calls[-1] == {"days": 7, "recent_limit": 5}

    wrong_scope_token = api_main.create_session_token(
        {
            "sub": "delta-admin",
            "scope": "admin:other",
            "iss": "delta-admin-panel",
            "iat": 1780891200,
            "exp": 4102444800,
        }
    )
    forbidden = client.get(
        "/api/analytics/report",
        headers={"Authorization": f"Bearer {wrong_scope_token}"},
    )

    assert forbidden.status_code == 403


def test_area_analysis_pdf_token_allows_positive_download_with_filename(nasa_client):
    client, _ = nasa_client
    user_token = "dp_user_token_1234567890"
    client.get("/api/health")
    client.cookies.set(
        "deltaplant_consent",
        json.dumps({"necessary": True, "llm": True, "voice": False, "maps": False, "analytics": False}),
    )

    analysis_response = client.post(
        "/api/nisar/area-analysis",
        json={
            "geo_data": {"type": "circle", "center": {"lat": 45.46, "lng": 9.19}, "radius": 250.0},
            "date_range": {"start": "2026-04-01", "end": "2026-04-30"},
            "user_token": user_token,
            "crop_answers": ["herbaceous"],
        },
    )

    assert analysis_response.status_code == 200
    pdf_token = analysis_response.json()["pdf_tokens"]["farmer"]

    pdf_response = client.get(f"/api/nisar/pdf/{pdf_token}")

    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.headers["content-disposition"] == 'attachment; filename="report.pdf"'
    assert pdf_response.content == b"%PDF-1.4 fake pdf"