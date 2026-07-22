"""Read-only parser for the fixed product/SKU XLSX template."""

from io import BytesIO
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from app.errors import AppError
from app.ingestion.schemas import ErrorCode, ParsedRow

DATA_SHEET = "商品SKU资料"
EXPECTED_HEADERS = [
    "tenant_id",
    "platform",
    "store_code",
    "product_code",
    "platform_product_id",
    "product_name",
    "sku_code",
    "platform_sku_id",
    "sku_name",
    "specifications",
    "applicable_age_min",
    "applicable_age_max",
    "material",
    "package_contents",
    "source_name",
    "effective_from",
    "effective_to",
    "notes",
]
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


def _check_zip_size(content: bytes) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise AppError(
                    ErrorCode.FILE_TOO_LARGE,
                    "XLSX uncompressed content exceeds the safety limit",
                    status_code=413,
                )
    except BadZipFile as exc:
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            "The uploaded file is not a valid XLSX workbook",
            status_code=422,
        ) from exc


def parse_product_sku_xlsx(content: bytes, *, max_rows: int) -> list[ParsedRow]:
    _check_zip_size(content)
    try:
        workbook = load_workbook(
            BytesIO(content), read_only=False, data_only=False, keep_links=False
        )
    except Exception as exc:
        raise AppError(
            ErrorCode.INTERNAL_PARSE_ERROR,
            "The XLSX workbook could not be parsed",
            status_code=422,
        ) from exc

    if DATA_SHEET not in workbook.sheetnames:
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            f"Required worksheet '{DATA_SHEET}' is missing",
            status_code=422,
        )
    sheet = workbook[DATA_SHEET]
    if sheet.sheet_state != "visible":
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            "The product data worksheet must be visible",
            status_code=422,
        )
    headers = [sheet.cell(1, index + 1).value for index in range(len(EXPECTED_HEADERS))]
    if headers != EXPECTED_HEADERS:
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            "The first row does not match the fixed product/SKU template",
            status_code=422,
        )
    if sheet.max_row - 2 > max_rows:
        raise AppError(
            ErrorCode.TOO_MANY_ROWS,
            f"Workbook exceeds the {max_rows}-row import limit",
            status_code=413,
        )

    parsed_rows: list[ParsedRow] = []
    for row_number in range(3, sheet.max_row + 1):
        cells = [sheet.cell(row_number, index + 1) for index in range(len(EXPECTED_HEADERS))]
        if all(cell.value in (None, "") for cell in cells):
            continue
        raw_data = {header: cell.value for header, cell in zip(EXPECTED_HEADERS, cells)}
        formula_fields = [
            header for header, cell in zip(EXPECTED_HEADERS, cells) if cell.data_type == "f"
        ]
        parsed_rows.append(
            ParsedRow(
                source_row_number=row_number,
                raw_data=raw_data,
                formula_fields=formula_fields,
            )
        )
    return parsed_rows
