"""Deterministic parser for 商品知识采集模板 V1.xlsx."""

from __future__ import annotations

from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.product_knowledge_import.product_knowledge_mapping import (
    DATA_SHEET,
    EXAMPLE_SHEET,
    EXPECTED_HEADERS,
    EXPECTED_SHEETS,
    EXPECTED_SHEET_TITLES,
    FIELD_DESCRIPTION_SHEET,
    HEADER_SCAN_MAX_ROWS,
    MAPPING_BY_HEADER,
    PARSER_VERSION,
    REQUIRED_HEADERS,
    TEMPLATE_TYPE,
    TEMPLATE_VERSION,
    CONFIRMATION_VALUES,
)
from app.product_knowledge_import.schemas import (
    ParsedProductKnowledgeRow,
    ProductKnowledgeParseResult,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    # Preserve operator-authored punctuation and wording in formal knowledge.
    # NFKC is used only for identity comparisons in the service layer.
    return str(value).strip()


def _normalized_header_row(sheet, row_number: int) -> tuple[str, ...]:
    return tuple(
        _text(sheet.cell(row_number, index).value)
        for index in range(1, len(EXPECTED_HEADERS) + 1)
    )


def _matching_header_rows(sheet) -> list[int]:
    """Find the frozen 16-column header without assuming a physical row number."""

    return [
        row_number
        for row_number in range(1, min(sheet.max_row, HEADER_SCAN_MAX_ROWS) + 1)
        if _normalized_header_row(sheet, row_number) == EXPECTED_HEADERS
    ]


def _matching_field_description_starts(sheet) -> list[int]:
    """Find the frozen vertical field list used to validate the mapping evidence."""

    last_start = min(sheet.max_row, HEADER_SCAN_MAX_ROWS) - len(EXPECTED_HEADERS) + 1
    if last_start < 1:
        return []
    return [
        row_number
        for row_number in range(1, last_start + 1)
        if tuple(
            _text(sheet.cell(row_number + offset, 1).value)
            for offset in range(len(EXPECTED_HEADERS))
        )
        == EXPECTED_HEADERS
    ]


class ProductKnowledgeTemplateParser:
    """Parse exactly the frozen V1 workbook without AI or dynamic inference."""

    def parse(
        self,
        content: bytes,
        *,
        max_rows: int,
        imported_at: datetime | None = None,
    ) -> ProductKnowledgeParseResult:
        system_import_date = (imported_at or datetime.now(timezone.utc)).date().isoformat()
        try:
            workbook = load_workbook(
                BytesIO(content),
                read_only=False,
                data_only=False,
                keep_links=False,
            )
        except (InvalidFileException, BadZipFile, OSError, ValueError, KeyError):
            return self._failed_result(
                "WORKBOOK_UNREADABLE",
                "Excel 文件无法读取，请使用商品知识采集模板 V1。",
            )

        sheet_results: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        expected_set = set(EXPECTED_SHEETS)
        actual_set = set(workbook.sheetnames)
        extra_sheets = sorted(actual_set - expected_set)

        for name in EXPECTED_SHEETS:
            present = name in workbook.sheetnames
            visible = bool(present and workbook[name].sheet_state == "visible")
            valid = present and visible
            errors: list[str] = []
            if not present:
                errors.append("SHEET_MISSING")
            elif not visible:
                errors.append("SHEET_NOT_VISIBLE")
            if present and _text(workbook[name]["A1"].value) != EXPECTED_SHEET_TITLES[name]:
                valid = False
                errors.append("SHEET_TITLE_MISMATCH")
            sheet_results.append(
                {
                    "sheet_name": name,
                    "present": present,
                    "visible": visible,
                    "valid": valid,
                    "errors": errors,
                }
            )
            for code in errors:
                message = (
                    f"工作表“{name}”标题与商品知识采集模板 V1 不一致。"
                    if code == "SHEET_TITLE_MISMATCH"
                    else f"工作表“{name}”缺失或不可见。"
                )
                issues.append(
                    {
                        "code": code,
                        "sheet": name,
                        "row": None,
                        "field": None,
                        "message": message,
                    }
                )

        if extra_sheets:
            issues.append(
                {
                    "code": "UNEXPECTED_SHEETS",
                    "sheet": None,
                    "row": None,
                    "field": None,
                    "message": f"模板包含未冻结工作表：{'、'.join(extra_sheets)}。",
                }
            )

        formula_cells: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.data_type == "f" or (
                        isinstance(cell.value, str) and cell.value.startswith("=")
                    ):
                        formula_cells.append(f"{sheet.title}!{cell.coordinate}")
        if formula_cells:
            issues.append(
                {
                    "code": "FORMULA_NOT_ALLOWED",
                    "sheet": None,
                    "row": None,
                    "field": None,
                    "message": "模板包含公式单元格，不能作为可信业务数据导入。",
                    "cells": formula_cells[:50],
                }
            )

        products: list[ParsedProductKnowledgeRow] = []
        detected_header_rows: dict[str, int] = {}
        field_description_start_row: int | None = None
        if DATA_SHEET in workbook.sheetnames:
            data_sheet = workbook[DATA_SHEET]
            header_rows = _matching_header_rows(data_sheet)
            if len(header_rows) != 1:
                issue_code = "HEADER_MISMATCH" if not header_rows else "HEADER_AMBIGUOUS"
                issues.append(
                    {
                        "code": issue_code,
                        "sheet": DATA_SHEET,
                        "row": header_rows[0] if header_rows else None,
                        "field": None,
                        "message": (
                            "数据填写表未找到完整且唯一的16字段表头。"
                            if not header_rows
                            else "数据填写表包含多个16字段表头，无法确定业务数据起始位置。"
                        ),
                        "expected": list(EXPECTED_HEADERS),
                        "matched_rows": header_rows,
                    }
                )
            else:
                detected_header_rows[DATA_SHEET] = header_rows[0]
                products, row_issues = self._parse_data_rows(
                    data_sheet,
                    header_row=header_rows[0],
                    max_rows=max_rows,
                    system_import_date=system_import_date,
                )
                issues.extend(row_issues)

        for support_sheet in (EXAMPLE_SHEET,):
            if support_sheet in workbook.sheetnames:
                support_header_rows = _matching_header_rows(workbook[support_sheet])
                if len(support_header_rows) != 1:
                    issues.append(
                        {
                            "code": "EXAMPLE_HEADER_MISMATCH",
                            "sheet": support_sheet,
                            "row": support_header_rows[0] if support_header_rows else None,
                            "field": None,
                            "message": "示例数据表未找到完整且唯一的16字段表头。",
                            "matched_rows": support_header_rows,
                        }
                    )
                else:
                    detected_header_rows[support_sheet] = support_header_rows[0]

        if FIELD_DESCRIPTION_SHEET in workbook.sheetnames:
            field_sheet = workbook[FIELD_DESCRIPTION_SHEET]
            description_starts = _matching_field_description_starts(field_sheet)
            if len(description_starts) != 1:
                issues.append(
                    {
                        "code": "FIELD_DESCRIPTION_MISMATCH",
                        "sheet": FIELD_DESCRIPTION_SHEET,
                        "row": description_starts[0] if description_starts else None,
                        "field": None,
                        "message": "字段说明未找到完整且唯一的16字段映射清单。",
                        "matched_rows": description_starts,
                    }
                )
            else:
                field_description_start_row = description_starts[0]

        if not products and not any(item["code"] == "HEADER_MISMATCH" for item in issues):
            issues.append(
                {
                    "code": "NO_DATA_ROWS",
                    "sheet": DATA_SHEET,
                    "row": None,
                    "field": None,
                    "message": "数据填写工作表没有可导入的商品记录。",
                }
            )

        duplicate_names: dict[str, list[int]] = {}
        for product in products:
            key = product.product_name.casefold()
            duplicate_names.setdefault(key, []).append(product.source_row_number)
        for rows in duplicate_names.values():
            if len(rows) > 1:
                issues.append(
                    {
                        "code": "DUPLICATE_PRODUCT_ROW",
                        "sheet": DATA_SHEET,
                        "row": rows[0],
                        "field": "商品名称",
                        "message": f"同一商品在模板中重复出现：第 {', '.join(map(str, rows))} 行。",
                    }
                )

        blocking_codes = {
            "SHEET_MISSING",
            "SHEET_NOT_VISIBLE",
            "SHEET_TITLE_MISMATCH",
            "UNEXPECTED_SHEETS",
            "FORMULA_NOT_ALLOWED",
            "HEADER_MISMATCH",
            "HEADER_AMBIGUOUS",
            "EXAMPLE_HEADER_MISMATCH",
            "FIELD_DESCRIPTION_MISMATCH",
            "REQUIRED_FIELD_MISSING",
            "SOURCE_DATE_INVALID",
            "CONFIRMATION_INVALID",
            "ROW_LIMIT_EXCEEDED",
            "NO_DATA_ROWS",
            "DUPLICATE_PRODUCT_ROW",
        }
        blocking_count = sum(issue["code"] in blocking_codes for issue in issues)
        instruction_rows: list[list[str]] = []
        if "填写说明" in workbook.sheetnames:
            instruction_sheet = workbook["填写说明"]
            for row in instruction_sheet.iter_rows(values_only=True):
                values = [_text(value) for value in row]
                if any(values):
                    instruction_rows.append(values)
        return ProductKnowledgeParseResult(
            template_type=TEMPLATE_TYPE,
            template_version=TEMPLATE_VERSION,
            parser_version=PARSER_VERSION,
            template_metadata={
                "instruction_rows": instruction_rows,
                "field_mapping_source": FIELD_DESCRIPTION_SHEET,
                "field_mapping_mode": "FIXED_CODE_VALIDATED_BY_WORKBOOK",
                "detected_header_rows": detected_header_rows,
                "field_description_start_row": field_description_start_row,
                "system_import_date": system_import_date,
            },
            sheet_results=sheet_results,
            field_validation_result={
                "headers_valid": not any(
                    issue["code"]
                    in {"HEADER_MISMATCH", "EXAMPLE_HEADER_MISMATCH", "FIELD_DESCRIPTION_MISMATCH"}
                    for issue in issues
                ),
                "data_row_count": len(products),
                "valid": blocking_count == 0,
                "blocking_issue_count": blocking_count,
                "issues": issues,
            },
            products=products,
        )

    def _parse_data_rows(
        self,
        sheet,
        *,
        header_row: int,
        max_rows: int,
        system_import_date: str,
    ) -> tuple[list[ParsedProductKnowledgeRow], list[dict[str, Any]]]:
        products: list[ParsedProductKnowledgeRow] = []
        issues: list[dict[str, Any]] = []
        seen_rows = 0
        for row_number in range(header_row + 1, sheet.max_row + 1):
            values = {
                header: _text(sheet.cell(row_number, index).value)
                for index, header in enumerate(EXPECTED_HEADERS, start=1)
            }
            if not any(values.values()):
                continue
            seen_rows += 1
            if seen_rows > max_rows:
                issues.append(
                    {
                        "code": "ROW_LIMIT_EXCEEDED",
                        "sheet": DATA_SHEET,
                        "row": row_number,
                        "field": None,
                        "message": f"导入记录超过 {max_rows} 行限制。",
                    }
                )
                break
            for header in REQUIRED_HEADERS:
                if not values[header]:
                    issues.append(
                        {
                            "code": "REQUIRED_FIELD_MISSING",
                            "sheet": DATA_SHEET,
                            "row": row_number,
                            "field": header,
                            "message": f"第 {row_number} 行缺少必填字段“{header}”。",
                        }
                    )
            incoming_source_date = values["来源日期"]
            if incoming_source_date and not self._valid_date(incoming_source_date):
                issues.append(
                    {
                        "code": "SOURCE_DATE_INVALID",
                        "sheet": DATA_SHEET,
                        "row": row_number,
                        "field": "来源日期",
                        "message": f"第 {row_number} 行来源日期不是有效日期。",
                    }
                )
            source_date = incoming_source_date or system_import_date
            if values["是否人工确认"] and values["是否人工确认"] not in CONFIRMATION_VALUES:
                issues.append(
                    {
                        "code": "CONFIRMATION_INVALID",
                        "sheet": DATA_SHEET,
                        "row": row_number,
                        "field": "是否人工确认",
                        "message": "是否人工确认只能填写“已确认”或“待确认”。",
                    }
                )
            fields = {
                mapping.field_key: values[mapping.excel_header] or None
                for mapping in MAPPING_BY_HEADER.values()
            }
            products.append(
                ParsedProductKnowledgeRow(
                    source_row_number=row_number,
                    store_name=values["店铺名称"],
                    product_name=values["商品名称"],
                    fields=fields,
                    source_name=values["资料来源"],
                    source_date=source_date,
                    source_date_origin=(
                        "EXCEL" if incoming_source_date else "SYSTEM_IMPORT_DATE"
                    ),
                    human_confirmation=values["是否人工确认"] or None,
                    remark=values["备注"] or None,
                )
            )
        return products, issues

    @staticmethod
    def _valid_date(value: str) -> bool:
        try:
            date.fromisoformat(value[:10])
        except ValueError:
            return False
        return True

    @staticmethod
    def _failed_result(code: str, message: str) -> ProductKnowledgeParseResult:
        return ProductKnowledgeParseResult(
            template_type=TEMPLATE_TYPE,
            template_version=TEMPLATE_VERSION,
            parser_version=PARSER_VERSION,
            template_metadata={
                "instruction_rows": [],
                "field_mapping_source": FIELD_DESCRIPTION_SHEET,
                "field_mapping_mode": "FIXED_CODE_VALIDATED_BY_WORKBOOK",
            },
            sheet_results=[],
            field_validation_result={
                "headers_valid": False,
                "data_row_count": 0,
                "valid": False,
                "blocking_issue_count": 1,
                "issues": [{"code": code, "message": message}],
            },
            products=[],
        )
