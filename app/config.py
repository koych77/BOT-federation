from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BFB Membership Bot"
    database_url: str = "sqlite:///./data/app.db"

    bot_token: str | None = None
    bot_username: str | None = None
    webapp_url: str = "http://localhost:8000"
    public_base_url: str | None = None
    telegram_webhook_secret: str = "change-me"
    require_telegram_auth: bool = False

    admin_telegram_ids: list[int] = []
    admin_export_token: str | None = None

    membership_year: int = 2026
    entry_fee: float = 45.0
    membership_fee: float = 90.0
    currency: str = "BYN"

    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = 10
    storage_backend: str = "local"
    storage_endpoint_url: str | None = None
    storage_region: str = "auto"
    storage_bucket: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [int(item) for item in value]
        return [int(item.strip()) for item in str(value).split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def webhook_url(self) -> str | None:
        if not self.public_base_url:
            return None
        return f"{self.public_base_url.rstrip('/')}/telegram/webhook/{self.telegram_webhook_secret}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
