from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(client: TestClient, fixture: str) -> dict[str, object]:
    with (FIXTURES / fixture).open("rb") as workbook:
        response = client.post(
            "/api/v1/import-batches/product-sku",
            files={"file": (fixture, workbook, XLSX_MIME)},
            data={"created_by": "api-pytest"},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["batch_id"] == body["id"]
    return body


def test_template_download_is_the_fixed_xlsx(client: TestClient) -> None:
    response = client.get("/api/v1/import-templates/product-sku")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(XLSX_MIME)
    assert response.content.startswith(b"PK")


def test_upload_list_detail_filter_and_error_report(client: TestClient) -> None:
    batch = upload(client, "product_sku_validation_cases.xlsx")
    batch_id = str(batch["id"])

    listing = client.get("/api/v1/import-batches").json()
    detail = client.get(f"/api/v1/import-batches/{batch_id}").json()
    invalid_rows = client.get(
        f"/api/v1/import-batches/{batch_id}/rows", params={"status": "INVALID"}
    ).json()
    errors = client.get(f"/api/v1/import-batches/{batch_id}/errors")

    assert listing["total"] == 1
    assert detail["status"] == "READY_FOR_REVIEW"
    assert detail["staged_rows"] == detail["valid_rows"]
    assert invalid_rows["total"] >= 6
    assert all(row["validation_status"] == "INVALID" for row in invalid_rows["items"])
    assert errors.status_code == 200
    assert errors.content.startswith(b"\xef\xbb\xbfrow_number,error_code")
    assert b"FORMULA_NOT_ALLOWED" in errors.content


def test_rejects_bad_file_and_returns_request_id(client: TestClient) -> None:
    response = client.post(
        "/api/v1/import-batches/product-sku",
        files={"file": ("data.csv", b"bad", "text/csv")},
        headers={"X-Request-ID": "api-bad-file"},
    )

    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_FILE_TYPE",
            "message": "Only .xlsx files are supported",
        },
        "request_id": "api-bad-file",
    }


def test_unknown_batch_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/import-batches/not-found")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BATCH_NOT_FOUND"
