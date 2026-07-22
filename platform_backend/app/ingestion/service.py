"""Orchestration for product/SKU ingestion into the review-only zone."""

from collections import Counter, defaultdict
from pathlib import PurePosixPath

from app.errors import AppError
from app.ingestion.hashing import sha256_bytes, stable_identity_key, stable_row_hash
from app.ingestion.models import ImportBatch
from app.ingestion.normalizers.product_sku import normalize_product_sku
from app.ingestion.parsers.product_sku_xlsx import (
    DATA_SHEET,
    inspect_product_sku_xlsx,
    parse_product_sku_xlsx,
)
from app.ingestion.repository import IngestionRepository
from app.ingestion.schemas import (
    BatchStatus,
    ErrorCode,
    PreflightIssueSummary,
    ProcessedRow,
    ProductSkuPreflightResponse,
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
        repository: IngestionRepository | None,
        *,
        max_upload_bytes: int,
        max_import_rows: int,
    ) -> None:
        self.repository = repository
        self.max_upload_bytes = max_upload_bytes
        self.max_import_rows = max_import_rows

    def preflight_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> ProductSkuPreflightResponse:
        """Analyze an XLSX without opening a database session or writing a batch."""
        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        self._validate_file(safe_filename, content_type, content)
        inspection = inspect_product_sku_xlsx(content, max_rows=self.max_import_rows)

        error_counts: Counter[str] = Counter()
        error_messages: dict[str, str] = {}
        warning_counts: Counter[str] = Counter()
        warning_messages: dict[str, str] = {}

        def add_error(code: str | ErrorCode, count: int, message: str) -> None:
            if count <= 0:
                return
            key = str(code)
            error_counts[key] += count
            error_messages.setdefault(key, message)

        def add_warning(code: str, count: int, message: str) -> None:
            if count <= 0:
                return
            warning_counts[code] += count
            warning_messages.setdefault(code, message)

        if not inspection.data_sheet_present:
            add_error(
                ErrorCode.INVALID_TEMPLATE,
                1,
                f"Required worksheet '{DATA_SHEET}' is missing",
            )
        if inspection.missing_columns:
            add_error(
                ErrorCode.INVALID_TEMPLATE,
                len(inspection.missing_columns),
                "Required template columns are missing",
            )
        if inspection.unknown_columns:
            add_error(
                ErrorCode.INVALID_TEMPLATE,
                len(inspection.unknown_columns),
                "Unknown template columns are present",
            )
        if (
            inspection.data_sheet_present
            and not inspection.fixed_headers_match
            and not inspection.missing_columns
            and not inspection.unknown_columns
        ):
            add_error(
                ErrorCode.INVALID_TEMPLATE,
                1,
                "Template columns are not in the fixed order",
            )
        if inspection.data_sheet_present and not inspection.data_sheet_visible:
            add_error(
                ErrorCode.INVALID_TEMPLATE,
                1,
                "The product data worksheet must be visible",
            )
        if inspection.row_limit_exceeded:
            add_error(
                ErrorCode.TOO_MANY_ROWS,
                1,
                f"Workbook exceeds the {self.max_import_rows}-row import limit",
            )
        if inspection.data_sheet_present and inspection.data_row_count == 0:
            add_error(
                ErrorCode.INVALID_TEMPLATE,
                1,
                "The product data worksheet has no data rows",
            )

        processed: list[ProcessedRow] = []
        if (
            inspection.data_sheet_present
            and inspection.fixed_headers_match
            and not inspection.row_limit_exceeded
        ):
            processed = self._process_rows(inspection.parsed_rows)
            for row in processed:
                for issue in row.errors:
                    if issue.error_code != ErrorCode.FORMULA_NOT_ALLOWED:
                        add_error(issue.error_code, 1, issue.message)

        add_error(
            ErrorCode.FORMULA_NOT_ALLOWED,
            inspection.formula_cell_count,
            "Formula cells are not accepted as trusted values",
        )
        add_warning(
            "HIDDEN_WORKSHEET",
            len(inspection.hidden_worksheet_names),
            "Hidden worksheets require review and are never treated as product data",
        )
        add_warning(
            "BLANK_ROWS_IGNORED",
            inspection.blank_row_count,
            "Blank rows will be ignored during import",
        )

        return ProductSkuPreflightResponse(
            original_filename=safe_filename,
            file_sha256=sha256_bytes(content),
            file_size_bytes=len(content),
            worksheets=inspection.worksheet_names,
            data_row_count=inspection.data_row_count,
            valid_rows=sum(row.validation_status == RowStatus.VALID for row in processed),
            invalid_rows=sum(row.validation_status == RowStatus.INVALID for row in processed),
            duplicate_rows=sum(
                row.validation_status == RowStatus.DUPLICATE for row in processed
            ),
            conflict_rows=sum(
                row.validation_status == RowStatus.CONFLICT for row in processed
            ),
            missing_columns=inspection.missing_columns,
            unknown_columns=inspection.unknown_columns,
            formula_cell_count=inspection.formula_cell_count,
            hidden_sheet_warnings=[
                f"Worksheet '{name}' is hidden"
                for name in inspection.hidden_worksheet_names
            ],
            blank_row_count=inspection.blank_row_count,
            error_summary=[
                PreflightIssueSummary(
                    code=code,
                    count=error_counts[code],
                    message=error_messages[code],
                )
                for code in sorted(error_counts)
            ],
            warning_summary=[
                PreflightIssueSummary(
                    code=code,
                    count=warning_counts[code],
                    message=warning_messages[code],
                )
                for code in sorted(warning_counts)
            ],
            can_import=not error_counts,
        )

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
        if self.repository is None:
            raise RuntimeError("A repository is required for a persisted import")
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
