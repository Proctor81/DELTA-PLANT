"""Structured GDPR audit logging without personal data."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from nasa_delta_plant.config import ROOT_DIR
from nasa_delta_plant.privacy.retention_policy import RetentionPolicy


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        extra_payload = getattr(record, "privacy_payload", None)
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        return json.dumps(payload, ensure_ascii=True)


@lru_cache(maxsize=1)
def get_gdpr_logger() -> logging.Logger:
    log_dir = ROOT_DIR / "logs" / "privacy"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("nasa_delta_plant.gdpr")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = TimedRotatingFileHandler(
            filename=log_dir / "gdpr_audit.log",
            when="midnight",
            interval=1,
            backupCount=RetentionPolicy().audit_retention_days,
            encoding="utf-8",
            utc=True,
        )
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    return logger


def log_gdpr_event(
    action: str,
    user_token_hash: str,
    ip_hash: str | None = None,
    details: dict[str, Any] | None = None,
    legal_basis: str = "consent",
) -> None:
    logger = get_gdpr_logger()
    logger.info(
        action,
        extra={
            "privacy_payload": {
                "action": action,
                "user_token_hash": user_token_hash,
                "ip_hash": ip_hash,
                "legal_basis": legal_basis,
                "details": details or {},
            }
        },
    )