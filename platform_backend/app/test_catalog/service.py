"""Application service for V0.3.1 test package preflight and import."""

from pathlib import PurePosixPath

from app.errors import AppError
from app.test_catalog.parser import ParsedTestPackage, parse_test_package_zip
from app.test_catalog.repository import TestCatalogRepository
from app.test_catalog.schemas import (
    PackageIssue,
    TestPackagePreflightResponse,
    TestPackageSummary,
)

ZIP_MIME_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}


class TestPackageService:
    def __init__(
        self,
        repository: TestCatalogRepository | None,
        *,
        max_upload_bytes: int,
        max_entries: int,
        max_uncompressed_bytes: int,
        max_single_file_bytes: int,
    ) -> None:
        self.repository = repository
        self.max_upload_bytes = max_upload_bytes
        self.max_entries = max_entries
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.max_single_file_bytes = max_single_file_bytes

    def preflight(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> TestPackagePreflightResponse:
        safe_filename, parsed = self._parse(filename, content_type, content)
        manifest = parsed.manifest
        return TestPackagePreflightResponse(
            original_filename=safe_filename,
            file_sha256=parsed.file_sha256,
            file_size_bytes=parsed.file_size_bytes,
            package_id=parsed.package_id,
            package_name=str(manifest["package_name"]),
            version=str(manifest["version"]),
            schema_version=str(manifest["schema_version"]),
            tenant_id=str(manifest["tenant_id"]),
            platform="pdd",
            store_code="PDD-SM",
            test_data_mode=True,
            production_usable=False,
            response_mode=str(manifest["response_mode"]),
            allow_auto_send=False,
            worksheets=parsed.worksheets,
            counts=parsed.counts,
            warnings=[
                PackageIssue(
                    code="TEST_ONLY_PACKAGE",
                    message="Imported records remain isolated from production and auto-send",
                )
            ],
            errors=[],
            can_import=True,
        )

    def import_package(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        imported_by: str,
    ) -> TestPackageSummary:
        safe_filename, parsed = self._parse(filename, content_type, content)
        if self.repository is None:
            raise RuntimeError("A repository is required for a persisted test package import")
        package = self.repository.save_package(
            parsed,
            original_filename=safe_filename,
            imported_by=imported_by,
        )
        return self.repository.package_summary(package)

    def _parse(
        self, filename: str, content_type: str | None, content: bytes
    ) -> tuple[str, ParsedTestPackage]:
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        if not safe_filename.lower().endswith(".zip"):
            raise AppError(
                "UNSUPPORTED_TEST_PACKAGE_TYPE",
                "Only .zip test packages are supported",
                status_code=415,
            )
        if content_type and content_type.lower() not in ZIP_MIME_TYPES:
            raise AppError(
                "UNSUPPORTED_TEST_PACKAGE_TYPE",
                "Only ZIP content types are supported",
                status_code=415,
            )
        if not content.startswith(b"PK"):
            raise AppError("INVALID_ZIP", "The uploaded file is not a valid ZIP archive")
        if len(content) > self.max_upload_bytes:
            raise AppError("TEST_PACKAGE_TOO_LARGE", "Test package exceeds the upload limit")
        parsed = parse_test_package_zip(
            content,
            max_entries=self.max_entries,
            max_uncompressed_bytes=self.max_uncompressed_bytes,
            max_single_file_bytes=self.max_single_file_bytes,
        )
        return safe_filename, parsed
