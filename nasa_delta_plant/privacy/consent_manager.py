"""Encrypted consent storage and GDPR user-right helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from nasa_delta_plant.config import ROOT_DIR, Settings, get_settings
from nasa_delta_plant.privacy.gdpr_logger import log_gdpr_event
from nasa_delta_plant.privacy.retention_policy import RetentionPolicy


DEFAULT_CONSENT = {
    "necessary": True,
    "analytics": False,
    "maps": False,
    "voice": False,
    "llm": False,
}


@dataclass(slots=True)
class ConsentSnapshot:
    user_token_hash: str
    categories: dict[str, bool]
    created_at: str
    updated_at: str
    revoked_at: str | None
    ip_hash: str | None
    history: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_token_hash": self.user_token_hash,
            "categories": self.categories,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revoked_at": self.revoked_at,
            "ip_hash": self.ip_hash,
            "history": self.history,
        }


class ConsentManager:
    """Encrypted filesystem-backed consent registry with hashed identifiers."""

    def __init__(self, settings: Settings | None = None, storage_path: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.retention = RetentionPolicy()
        self._lock = threading.RLock()
        self.storage_path = storage_path or self.settings.privacy_storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(self._derive_fernet_key(self.settings.secret_key.get_secret_value()))

    @staticmethod
    def _derive_fernet_key(secret: str) -> bytes:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def hash_identifier(self, value: str) -> str:
        return hashlib.sha256(f"delta-privacy:{self.settings.secret_key.get_secret_value()}:{value}".encode("utf-8")).hexdigest()

    def issue_csrf_token(self) -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def validate_csrf(cookie_token: str | None, header_token: str | None) -> bool:
        if not cookie_token or not header_token:
            return False
        return secrets.compare_digest(cookie_token, header_token)

    def grant_consent(
        self,
        user_token: str,
        categories: dict[str, bool],
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            store = self._load_store()
            user_hash = self.hash_identifier(user_token)
            ip_hash = self.hash_identifier(ip_address) if ip_address else None
            now = datetime.now(timezone.utc).isoformat()
            previous = store.get(user_hash)
            merged_categories = {**DEFAULT_CONSENT, **(previous or {}).get("categories", {}), **categories}
            merged_categories["necessary"] = True
            history = list((previous or {}).get("history", []))
            history.append({"action": "grant", "timestamp": now, "categories": merged_categories, "ip_hash": ip_hash})
            snapshot = ConsentSnapshot(
                user_token_hash=user_hash,
                categories=merged_categories,
                created_at=(previous or {}).get("created_at", now),
                updated_at=now,
                revoked_at=None,
                ip_hash=ip_hash,
                history=history,
            )
            store[user_hash] = snapshot.as_dict()
            self._save_store(store)
            log_gdpr_event("consent_granted", user_hash, ip_hash=ip_hash, details={"categories": merged_categories})
            return snapshot.as_dict()

    def revoke_consent(
        self,
        user_token: str,
        categories: list[str] | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            store = self._load_store()
            user_hash = self.hash_identifier(user_token)
            ip_hash = self.hash_identifier(ip_address) if ip_address else None
            existing = store.get(user_hash, {
                "user_token_hash": user_hash,
                "categories": dict(DEFAULT_CONSENT),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "revoked_at": None,
                "ip_hash": ip_hash,
                "history": [],
            })
            updated_categories = dict(existing.get("categories", DEFAULT_CONSENT))
            for category in categories or [key for key in DEFAULT_CONSENT if key != "necessary"]:
                updated_categories[category] = False
            now = datetime.now(timezone.utc).isoformat()
            history = list(existing.get("history", []))
            history.append({"action": "revoke", "timestamp": now, "categories": updated_categories, "ip_hash": ip_hash})
            existing.update(
                {
                    "categories": updated_categories,
                    "updated_at": now,
                    "revoked_at": now,
                    "ip_hash": ip_hash,
                    "history": history,
                }
            )
            store[user_hash] = existing
            self._save_store(store)
            log_gdpr_event("consent_revoked", user_hash, ip_hash=ip_hash, details={"categories": updated_categories})
            return existing

    def get_status(self, user_token: str) -> dict[str, Any]:
        store = self._load_store()
        user_hash = self.hash_identifier(user_token)
        snapshot = store.get(user_hash)
        if snapshot is None:
            now = datetime.now(timezone.utc).isoformat()
            return {
                "user_token_hash": user_hash,
                "categories": dict(DEFAULT_CONSENT),
                "created_at": now,
                "updated_at": now,
                "revoked_at": None,
                "ip_hash": None,
                "history": [],
            }
        return snapshot

    def export_user_data(self, user_token: str) -> dict[str, Any]:
        user_hash = self.hash_identifier(user_token)
        snapshot = self._load_store().get(user_hash)
        log_gdpr_event("data_export", user_hash)
        return snapshot or {"user_token_hash": user_hash, "categories": dict(DEFAULT_CONSENT), "history": []}

    def delete_user_data(self, user_token: str) -> bool:
        with self._lock:
            store = self._load_store()
            user_hash = self.hash_identifier(user_token)
            existed = user_hash in store
            if existed:
                del store[user_hash]
                self._save_store(store)
            log_gdpr_event("data_delete", user_hash, details={"deleted": existed})
            return existed

    def _load_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {}
        encrypted = self.storage_path.read_bytes()
        if not encrypted:
            return {}
        decrypted = self._fernet.decrypt(encrypted)
        payload = json.loads(decrypted.decode("utf-8"))
        cutoff = self.retention.consent_cutoff().isoformat()
        return {
            user_hash: record
            for user_hash, record in payload.items()
            if record.get("updated_at", cutoff) >= cutoff
        }

    def _save_store(self, store: dict[str, Any]) -> None:
        payload = json.dumps(store, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        encrypted = self._fernet.encrypt(payload)
        self.storage_path.write_bytes(encrypted)