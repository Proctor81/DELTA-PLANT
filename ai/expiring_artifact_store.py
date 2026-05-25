from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from nasa_delta_plant.privacy import RetentionPolicy


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