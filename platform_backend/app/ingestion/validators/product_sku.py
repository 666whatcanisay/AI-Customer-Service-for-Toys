"""Validation rules and stable row-level error payloads."""

from datetime import date
from typing import Any

from app.ingestion.schemas import ErrorCode, ValidationIssue

ALLOWED_PLATFORMS = {"douyin", "taobao", "pdd", "jd", "offline", "other"}
REQUIRED_FIELDS = {
    "tenant_id",
    "platform",
    "store_code",
    "product_name",
    "sku_name",
    "source_name",
}
FIELD_LIMITS = {
    "tenant_id": 64,
    "platform": 32,
    "store_code": 128,
    "product_code": 128,
    "platform_product_id": 128,
    "product_name": 255,
    "sku_code": 128,
    "platform_sku_id": 128,
    "sku_name": 255,
    "specifications": 2000,
    "material": 255,
    "package_contents": 2000,
    "source_name": 255,
    "notes": 2000,
}


def _issue(
    code: ErrorCode,
    row_number: int,
    field: str | None,
    raw_value: Any,
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


def validate_product_sku(
    normalized: dict[str, Any],
    *,
    row_number: int,
    formula_fields: list[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for field in sorted(REQUIRED_FIELDS):
        if normalized.get(field) is None:
            issues.append(
                _issue(
                    ErrorCode.REQUIRED_FIELD_MISSING,
                    row_number,
                    field,
                    None,
                    f"Required field '{field}' is missing",
                    "Fill the field using a verified source",
                )
            )
    platform = normalized.get("platform")
    if platform is not None and platform not in ALLOWED_PLATFORMS:
        issues.append(
            _issue(
                ErrorCode.INVALID_PLATFORM,
                row_number,
                "platform",
                platform,
                "Platform is not in the allowed list",
                "Use douyin, taobao, pdd, jd, offline, or other",
            )
        )
    for field in ("applicable_age_min", "applicable_age_max"):
        value = normalized.get(field)
        if value is not None and (not isinstance(value, int) or value < 0):
            issues.append(
                _issue(
                    ErrorCode.INVALID_INTEGER,
                    row_number,
                    field,
                    value,
                    "Age must be a non-negative integer",
                    "Enter a verified whole number or leave the field blank",
                )
            )
    age_min = normalized.get("applicable_age_min")
    age_max = normalized.get("applicable_age_max")
    if isinstance(age_min, int) and isinstance(age_max, int) and age_min > age_max:
        issues.append(
            _issue(
                ErrorCode.AGE_RANGE_INVALID,
                row_number,
                "applicable_age_min",
                age_min,
                "Minimum age cannot exceed maximum age",
                "Verify both age limits against the source",
            )
        )
    parsed_dates: dict[str, date] = {}
    for field in ("effective_from", "effective_to"):
        value = normalized.get(field)
        if value is None:
            continue
        try:
            parsed_dates[field] = date.fromisoformat(value)
        except (TypeError, ValueError):
            issues.append(
                _issue(
                    ErrorCode.INVALID_DATE,
                    row_number,
                    field,
                    value,
                    "Date must use ISO 8601 format",
                    "Use YYYY-MM-DD or leave the field blank",
                )
            )
    if (
        "effective_from" in parsed_dates
        and "effective_to" in parsed_dates
        and parsed_dates["effective_from"] > parsed_dates["effective_to"]
    ):
        issues.append(
            _issue(
                ErrorCode.EFFECTIVE_RANGE_INVALID,
                row_number,
                "effective_from",
                normalized.get("effective_from"),
                "Effective start date cannot be after the end date",
                "Verify both effective dates against the source",
            )
        )
    if not (normalized.get("product_code") or normalized.get("platform_product_id")):
        issues.append(
            _issue(
                ErrorCode.PRODUCT_IDENTIFIER_MISSING,
                row_number,
                "product_code",
                None,
                "A product_code or platform_product_id is required",
                "Provide at least one verified product identifier",
            )
        )
    if not (normalized.get("sku_code") or normalized.get("platform_sku_id")):
        issues.append(
            _issue(
                ErrorCode.SKU_IDENTIFIER_MISSING,
                row_number,
                "sku_code",
                None,
                "A sku_code or platform_sku_id is required",
                "Provide at least one verified SKU identifier",
            )
        )
    for field, limit in FIELD_LIMITS.items():
        value = normalized.get(field)
        if isinstance(value, str) and len(value) > limit:
            issues.append(
                _issue(
                    ErrorCode.INVALID_TEMPLATE,
                    row_number,
                    field,
                    f"<{len(value)} characters>",
                    f"Field exceeds the {limit}-character limit",
                    "Shorten the value without removing required facts",
                )
            )
    for field in formula_fields:
        issues.append(
            _issue(
                ErrorCode.FORMULA_NOT_ALLOWED,
                row_number,
                field,
                normalized.get(field),
                "Formula cells are not accepted as trusted values",
                "Replace the formula with a verified static value",
            )
        )
    return issues
