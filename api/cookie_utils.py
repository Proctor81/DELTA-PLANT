"""Shared cookie helpers for NASA DeltaPlant API routes."""

from __future__ import annotations

from fastapi import Request

from nasa_delta_plant.config import get_settings


LOCAL_HOSTS = {"localhost", "127.0.0.1"}
SHARED_PARENT_DOMAIN = "deltaplant.ai"


def secure_cookie(request: Request) -> bool:
    hostname = request.url.hostname or ""
    return request.url.scheme == "https" and hostname not in LOCAL_HOSTS


def cookie_domain_for_request(request: Request) -> str | None:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    if settings.cookie_domain:
        return settings.cookie_domain

    hostname = (request.url.hostname or "").lower().strip(".")
    if hostname == SHARED_PARENT_DOMAIN or hostname.endswith(f".{SHARED_PARENT_DOMAIN}"):
        return f".{SHARED_PARENT_DOMAIN}"
    return None


def cookie_policy_for_request(request: Request) -> dict[str, object]:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    return {
        "domain": cookie_domain_for_request(request),
        "path": "/",
        "samesite": settings.cookie_samesite,
        "secure": secure_cookie(request),
    }