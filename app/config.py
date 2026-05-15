from functools import lru_cache
import os
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    app_name: str = "BFB Membership Bot"
    database_url: str = "sqlite:///./data/app.db"
    allow_sqlite_on_railway: bool = False

    bot_token: str | None = None
    bot_username: str | None = None
    webapp_url: str = "http://localhost:8000"
    public_base_url: str | None = None
    telegram_webhook_secret: str = "change-me"
    require_telegram_auth: bool = False

    admin_telegram_ids: Annotated[list[int], NoDecode] = []
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

    @field_validator("database_url", mode="before")
    @classmethod
    def default_empty_database_url(cls, value: object) -> str:
        railway_runtime = any(
            os.getenv(name)
            for name in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")
        )
        if railway_runtime and value in (None, "", "sqlite:///./data/app.db"):
            mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data").rstrip("/") or "/data"
            return f"sqlite:///{mount_path}/app.db"
        if value in (None, ""):
            return "sqlite:///./data/app.db"
        return str(value)

    @property
    def is_railway_runtime(self) -> bool:
        return any(
            os.getenv(name)
            for name in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")
        )

    @property
    def is_sqlite_database(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_persistent_railway_sqlite(self) -> bool:
        if not (self.is_railway_runtime and self.is_sqlite_database):
            return False
        mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data").rstrip("/") or "/data"
        return self.database_url.startswith(f"sqlite:///{mount_path}/")

    @property
    def database_storage_label(self) -> str:
        if self.is_persistent_railway_sqlite:
            return "sqlite_on_railway_volume"
        if self.is_sqlite_database:
            return "sqlite"
        return "postgres"

    def database_safety_error(self) -> str | None:
        if (
            self.is_railway_runtime
            and self.is_sqlite_database
            and not self.is_persistent_railway_sqlite
            and not self.allow_sqlite_on_railway
        ):
            return (
                "Unsafe Railway database configuration: DATABASE_URL is empty or points to SQLite. "
                "Set DATABASE_URL=${{Postgres.DATABASE_URL}} or use SQLite on the Railway Volume. "
                "Writes are blocked to protect member applications from being saved to temporary storage."
            )
        return None

    def database_url_diagnostics(self) -> dict[str, object]:
        raw_value = os.getenv("DATABASE_URL")
        configured = self.database_url

        def describe(value: str | None) -> dict[str, object]:
            if value is None:
                return {"present": False, "length": 0, "kind": "missing", "hasWhitespace": False}
            stripped = value.strip()
            if not stripped:
                return {"present": True, "length": len(value), "kind": "empty", "hasWhitespace": value != stripped}
            if stripped.startswith(("postgresql://", "postgres://")):
                kind = "postgres"
            elif stripped.startswith("sqlite"):
                mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data").rstrip("/") or "/data"
                kind = "sqlite_volume" if stripped.startswith(f"sqlite:///{mount_path}/") else "sqlite"
            elif stripped.startswith("${{"):
                kind = "unresolved_reference"
            else:
                kind = stripped.split(":", 1)[0] if ":" in stripped else "unknown"
            return {
                "present": True,
                "length": len(value),
                "kind": kind,
                "hasWhitespace": value != stripped,
            }

        return {
            "railwayRuntime": self.is_railway_runtime,
            "envDatabaseUrl": describe(raw_value),
            "settingsDatabaseUrl": describe(configured),
        }

    def validate_database_safety(self) -> None:
        error = self.database_safety_error()
        if error:
            raise RuntimeError(error)

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
