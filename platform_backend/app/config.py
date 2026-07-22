"""Environment-backed configuration for the minimal platform service."""

from dataclasses import dataclass
from functools import lru_cache
import os

from app import __version__


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    service_name: str
    version: str
    environment: str
    database_url: str
    max_upload_bytes: int
    max_import_rows: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("PLATFORM_APP_NAME", "Mumu Platform Backend"),
        service_name=os.getenv("PLATFORM_SERVICE_NAME", "platform-backend"),
        version=os.getenv("PLATFORM_VERSION", __version__),
        environment=os.getenv("PLATFORM_ENVIRONMENT", "development"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./platform.db"),
        max_upload_bytes=int(os.getenv("PLATFORM_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
        max_import_rows=int(os.getenv("PLATFORM_MAX_IMPORT_ROWS", "1000")),
    )
