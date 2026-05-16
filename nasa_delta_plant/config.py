"""Settings for the NASA DeltaPlant pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent


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

    @field_validator("pdf_temp_dir", mode="before")
    @classmethod
    def _normalize_pdf_dir(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value
        return Path(str(value)).expanduser()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance and ensure temp dir exists."""

    settings = Settings()
    settings.pdf_temp_dir.mkdir(parents=True, exist_ok=True)
    return settings