"""Retention and purge helpers for privacy-sensitive artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    consent_retention_days: int = 36 * 30
    audit_retention_days: int = 30
    runtime_pdf_ttl_minutes: int = 60

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def consent_cutoff(self) -> datetime:
        return self.now() - timedelta(days=self.consent_retention_days)

    def audit_cutoff(self) -> datetime:
        return self.now() - timedelta(days=self.audit_retention_days)

    def pdf_expiry(self) -> datetime:
        return self.now() + timedelta(minutes=self.runtime_pdf_ttl_minutes)

    def is_expired(self, timestamp: datetime, ttl_minutes: int | None = None) -> bool:
        if ttl_minutes is not None:
            return timestamp < (self.now() - timedelta(minutes=ttl_minutes))
        return timestamp < self.consent_cutoff()

    def purge_directory(self, directory: Path, older_than: timedelta) -> int:
        if not directory.exists():
            return 0
        cutoff = self.now() - older_than
        removed = 0
        for child in directory.iterdir():
            if not child.is_file():
                continue
            modified = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                child.unlink(missing_ok=True)
                removed += 1
        return removed