"""Settings for the NASA DeltaPlant pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CORS_ALLOW_ORIGINS = [
    "https://deltaplant.ai",
    "https://www.deltaplant.ai",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
DEFAULT_ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "deltaplant.ai",
    "*.deltaplant.ai",
]


class Settings(BaseSettings):
    """Runtime configuration loaded from the project .env file."""

    earthdata_username: str = Field(alias="EARTHDATA_USERNAME")
    earthdata_password: SecretStr = Field(alias="EARTHDATA_PASSWORD")
    earthdata_base_url: str = Field(alias="EARTHDATA_BASE_URL")

    copernicus_username: str = Field(alias="COPERNICUS_USERNAME")
    copernicus_password: SecretStr = Field(alias="COPERNICUS_PASSWORD")
    copernicus_base_url: str = Field(alias="COPERNICUS_BASE_URL")

    nasa_power_base_url: str = Field(alias="NASA_POWER_BASE_URL")

    secret_key: SecretStr = Field(alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    pdf_temp_dir: Path = Field(default=Path("/tmp/deltaplant"), alias="PDF_TEMP_DIR")
    privacy_storage_path: Path = Field(
        default=ROOT_DIR / "data" / "privacy" / "consents.enc",
        alias="PRIVACY_STORAGE_PATH",
    )
    privacy_log_dir: Path = Field(
        default=ROOT_DIR / "logs" / "privacy",
        alias="PRIVACY_LOG_DIR",
    )
    cors_allow_origins: Annotated[
        list[str],
        NoDecode,
    ] = Field(default_factory=lambda: list(DEFAULT_CORS_ALLOW_ORIGINS), alias="CORS_ALLOW_ORIGINS")
    allowed_hosts: Annotated[
        list[str],
        NoDecode,
    ] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_HOSTS), alias="ALLOWED_HOSTS")
    cookie_domain: str | None = Field(default=None, alias="COOKIE_DOMAIN")
    cookie_samesite: str = Field(default="strict", alias="COOKIE_SAMESITE")

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "earthdata_base_url",
        "copernicus_base_url",
        "nasa_power_base_url",
        mode="before",
    )
    @classmethod
    def _strip_url(cls, value: str) -> str:
        return str(value).strip().rstrip("/")

    @field_validator("cors_allow_origins", "allowed_hosts", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]

    @field_validator("pdf_temp_dir", "privacy_storage_path", "privacy_log_dir", mode="before")
    @classmethod
    def _normalize_pdf_dir(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value
        return Path(str(value)).expanduser()

    @field_validator("cookie_domain", mode="before")
    @classmethod
    def _normalize_cookie_domain(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().strip(".")
        if not normalized or normalized in {"localhost", "127.0.0.1"}:
            return None
        return f".{normalized}"

    @field_validator("cookie_samesite", mode="before")
    @classmethod
    def _normalize_cookie_samesite(cls, value: object) -> str:
        normalized = str(value or "strict").strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of lax, strict, or none")
        return normalized


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance and ensure temp dir exists."""

    settings = Settings()
    settings.pdf_temp_dir.mkdir(parents=True, exist_ok=True)
    settings.privacy_storage_path.parent.mkdir(parents=True, exist_ok=True)
    settings.privacy_log_dir.mkdir(parents=True, exist_ok=True)
    return settings