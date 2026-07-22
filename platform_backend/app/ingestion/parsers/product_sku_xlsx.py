"""Read-only parser and inspector for the fixed product/SKU XLSX template."""

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any
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


@dataclass(slots=True)
class ProductSkuWorkbookInspection:
    worksheet_names: list[str]
    hidden_worksheet_names: list[str]
    data_sheet_present: bool
    data_sheet_visible: bool
    fixed_headers: list[Any] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    unknown_columns: list[str] = field(default_factory=list)
    data_row_count: int = 0
    blank_row_count: int = 0
    formula_cell_count: int = 0
    row_limit_exceeded: bool = False
    parsed_rows: list[ParsedRow] = field(default_factory=list)

    @property
    def fixed_headers_match(self) -> bool:
        return self.fixed_headers == EXPECTED_HEADERS


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


def _load_workbook(content: bytes):
    _check_zip_size(content)
    try:
        return load_workbook(
            BytesIO(content), read_only=False, data_only=False, keep_links=False
        )
    except Exception as exc:
        raise AppError(
            ErrorCode.INTERNAL_PARSE_ERROR,
            "The XLSX workbook could not be parsed",
            status_code=422,
        ) from exc


def inspect_product_sku_xlsx(
    content: bytes, *, max_rows: int
) -> ProductSkuWorkbookInspection:
    """Inspect workbook structure and rows without mutating persistence."""
    workbook = _load_workbook(content)
    inspection = ProductSkuWorkbookInspection(
        worksheet_names=list(workbook.sheetnames),
        hidden_worksheet_names=[
            sheet.title for sheet in workbook.worksheets if sheet.sheet_state != "visible"
        ],
        data_sheet_present=DATA_SHEET in workbook.sheetnames,
        data_sheet_visible=False,
    )
    if DATA_SHEET not in workbook.sheetnames:
        inspection.missing_columns = list(EXPECTED_HEADERS)
        return inspection

    sheet = workbook[DATA_SHEET]
    inspection.data_sheet_visible = sheet.sheet_state == "visible"
    inspection.fixed_headers = [
        sheet.cell(1, index + 1).value for index in range(len(EXPECTED_HEADERS))
    ]
    actual_headers = [
        sheet.cell(1, index + 1).value for index in range(sheet.max_column)
    ]
    inspection.missing_columns = [
        header for header in EXPECTED_HEADERS if header not in actual_headers
    ]
    inspection.unknown_columns = list(
        dict.fromkeys(
            str(header)
            for header in actual_headers
            if header not in (None, "") and header not in EXPECTED_HEADERS
        )
    )
    inspection.row_limit_exceeded = max(sheet.max_row - 2, 0) > max_rows

    inspected_column_count = max(sheet.max_column, len(EXPECTED_HEADERS))
    for row_number in range(3, sheet.max_row + 1):
        inspected_cells = [
            sheet.cell(row_number, index + 1)
            for index in range(inspected_column_count)
        ]
        if all(cell.value in (None, "") for cell in inspected_cells):
            inspection.blank_row_count += 1
            continue
        inspection.data_row_count += 1
        inspection.formula_cell_count += sum(
            cell.data_type == "f" for cell in inspected_cells
        )

        fixed_cells = inspected_cells[: len(EXPECTED_HEADERS)]
        if all(cell.value in (None, "") for cell in fixed_cells):
            continue
        inspection.parsed_rows.append(
            ParsedRow(
                source_row_number=row_number,
                raw_data={
                    header: cell.value
                    for header, cell in zip(EXPECTED_HEADERS, fixed_cells)
                },
                formula_fields=[
                    header
                    for header, cell in zip(EXPECTED_HEADERS, fixed_cells)
                    if cell.data_type == "f"
                ],
            )
        )
    return inspection


def parse_product_sku_xlsx(content: bytes, *, max_rows: int) -> list[ParsedRow]:
    inspection = inspect_product_sku_xlsx(content, max_rows=max_rows)
    if not inspection.data_sheet_present:
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            f"Required worksheet '{DATA_SHEET}' is missing",
            status_code=422,
        )
    if not inspection.data_sheet_visible:
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            "The product data worksheet must be visible",
            status_code=422,
        )
    if not inspection.fixed_headers_match:
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            "The first row does not match the fixed product/SKU template",
            status_code=422,
        )
    if inspection.row_limit_exceeded:
        raise AppError(
            ErrorCode.TOO_MANY_ROWS,
            f"Workbook exceeds the {max_rows}-row import limit",
            status_code=413,
        )
    return inspection.parsed_rows
