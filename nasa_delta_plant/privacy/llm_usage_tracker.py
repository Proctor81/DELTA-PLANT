"""Daily per-user LLM usage tracking with Redis fallback to in-memory state."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone

from nasa_delta_plant.privacy.consent_manager import ConsentManager


class LLMUsageTracker:
    DAILY_LIMIT = 1

    def __init__(self, consent_manager: ConsentManager) -> None:
        self.consent_manager = consent_manager
        self._lock = threading.RLock()
        self._memory_store: dict[str, int] = {}
        self._redis = None

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis  # type: ignore

                self._redis = redis.from_url(redis_url, decode_responses=True)
            except Exception:
                self._redis = None

    @staticmethod
    def _today_key() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _key(self, user_token: str) -> str:
        user_hash = self.consent_manager.hash_identifier(user_token)
        return f"llm:{self._today_key()}:{user_hash}"

    def remaining_calls(self, user_token: str) -> int:
        key = self._key(user_token)
        if self._redis is not None:
            value = int(self._redis.get(key) or 0)
            return max(self.DAILY_LIMIT - value, 0)
        with self._lock:
            self._purge_memory()
            return max(self.DAILY_LIMIT - self._memory_store.get(key, 0), 0)

    def try_consume(self, user_token: str) -> bool:
        key = self._key(user_token)
        if self._redis is not None:
            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            expires_at = datetime.combine(
                (datetime.now(timezone.utc) + timedelta(days=1)).date(),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            pipeline.expireat(key, expires_at)
            count, _ = pipeline.execute()
            return int(count) <= self.DAILY_LIMIT

        with self._lock:
            self._purge_memory()
            count = self._memory_store.get(key, 0) + 1
            self._memory_store[key] = count
            return count <= self.DAILY_LIMIT

    def _purge_memory(self) -> None:
        today_prefix = f"llm:{self._today_key()}:"
        expired = [key for key in self._memory_store if not key.startswith(today_prefix)]
        for key in expired:
            self._memory_store.pop(key, None)