"""Privacy-safe first-party website analytics storage and summaries."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from nasa_delta_plant.config import Settings, get_settings
from nasa_delta_plant.privacy.consent_manager import ConsentManager
from nasa_delta_plant.privacy.retention_policy import RetentionPolicy


ALLOWED_EVENT_TYPES = {
    "page_view",
    "session_start",
    "page_exit",
    "cta_click",
    "outbound_click",
    "hero_dashboard_run",
    "contact_submit",
    "privacy_update",
    "language_change",
}


class WebsiteAnalyticsTracker:
    """SQLite-backed first-party analytics with anonymous identifiers only."""

    def __init__(
        self,
        consent_manager: ConsentManager | None = None,
        settings: Settings | None = None,
        storage_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.consent_manager = consent_manager
        self.retention = RetentionPolicy()

        if storage_path is not None:
            self.storage_path = Path(storage_path)
        else:
            resolved_settings = settings or get_settings()
            self.settings = resolved_settings
            self.storage_path = resolved_settings.website_analytics_storage_path
            if self.consent_manager is None:
                self.consent_manager = ConsentManager(settings=resolved_settings)

        self._lock = threading.RLock()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.storage_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS website_analytics_events (
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
                );
                CREATE INDEX IF NOT EXISTS idx_website_analytics_created_at
                    ON website_analytics_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_website_analytics_event_type
                    ON website_analytics_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_website_analytics_page_path
                    ON website_analytics_events(page_path);
                """
            )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _clamp_text(value: Any, max_length: int = 255) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized[:max_length]

    @staticmethod
    def _normalize_event_type(value: Any) -> str:
        normalized = str(value or "page_view").strip().lower().replace("-", "_")
        return normalized if normalized in ALLOWED_EVENT_TYPES else "page_view"

    @staticmethod
    def _normalize_path(value: Any) -> str:
        raw = str(value or "/").strip()
        if not raw:
            return "/"
        parsed = urlparse(raw)
        path = parsed.path or raw
        if not path.startswith("/"):
            path = f"/{path}"
        return path[:255]

    @staticmethod
    def _normalize_referrer_host(referrer: Any) -> str | None:
        normalized = str(referrer or "").strip()
        if not normalized:
            return None
        parsed = urlparse(normalized)
        host = parsed.netloc or parsed.path
        return host[:255] if host else None

    @staticmethod
    def _sanitize_metadata(data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            return {}

        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            normalized_key = str(key).strip().lower().replace(" ", "_")[:64]
            if not normalized_key:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[normalized_key] = value if not isinstance(value, str) else value[:240]
                continue
            if isinstance(value, (list, tuple)):
                sanitized[normalized_key] = [str(item)[:120] for item in value[:12]]
                continue
            sanitized[normalized_key] = str(value)[:240]
        return sanitized

    @staticmethod
    def _extract_utm_values(page_path: str, metadata: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        source = metadata.get("utm_source")
        medium = metadata.get("utm_medium")
        campaign = metadata.get("utm_campaign")
        if source or medium or campaign:
            return (
                WebsiteAnalyticsTracker._clamp_text(source, 80),
                WebsiteAnalyticsTracker._clamp_text(medium, 80),
                WebsiteAnalyticsTracker._clamp_text(campaign, 80),
            )

        parsed = urlparse(page_path)
        query = parse_qs(parsed.query)
        return (
            WebsiteAnalyticsTracker._clamp_text((query.get("utm_source") or [None])[0], 80),
            WebsiteAnalyticsTracker._clamp_text((query.get("utm_medium") or [None])[0], 80),
            WebsiteAnalyticsTracker._clamp_text((query.get("utm_campaign") or [None])[0], 80),
        )

    def purge_expired(self) -> int:
        cutoff = self.retention.analytics_cutoff().isoformat()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM website_analytics_events WHERE created_at < ?",
                (cutoff,),
            )
            return cursor.rowcount or 0

    def record_event(self, payload: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
        if self.consent_manager is None:
            raise RuntimeError("Consent manager required to record analytics events.")

        self.purge_expired()

        now = self._now()
        event_type = self._normalize_event_type(payload.get("event_type"))
        raw_page_path = str(payload.get("page_path") or "/")
        page_path = self._normalize_path(raw_page_path)
        metadata = self._sanitize_metadata(payload.get("event_data"))
        utm_source, utm_medium, utm_campaign = self._extract_utm_values(raw_page_path, metadata)
        visitor_hash = self.consent_manager.hash_identifier(str(payload.get("user_token")))
        resolved_session = str(session_id or payload.get("session_id") or visitor_hash[:24])
        session_hash = self.consent_manager.hash_identifier(resolved_session)
        engaged_seconds = payload.get("engaged_seconds", metadata.get("engaged_seconds"))
        try:
            engaged_seconds_value = max(float(engaged_seconds), 0.0)
        except (TypeError, ValueError):
            engaged_seconds_value = None

        record = {
            "created_at": now.isoformat(),
            "day": now.strftime("%Y-%m-%d"),
            "event_type": event_type,
            "event_label": self._clamp_text(payload.get("event_label") or metadata.get("label") or metadata.get("name"), 96),
            "page_path": page_path[:255],
            "page_title": self._clamp_text(payload.get("page_title"), 160),
            "visitor_hash": visitor_hash,
            "session_hash": session_hash,
            "referrer_host": self._normalize_referrer_host(payload.get("referrer")),
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "language": self._clamp_text(payload.get("language"), 24),
            "timezone": self._clamp_text(payload.get("timezone"), 64),
            "device_type": self._clamp_text(payload.get("device_type"), 24),
            "viewport": self._clamp_text(payload.get("viewport"), 32),
            "screen": self._clamp_text(payload.get("screen"), 32),
            "engaged_seconds": engaged_seconds_value,
            "metadata_json": json.dumps(metadata, ensure_ascii=True, separators=(",", ":")),
        }

        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO website_analytics_events (
                    created_at, day, event_type, event_label, page_path, page_title,
                    visitor_hash, session_hash, referrer_host, utm_source, utm_medium,
                    utm_campaign, language, timezone, device_type, viewport, screen,
                    engaged_seconds, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["created_at"],
                    record["day"],
                    record["event_type"],
                    record["event_label"],
                    record["page_path"],
                    record["page_title"],
                    record["visitor_hash"],
                    record["session_hash"],
                    record["referrer_host"],
                    record["utm_source"],
                    record["utm_medium"],
                    record["utm_campaign"],
                    record["language"],
                    record["timezone"],
                    record["device_type"],
                    record["viewport"],
                    record["screen"],
                    record["engaged_seconds"],
                    record["metadata_json"],
                ),
            )
            event_id = cursor.lastrowid

        return {
            "accepted": True,
            "event_id": event_id,
            "event_type": event_type,
            "page_path": record["page_path"],
            "created_at": record["created_at"],
        }

    @staticmethod
    def _rows_to_pairs(rows: list[sqlite3.Row], key: str, value: str = "count") -> list[dict[str, Any]]:
        return [{key: row[key], value: row[value]} for row in rows if row[key]]

    def build_report(self, days: int = 30, recent_limit: int = 12) -> dict[str, Any]:
        days = max(1, min(int(days), 365))
        since_timestamp = (self._now() - timedelta(days=days)).isoformat()

        with self._lock, self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT visitor_hash) AS unique_visitors,
                    COUNT(DISTINCT session_hash) AS unique_sessions,
                    SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS page_views,
                    SUM(CASE WHEN event_type = 'session_start' THEN 1 ELSE 0 END) AS session_starts,
                    SUM(CASE WHEN event_type = 'cta_click' THEN 1 ELSE 0 END) AS cta_clicks,
                    SUM(CASE WHEN event_type = 'outbound_click' THEN 1 ELSE 0 END) AS outbound_clicks,
                    SUM(CASE WHEN event_type = 'hero_dashboard_run' THEN 1 ELSE 0 END) AS hero_dashboard_runs,
                    SUM(CASE WHEN event_type = 'contact_submit' THEN 1 ELSE 0 END) AS contact_submissions,
                    AVG(CASE WHEN event_type = 'page_exit' THEN engaged_seconds END) AS avg_engagement_seconds
                FROM website_analytics_events
                WHERE created_at >= ?
                """,
                (since_timestamp,),
            ).fetchone()

            event_breakdown = connection.execute(
                """
                SELECT event_type, COUNT(*) AS count
                FROM website_analytics_events
                WHERE created_at >= ?
                GROUP BY event_type
                ORDER BY count DESC, event_type ASC
                """,
                (since_timestamp,),
            ).fetchall()

            top_pages = connection.execute(
                """
                SELECT page_path, COUNT(*) AS count
                FROM website_analytics_events
                WHERE created_at >= ? AND event_type = 'page_view'
                GROUP BY page_path
                ORDER BY count DESC, page_path ASC
                LIMIT 10
                """,
                (since_timestamp,),
            ).fetchall()

            top_referrers = connection.execute(
                """
                SELECT referrer_host, COUNT(*) AS count
                FROM website_analytics_events
                WHERE created_at >= ? AND referrer_host IS NOT NULL AND referrer_host != ''
                GROUP BY referrer_host
                ORDER BY count DESC, referrer_host ASC
                LIMIT 10
                """,
                (since_timestamp,),
            ).fetchall()

            top_campaigns = connection.execute(
                """
                SELECT utm_campaign, COUNT(*) AS count
                FROM website_analytics_events
                WHERE created_at >= ? AND utm_campaign IS NOT NULL AND utm_campaign != ''
                GROUP BY utm_campaign
                ORDER BY count DESC, utm_campaign ASC
                LIMIT 10
                """,
                (since_timestamp,),
            ).fetchall()

            device_breakdown = connection.execute(
                """
                SELECT device_type, COUNT(*) AS count
                FROM website_analytics_events
                WHERE created_at >= ? AND device_type IS NOT NULL AND device_type != ''
                GROUP BY device_type
                ORDER BY count DESC, device_type ASC
                """,
                (since_timestamp,),
            ).fetchall()

            language_breakdown = connection.execute(
                """
                SELECT language, COUNT(*) AS count
                FROM website_analytics_events
                WHERE created_at >= ? AND language IS NOT NULL AND language != ''
                GROUP BY language
                ORDER BY count DESC, language ASC
                LIMIT 10
                """,
                (since_timestamp,),
            ).fetchall()

            daily = connection.execute(
                """
                SELECT day, COUNT(*) AS events, COUNT(DISTINCT visitor_hash) AS visitors
                FROM website_analytics_events
                WHERE created_at >= ?
                GROUP BY day
                ORDER BY day DESC
                LIMIT 30
                """,
                (since_timestamp,),
            ).fetchall()

            recent = connection.execute(
                """
                SELECT created_at, event_type, event_label, page_path, referrer_host, device_type, language, engaged_seconds
                FROM website_analytics_events
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (since_timestamp, recent_limit),
            ).fetchall()

        total_events = int(totals["total_events"] or 0)
        consent_overview = None
        if self.consent_manager is not None:
            try:
                store = self.consent_manager._load_store()  # noqa: SLF001
                consent_overview = {
                    "records": len(store),
                    "analytics_enabled": sum(
                        1
                        for snapshot in store.values()
                        if isinstance(snapshot, dict) and bool((snapshot.get("categories") or {}).get("analytics"))
                    ),
                }
            except Exception:
                consent_overview = None

        return {
            "window_days": days,
            "generated_at": self._now().isoformat(),
            "storage_path": str(self.storage_path),
            "totals": {
                "total_events": total_events,
                "unique_visitors": int(totals["unique_visitors"] or 0),
                "unique_sessions": int(totals["unique_sessions"] or 0),
                "page_views": int(totals["page_views"] or 0),
                "session_starts": int(totals["session_starts"] or 0),
                "cta_clicks": int(totals["cta_clicks"] or 0),
                "outbound_clicks": int(totals["outbound_clicks"] or 0),
                "hero_dashboard_runs": int(totals["hero_dashboard_runs"] or 0),
                "contact_submissions": int(totals["contact_submissions"] or 0),
                "avg_engagement_seconds": round(float(totals["avg_engagement_seconds"] or 0.0), 2),
            },
            "consent_overview": consent_overview,
            "event_breakdown": self._rows_to_pairs(event_breakdown, "event_type"),
            "top_pages": self._rows_to_pairs(top_pages, "page_path"),
            "top_referrers": self._rows_to_pairs(top_referrers, "referrer_host"),
            "top_campaigns": self._rows_to_pairs(top_campaigns, "utm_campaign"),
            "device_breakdown": self._rows_to_pairs(device_breakdown, "device_type"),
            "language_breakdown": self._rows_to_pairs(language_breakdown, "language"),
            "daily": [
                {
                    "day": row["day"],
                    "events": row["events"],
                    "visitors": row["visitors"],
                }
                for row in daily
            ],
            "recent_events": [
                {
                    "created_at": row["created_at"],
                    "event_type": row["event_type"],
                    "event_label": row["event_label"],
                    "page_path": row["page_path"],
                    "referrer_host": row["referrer_host"],
                    "device_type": row["device_type"],
                    "language": row["language"],
                    "engaged_seconds": row["engaged_seconds"],
                }
                for row in recent
            ],
        }

    def export_report(self, destination: Path, days: int = 30) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.build_report(days=days), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination