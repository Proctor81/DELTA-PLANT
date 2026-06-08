import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import requests

from interface.admin import AdminPanel, _ROOT


def _create_analytics_db(storage_path: Path, created_at: str = "2026-06-08T11:15:00+00:00") -> None:
    with sqlite3.connect(str(storage_path)) as connection:
        connection.execute(
            """
            CREATE TABLE website_analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                day TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_label TEXT,
                page_path TEXT NOT NULL,
                page_title TEXT,
                visitor_hash TEXT NOT NULL,
                session_hash TEXT NOT NULL,
                referrer_host TEXT,
                utm_source TEXT,
                utm_medium TEXT,
                utm_campaign TEXT,
                language TEXT,
                timezone TEXT,
                device_type TEXT,
                viewport TEXT,
                screen TEXT,
                engaged_seconds REAL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO website_analytics_events (
                created_at, day, event_type, event_label, page_path, page_title,
                visitor_hash, session_hash, referrer_host, utm_source, utm_medium,
                utm_campaign, language, timezone, device_type, viewport, screen,
                engaged_seconds, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                "2026-06-08",
                "page_view",
                "debug",
                "/debug",
                "Debug",
                "visitor",
                "session",
                "github.com",
                "debug",
                None,
                None,
                "it-IT",
                "Europe/Rome",
                "desktop",
                "1920x1080",
                "1920x1080",
                None,
                "{}",
            ),
        )


def test_admin_monitor_prefers_configured_storage_path(monkeypatch, tmp_path):
    configured_path = tmp_path / "shared" / "website_events.sqlite"
    configured_path.parent.mkdir(parents=True)
    panel = AdminPanel(agent=None)

    monkeypatch.setattr(
        "nasa_delta_plant.config.get_settings",
        lambda: SimpleNamespace(website_analytics_storage_path=configured_path),
    )

    resolved_path, source = panel._resolve_website_analytics_storage_path()

    assert resolved_path == configured_path
    assert source == "settings"


def test_admin_monitor_falls_back_to_local_storage_path(monkeypatch):
    panel = AdminPanel(agent=None)

    def _raise_settings_error():
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr("nasa_delta_plant.config.get_settings", _raise_settings_error)

    resolved_path, source = panel._resolve_website_analytics_storage_path()

    assert resolved_path == _ROOT / "data" / "analytics" / "website_events.sqlite"
    assert source == "fallback"


def test_admin_monitor_storage_diagnostics_reads_local_counts(tmp_path):
    storage_path = tmp_path / "website_events.sqlite"
    _create_analytics_db(storage_path)
    panel = AdminPanel(agent=None)

    diagnostics = panel._website_analytics_storage_diagnostics(storage_path)

    assert diagnostics["exists"] is True
    assert diagnostics["size_bytes"] > 0
    assert diagnostics["total_events"] == 1
    assert diagnostics["latest_event_at"] == "2026-06-08T11:15:00+00:00"
    assert diagnostics["error"] is None


def test_admin_monitor_load_report_prefers_remote_when_authenticated(monkeypatch):
    panel = AdminPanel(agent=None)
    panel._admin_authenticated = True
    remote_report = {
        "totals": {"total_events": 9, "unique_visitors": 4, "unique_sessions": 4, "page_views": 7, "session_starts": 2, "cta_clicks": 0, "outbound_clicks": 0, "hero_dashboard_runs": 0, "contact_submissions": 0, "avg_engagement_seconds": 3.2},
        "recent_events": [],
    }
    tracker = Mock()
    monkeypatch.setattr(panel, "_fetch_remote_website_analytics_report", lambda days, recent_limit=15: (remote_report, None))

    report, source_name, warning = panel._load_website_analytics_report(tracker, days=7, recent_limit=5)

    assert report is remote_report
    assert source_name == "API pubblica"
    assert warning is None
    tracker.build_report.assert_not_called()


def test_admin_monitor_load_report_falls_back_to_local(monkeypatch):
    panel = AdminPanel(agent=None)
    panel._admin_authenticated = True
    tracker = Mock()
    tracker.build_report.return_value = {"totals": {"total_events": 1}, "recent_events": []}
    monkeypatch.setattr(panel, "_fetch_remote_website_analytics_report", lambda days, recent_limit=15: (None, "remote down"))

    report, source_name, warning = panel._load_website_analytics_report(tracker, days=30, recent_limit=15)

    assert report["report_source"] == "local_storage"
    assert source_name == "SQLite locale"
    assert warning == "remote down"
    tracker.build_report.assert_called_once_with(days=30, recent_limit=15)


def test_admin_remote_report_diagnostic_captures_http_rejection(monkeypatch):
    panel = AdminPanel(agent=None)
    panel._admin_authenticated = True

    class _Response:
        status_code = 404
        ok = False
        text = '{"detail":"Not Found"}'

        @staticmethod
        def json():
            return {"detail": "Not Found"}

    monkeypatch.setattr(panel, "_issue_admin_analytics_token", lambda lifetime_minutes=5: "token")
    monkeypatch.setattr("interface.admin.requests.get", lambda *args, **kwargs: _Response())

    diagnostic = panel._request_remote_website_analytics_report(days=30, recent_limit=5)

    assert diagnostic["ok"] is False
    assert diagnostic["token_available"] is True
    assert diagnostic["status_code"] == 404
    assert diagnostic["detail"] == "Not Found"
    assert "Report remoto rifiutato" in str(diagnostic["error"])


def test_admin_remote_report_diagnostic_captures_network_error(monkeypatch):
    panel = AdminPanel(agent=None)
    panel._admin_authenticated = True

    monkeypatch.setattr(panel, "_issue_admin_analytics_token", lambda lifetime_minutes=5: "token")

    def _raise_request_error(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr("interface.admin.requests.get", _raise_request_error)

    diagnostic = panel._request_remote_website_analytics_report(days=30, recent_limit=5)

    assert diagnostic["ok"] is False
    assert diagnostic["token_available"] is True
    assert diagnostic["status_code"] is None
    assert diagnostic["detail"] is None
    assert diagnostic["error"] == "Endpoint report remoto non raggiungibile: boom"