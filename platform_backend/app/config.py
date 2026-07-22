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
    max_test_package_upload_bytes: int
    max_test_package_entries: int
    max_test_package_uncompressed_bytes: int
    max_test_package_single_file_bytes: int


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
        max_test_package_upload_bytes=int(
            os.getenv("PLATFORM_MAX_TEST_PACKAGE_UPLOAD_BYTES", str(32 * 1024 * 1024))
        ),
        max_test_package_entries=int(os.getenv("PLATFORM_MAX_TEST_PACKAGE_ENTRIES", "100")),
        max_test_package_uncompressed_bytes=int(
            os.getenv("PLATFORM_MAX_TEST_PACKAGE_UNCOMPRESSED_BYTES", str(64 * 1024 * 1024))
        ),
        max_test_package_single_file_bytes=int(
            os.getenv("PLATFORM_MAX_TEST_PACKAGE_SINGLE_FILE_BYTES", str(20 * 1024 * 1024))
        ),
    )
