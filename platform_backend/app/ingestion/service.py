"""Orchestration for product/SKU ingestion into the review-only zone."""

from collections import defaultdict
from pathlib import PurePosixPath

from app.errors import AppError
from app.ingestion.hashing import sha256_bytes, stable_identity_key, stable_row_hash
from app.ingestion.models import ImportBatch
from app.ingestion.normalizers.product_sku import normalize_product_sku
from app.ingestion.parsers.product_sku_xlsx import parse_product_sku_xlsx
from app.ingestion.repository import IngestionRepository
from app.ingestion.schemas import (
    BatchStatus,
    ErrorCode,
    ProcessedRow,
    RowStatus,
    ValidationIssue,
)
from app.ingestion.validators.product_sku import validate_product_sku

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class IngestionService:
    def __init__(
        self,
        repository: IngestionRepository,
        *,
        max_upload_bytes: int,
        max_import_rows: int,
    ) -> None:
        self.repository = repository
        self.max_upload_bytes = max_upload_bytes
        self.max_import_rows = max_import_rows

    def process_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        created_by: str,
    ) -> ImportBatch:
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        self._validate_file(safe_filename, content_type, content)
        batch = self.repository.create_batch(
            original_filename=safe_filename,
            file_sha256=sha256_bytes(content),
            created_by=created_by.strip()[:128] or "manual-import",
        )
        self.repository.set_status(batch, BatchStatus.PARSING)
        try:
            parsed_rows = parse_product_sku_xlsx(content, max_rows=self.max_import_rows)
            processed = self._process_rows(parsed_rows)
            self.repository.save_processed_rows(batch, processed)
            self.repository.set_status(batch, BatchStatus.VALIDATED)
            final_status = (
                BatchStatus.READY_FOR_REVIEW if batch.valid_rows > 0 else BatchStatus.REJECTED
            )
            self.repository.set_status(batch, final_status, completed=True)
            return batch
        except AppError as exc:
            self.repository.set_status(
                batch,
                BatchStatus.FAILED,
                error_message=f"{exc.code}: {exc.message}",
                completed=True,
            )
            raise
        except Exception as exc:
            self.repository.set_status(
                batch,
                BatchStatus.FAILED,
                error_message="INTERNAL_PARSE_ERROR: ingestion failed",
                completed=True,
            )
            raise AppError(
                ErrorCode.INTERNAL_PARSE_ERROR,
                "The import could not be completed",
                status_code=500,
            ) from exc

    def _validate_file(
        self, filename: str, content_type: str | None, content: bytes
    ) -> None:
        if not filename.lower().endswith(".xlsx"):
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                "Only .xlsx files are supported",
                status_code=415,
            )
        if content_type not in ALLOWED_MIME_TYPES:
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                "The uploaded MIME type is not an XLSX workbook",
                status_code=415,
            )
        if len(content) > self.max_upload_bytes:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                f"File exceeds the {self.max_upload_bytes}-byte upload limit",
                status_code=413,
            )

    def _process_rows(self, parsed_rows: list) -> list[ProcessedRow]:
        rows: list[ProcessedRow] = []
        for parsed in parsed_rows:
            normalized = normalize_product_sku(parsed.raw_data)
            errors = validate_product_sku(
                normalized,
                row_number=parsed.source_row_number,
                formula_fields=parsed.formula_fields,
            )
            rows.append(
                ProcessedRow(
                    source_row_number=parsed.source_row_number,
                    raw_data=parsed.raw_data,
                    normalized_data=normalized,
                    row_hash=stable_row_hash(normalized),
                    identity_key=stable_identity_key(normalized),
                    validation_status=RowStatus.INVALID if errors else RowStatus.VALID,
                    errors=errors,
                )
            )

        by_hash: dict[str, list[ProcessedRow]] = defaultdict(list)
        for row in rows:
            if row.validation_status == RowStatus.VALID:
                by_hash[row.row_hash].append(row)
        for group in by_hash.values():
            for duplicate in group[1:]:
                duplicate.validation_status = RowStatus.DUPLICATE
                duplicate.errors.append(
                    _issue(
                        ErrorCode.DUPLICATE_ROW,
                        duplicate.source_row_number,
                        None,
                        duplicate.row_hash,
                        "This normalized row is duplicated within the batch",
                        "Remove the duplicate row or keep one verified source row",
                    )
                )

        by_identity: dict[str, list[ProcessedRow]] = defaultdict(list)
        for row in rows:
            if row.validation_status == RowStatus.VALID:
                by_identity[row.identity_key].append(row)
        for group in by_identity.values():
            if len({row.row_hash for row in group}) <= 1:
                continue
            for conflict in group:
                conflict.validation_status = RowStatus.CONFLICT
                conflict.errors.append(
                    _issue(
                        ErrorCode.CONFLICT_REQUIRES_REVIEW,
                        conflict.source_row_number,
                        None,
                        conflict.identity_key,
                        "The same product/SKU identity has conflicting data",
                        "Verify the source and import a single authoritative row",
                    )
                )

        tenants = {row.normalized_data.get("tenant_id") for row in rows}
        tenants.discard(None)
        if len(tenants) > 1:
            for row in rows:
                row.validation_status = RowStatus.CONFLICT
                row.errors.append(
                    _issue(
                        ErrorCode.CONFLICT_REQUIRES_REVIEW,
                        row.source_row_number,
                        "tenant_id",
                        row.normalized_data.get("tenant_id"),
                        "A single import batch cannot contain multiple tenants",
                        "Split the workbook into one batch per tenant",
                    )
                )
        return rows


def _issue(
    code: ErrorCode,
    row_number: int,
    field: str | None,
    raw_value: object,
    message: str,
    suggestion: str,
) -> ValidationIssue:
    return ValidationIssue(
        error_code=code,
        message=message,
        row_number=row_number,
        field=field,
        raw_value=raw_value,
        suggestion=suggestion,
    )
