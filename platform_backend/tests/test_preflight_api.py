from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.models import ImportBatch, ImportRow, StagedProductSku
from app.ingestion.parsers.product_sku_xlsx import EXPECTED_HEADERS
from conftest import valid_row, workbook_bytes

FIXTURES = Path(__file__).parent / "fixtures"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PREFLIGHT_URL = "/api/v1/import-batches/product-sku/preflight"


def preflight(client: TestClient, content: bytes, filename: str = "synthetic.xlsx"):
    return client.post(
        PREFLIGHT_URL,
        files={"file": (filename, content, XLSX_MIME)},
    )


def codes(body: dict[str, object], key: str) -> set[str]:
    summaries = body[key]
    assert isinstance(summaries, list)
    return {str(item["code"]) for item in summaries}


def database_counts(session: Session) -> tuple[int, int, int]:
    return (
        session.scalar(select(func.count()).select_from(ImportBatch)) or 0,
        session.scalar(select(func.count()).select_from(ImportRow)) or 0,
        session.scalar(select(func.count()).select_from(StagedProductSku)) or 0,
    )


def test_valid_file_preflight_reports_metadata_and_writes_nothing(
    client: TestClient, session: Session
) -> None:
    content = (FIXTURES / "product_sku_valid_10.xlsx").read_bytes()
    before = database_counts(session)

    response = preflight(client, content)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["original_filename"] == "synthetic.xlsx"
    assert len(body["file_sha256"]) == 64
    assert body["file_size_bytes"] == len(content)
    assert body["worksheets"] == ["商品SKU资料"]
    assert body["data_row_count"] == 10
    assert body["valid_rows"] == 10
    assert body["missing_columns"] == []
    assert body["unknown_columns"] == []
    assert body["formula_cell_count"] == 0
    assert body["error_summary"] == []
    assert body["can_import"] is True
    assert database_counts(session) == before == (0, 0, 0)


def test_preflight_reports_missing_column(client: TestClient) -> None:
    headers = [header for header in EXPECTED_HEADERS if header != "product_name"]

    response = preflight(client, workbook_bytes([valid_row()], headers=headers))

    assert response.status_code == 200
    body = response.json()
    assert body["missing_columns"] == ["product_name"]
    assert body["can_import"] is False
    assert "INVALID_TEMPLATE" in codes(body, "error_summary")


def test_preflight_reports_unknown_column(client: TestClient) -> None:
    headers = [*EXPECTED_HEADERS, "legacy_note"]

    response = preflight(client, workbook_bytes([valid_row()], headers=headers))

    assert response.status_code == 200
    body = response.json()
    assert body["unknown_columns"] == ["legacy_note"]
    assert body["can_import"] is False
    assert "INVALID_TEMPLATE" in codes(body, "error_summary")


def test_preflight_counts_formula_cells_as_blocking_errors(client: TestClient) -> None:
    content = workbook_bytes(
        [valid_row()], formula_cells={"F3": '="synthetic product"'}
    )

    response = preflight(client, content)

    assert response.status_code == 200
    body = response.json()
    assert body["formula_cell_count"] == 1
    assert body["invalid_rows"] == 1
    assert body["can_import"] is False
    assert "FORMULA_NOT_ALLOWED" in codes(body, "error_summary")


def test_preflight_warns_about_hidden_support_sheet(client: TestClient) -> None:
    content = workbook_bytes([valid_row()], hide_support_sheet=True)

    response = preflight(client, content)

    assert response.status_code == 200
    body = response.json()
    assert body["hidden_sheet_warnings"] == ["Worksheet '隐藏说明' is hidden"]
    assert "HIDDEN_WORKSHEET" in codes(body, "warning_summary")
    assert body["can_import"] is True


def test_preflight_rejects_unsupported_file_type(client: TestClient) -> None:
    response = client.post(
        PREFLIGHT_URL,
        files={"file": ("products.csv", b"bad", "text/csv")},
        headers={"X-Request-ID": "preflight-file-type"},
    )

    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_FILE_TYPE",
            "message": "Only .xlsx files are supported",
        },
        "request_id": "preflight-file-type",
    }
