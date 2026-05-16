from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
SERVICE_NAME = "proctor81-deltaplant-nasa-api"
CUSTOM_DOMAIN = "api.deltaplant.ai"
DEFAULT_HOSTNAME = f"{SERVICE_NAME}.onrender.com"
DNS_RECORD = {
    "type": "CNAME",
    "host": "api",
    "target": DEFAULT_HOSTNAME,
    "ttl": "3600",
}
RENDER_KEYS = [
    "EARTHDATA_USERNAME",
    "EARTHDATA_PASSWORD",
    "EARTHDATA_BASE_URL",
    "COPERNICUS_USERNAME",
    "COPERNICUS_PASSWORD",
    "COPERNICUS_BASE_URL",
    "NASA_POWER_BASE_URL",
    "SECRET_KEY",
    "JWT_ALGORITHM",
    "PDF_TEMP_DIR",
    "PRIVACY_STORAGE_PATH",
    "PRIVACY_LOG_DIR",
    "COOKIE_DOMAIN",
    "COOKIE_SAMESITE",
    "CORS_ALLOW_ORIGINS",
    "ALLOWED_HOSTS",
    "REDIS_URL",
]
SECRET_KEYS = {
    "EARTHDATA_PASSWORD",
    "COPERNICUS_PASSWORD",
    "SECRET_KEY",
    "REDIS_URL",
}
DEFAULT_VALUES = {
    "EARTHDATA_BASE_URL": "https://urs.earthdata.nasa.gov",
    "COPERNICUS_BASE_URL": "https://dataspace.copernicus.eu",
    "NASA_POWER_BASE_URL": "https://power.larc.nasa.gov/api/temporal/daily/point",
    "JWT_ALGORITHM": "HS256",
    "PDF_TEMP_DIR": "/var/lib/deltaplant/tmp",
    "PRIVACY_STORAGE_PATH": "/var/lib/deltaplant/privacy/consents.enc",
    "PRIVACY_LOG_DIR": "/var/lib/deltaplant/logs/privacy",
    "COOKIE_DOMAIN": ".deltaplant.ai",
    "COOKIE_SAMESITE": "strict",
    "CORS_ALLOW_ORIGINS": "https://deltaplant.ai,https://www.deltaplant.ai",
    "ALLOWED_HOSTS": "localhost,127.0.0.1,deltaplant.ai,*.deltaplant.ai",
}
REQUIRED_KEYS = {
    "EARTHDATA_USERNAME",
    "EARTHDATA_PASSWORD",
    "COPERNICUS_USERNAME",
    "COPERNICUS_PASSWORD",
    "SECRET_KEY",
}


def mask_secret(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def load_values() -> dict[str, str]:
    env_values = {key: value for key, value in dotenv_values(ENV_PATH).items() if value}
    merged = {**DEFAULT_VALUES, **env_values}
    for key in RENDER_KEYS:
        runtime_value = os.getenv(key)
        if runtime_value:
            merged[key] = runtime_value
    return merged


def render_lines(values: dict[str, str], reveal_secrets: bool) -> list[str]:
    lines = [
        "Render bundle",
        f"service_name={SERVICE_NAME}",
        f"custom_domain={CUSTOM_DOMAIN}",
        f"default_hostname={DEFAULT_HOSTNAME}",
        "",
        "DNS record",
        f"type={DNS_RECORD['type']}",
        f"host={DNS_RECORD['host']}",
        f"target={DNS_RECORD['target']}",
        f"ttl={DNS_RECORD['ttl']}",
        "",
        "Render env vars",
    ]
    for key in RENDER_KEYS:
        value = values.get(key, "")
        printable = value if reveal_secrets or key not in SECRET_KEYS else mask_secret(value)
        lines.append(f"{key}={printable or '<missing>'}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the exact Render and DNS cutover bundle for DELTA Plant.")
    parser.add_argument(
        "--reveal-secrets",
        action="store_true",
        help="Print secret values from .env or the current environment without masking.",
    )
    args = parser.parse_args()

    values = load_values()
    missing = [key for key in sorted(REQUIRED_KEYS) if not values.get(key)]
    print("\n".join(render_lines(values, reveal_secrets=args.reveal_secrets)))

    if missing:
        print("", file=sys.stderr)
        print(f"Missing required values: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())