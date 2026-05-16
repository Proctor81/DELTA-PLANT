"""Authenticated Earthdata session helpers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from nasa_delta_plant.config import Settings, get_settings


@dataclass(slots=True)
class EarthdataAuthState:
    authenticated_at: float = 0.0
    refresh_interval_seconds: int = 45 * 60

    def expired(self) -> bool:
        return (time.monotonic() - self.authenticated_at) >= self.refresh_interval_seconds


class EarthdataSession:
    """Persistent authenticated session for NASA Earthdata URS."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.RLock()
        self._state = EarthdataAuthState()
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.auth = HTTPBasicAuth(
            self.settings.earthdata_username,
            self.settings.earthdata_password.get_secret_value(),
        )
        session.headers.update(
            {
                "User-Agent": "DeltaPlant-NASA-Pipeline/1.0",
                "Accept": "application/json,application/xml,text/plain,*/*",
            }
        )
        return session

    def _authenticate(self, force: bool = False) -> None:
        with self._lock:
            if not force and not self._state.expired() and self._state.authenticated_at > 0:
                return

            self._session = self._build_session()
            response = self._session.get(
                self.settings.earthdata_base_url,
                allow_redirects=True,
                timeout=30,
            )
            if response.status_code >= 500:
                response.raise_for_status()
            self._state.authenticated_at = time.monotonic()

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self._authenticate()
        response = self._session.request(method=method.upper(), url=url, timeout=60, **kwargs)
        if response.status_code == 401:
            self._authenticate(force=True)
            response = self._session.request(method=method.upper(), url=url, timeout=60, **kwargs)
        response.raise_for_status()
        return response

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("HEAD", url, **kwargs)

    def download_bytes(self, url: str, **kwargs: Any) -> bytes:
        response = self.get(url, **kwargs)
        return response.content
