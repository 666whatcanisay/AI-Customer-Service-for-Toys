"""Environment-backed configuration for the minimal platform service."""

from dataclasses import dataclass
from functools import lru_cache
import os
from urllib.parse import urlsplit

from app import __version__


DEFAULT_CORS_ALLOWED_ORIGINS = "http://127.0.0.1:5173"


def parse_cors_allowed_origins(raw_value: str) -> tuple[str, ...]:
    """Parse and validate the explicit browser origins allowed to call C APIs."""

    origins: list[str] = []
    for raw_origin in raw_value.split(","):
        origin = raw_origin.strip()
        if not origin:
            continue
        if origin == "*":
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain the wildcard '*'")

        parsed = urlsplit(origin)
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError(f"CORS_ALLOWED_ORIGINS contains an invalid origin: {origin!r}") from exc

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in origin)
        ):
            raise ValueError(f"CORS_ALLOWED_ORIGINS contains an invalid origin: {origin!r}")

        normalized_origin = origin.removesuffix("/")
        if normalized_origin not in origins:
            origins.append(normalized_origin)

    if not origins:
        raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one explicit origin")
    return tuple(origins)


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    service_name: str
    version: str
    environment: str
    cors_allowed_origins: tuple[str, ...]
    database_url: str
    max_upload_bytes: int
    max_import_rows: int
    max_test_package_upload_bytes: int
    max_test_package_entries: int
    max_test_package_uncompressed_bytes: int
    max_test_package_single_file_bytes: int
    max_knowledge_material_upload_bytes: int
    knowledge_material_storage_dir: str
    ai_service_base_url: str
    ai_service_timeout_seconds: float
    iam_session_ttl_minutes: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("PLATFORM_APP_NAME", "Mumu Platform Backend"),
        service_name=os.getenv("PLATFORM_SERVICE_NAME", "platform-backend"),
        version=os.getenv("PLATFORM_VERSION", __version__),
        environment=os.getenv("PLATFORM_ENVIRONMENT", "development"),
        cors_allowed_origins=parse_cors_allowed_origins(
            os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ALLOWED_ORIGINS)
        ),
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
        max_knowledge_material_upload_bytes=int(
            os.getenv("PLATFORM_MAX_KNOWLEDGE_MATERIAL_UPLOAD_BYTES", str(5 * 1024 * 1024))
        ),
        knowledge_material_storage_dir=os.getenv(
            "PLATFORM_KNOWLEDGE_MATERIAL_STORAGE_DIR", "./.runtime/knowledge-materials"
        ),
        ai_service_base_url=os.getenv(
            "AI_SERVICE_BASE_URL", "http://127.0.0.1:8000"
        ).rstrip("/"),
        ai_service_timeout_seconds=float(
            os.getenv("AI_SERVICE_TIMEOUT_SECONDS", "120")
        ),
        iam_session_ttl_minutes=int(os.getenv("IAM_SESSION_TTL_MINUTES", "480")),
    )
