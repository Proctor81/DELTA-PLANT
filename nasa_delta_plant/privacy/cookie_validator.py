"""Cookie and consent category validation helpers."""

from __future__ import annotations

import json
from typing import Any

from nasa_delta_plant.privacy.consent_manager import ConsentManager, DEFAULT_CONSENT


FEATURE_CATEGORY_MAP = {
    "analytics": "analytics",
    "llm": "llm",
    "voice": "voice",
    "maps": "maps",
    "pdf": "necessary",
    "api": "necessary",
}


class CookieValidator:
    def __init__(self, consent_manager: ConsentManager) -> None:
        self.consent_manager = consent_manager

    @staticmethod
    def parse_cookie_payload(cookie_value: str | None) -> dict[str, bool]:
        if not cookie_value:
            return dict(DEFAULT_CONSENT)
        try:
            parsed = json.loads(cookie_value)
        except json.JSONDecodeError:
            return dict(DEFAULT_CONSENT)
        return {**DEFAULT_CONSENT, **{key: bool(value) for key, value in parsed.items()}}

    def merged_consent(self, user_token: str, cookie_value: str | None) -> dict[str, bool]:
        stored = self.consent_manager.get_status(user_token).get("categories", DEFAULT_CONSENT)
        cookie = self.parse_cookie_payload(cookie_value)
        merged = dict(DEFAULT_CONSENT)
        for category in merged:
            if category == "necessary":
                merged[category] = True
                continue
            stored_value = bool(stored.get(category, False))
            cookie_value_present = cookie_value is not None and category in cookie
            cookie_choice = bool(cookie.get(category, False)) if cookie_value_present else True
            merged[category] = stored_value and cookie_choice
        return merged

    def feature_allowed(self, user_token: str, feature: str, cookie_value: str | None) -> bool:
        category = FEATURE_CATEGORY_MAP.get(feature, "necessary")
        consent = self.merged_consent(user_token, cookie_value)
        return bool(consent.get(category, False)) if category != "necessary" else True
