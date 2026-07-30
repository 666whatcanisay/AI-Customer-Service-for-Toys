"""Stable ingestion enums and API schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BatchStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PARSING = "PARSING"
    VALIDATED = "VALIDATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    IDENTIFIED_PENDING_REVIEW = "IDENTIFIED_PENDING_REVIEW"
    NO_CHANGE = "NO_CHANGE"
    PARTIALLY_REVIEWED = "PARTIALLY_REVIEWED"
    COMPLETED = "COMPLETED"


class RowStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"


class ReviewStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"


class ErrorCode(StrEnum):
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    INVALID_PLATFORM = "INVALID_PLATFORM"
    INVALID_INTEGER = "INVALID_INTEGER"
    INVALID_DATE = "INVALID_DATE"
    AGE_RANGE_INVALID = "AGE_RANGE_INVALID"
    EFFECTIVE_RANGE_INVALID = "EFFECTIVE_RANGE_INVALID"
    PRODUCT_IDENTIFIER_MISSING = "PRODUCT_IDENTIFIER_MISSING"
    SKU_IDENTIFIER_MISSING = "SKU_IDENTIFIER_MISSING"
    DUPLICATE_ROW = "DUPLICATE_ROW"
    CONFLICT_REQUIRES_REVIEW = "CONFLICT_REQUIRES_REVIEW"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_ROWS = "TOO_MANY_ROWS"
    INVALID_TEMPLATE = "INVALID_TEMPLATE"
    FORMULA_NOT_ALLOWED = "FORMULA_NOT_ALLOWED"
    INTERNAL_PARSE_ERROR = "INTERNAL_PARSE_ERROR"


class ValidationIssue(BaseModel):
    error_code: ErrorCode
    message: str
    row_number: int
    field: str | None = None
    raw_value: Any = None
    suggestion: str


class ParsedRow(BaseModel):
    source_row_number: int
    raw_data: dict[str, Any]
    formula_fields: list[str] = Field(default_factory=list)


class ProcessedRow(BaseModel):
    source_row_number: int
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    row_hash: str
    identity_key: str
    validation_status: RowStatus
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class PreflightIssueSummary(BaseModel):
    code: str
    count: int
    message: str


class ProductSkuPreflightResponse(BaseModel):
    original_filename: str
    file_sha256: str
    file_size_bytes: int
    worksheets: list[str]
    data_row_count: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    conflict_rows: int
    missing_columns: list[str]
    unknown_columns: list[str]
    formula_cell_count: int
    hidden_sheet_warnings: list[str]
    blank_row_count: int
    error_summary: list[PreflightIssueSummary]
    warning_summary: list[PreflightIssueSummary]
    can_import: bool


class BatchSummary(BaseModel):
    id: str
    batch_id: str
    tenant_id: str
    import_type: str
    original_filename: str
    file_sha256: str
    status: BatchStatus
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    created_at: datetime
    completed_at: datetime | None
    created_by: str
    error_message: str | None


class BatchDetail(BatchSummary):
    staged_rows: int


class BatchListResponse(BaseModel):
    items: list[BatchSummary]
    page: int
    page_size: int
    total: int


class ImportRowResponse(BaseModel):
    id: int
    batch_id: str
    source_row_number: int
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    row_hash: str
    validation_status: RowStatus
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]


class ImportRowListResponse(BaseModel):
    items: list[ImportRowResponse]
    page: int
    page_size: int
    total: int
