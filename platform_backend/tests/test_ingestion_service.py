from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.ingestion.models import ImportRow, StagedProductSku
from app.ingestion.repository import IngestionRepository
from app.ingestion.schemas import BatchStatus, ErrorCode, ReviewStatus, RowStatus
from app.ingestion.service import IngestionService
from conftest import valid_row, workbook_bytes

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FIXTURES = Path(__file__).parent / "fixtures"


def service(session: Session, *, max_bytes: int = 5 * 1024 * 1024, max_rows: int = 1000):
    return IngestionService(
        IngestionRepository(session),
        max_upload_bytes=max_bytes,
        max_import_rows=max_rows,
    )


def process(session: Session, content: bytes):
    return service(session).process_upload(
        filename="synthetic.xlsx",
        content_type=XLSX_MIME,
        content=content,
        created_by="pytest",
    )


def test_valid_rows_only_enter_review_staging(session: Session) -> None:
    content = (FIXTURES / "product_sku_valid_10.xlsx").read_bytes()

    batch = process(session, content)

    assert batch.status == BatchStatus.READY_FOR_REVIEW
    assert (batch.total_rows, batch.valid_rows, batch.invalid_rows) == (10, 10, 0)
    staged = list(session.scalars(select(StagedProductSku)))
    assert len(staged) == 10
    assert {item.review_status for item in staged} == {ReviewStatus.PENDING_REVIEW}
    assert {item.external_system for item in staged} == {"MANUAL_EXCEL"}


def test_duplicate_and_conflict_rows_are_not_staged(session: Session) -> None:
    first = valid_row(1)
    duplicate = dict(first)
    conflict = dict(first)
    conflict["material"] = "冲突材质"

    batch = process(session, workbook_bytes([first, duplicate, conflict]))

    statuses = list(
        session.scalars(select(ImportRow.validation_status).order_by(ImportRow.id))
    )
    assert statuses == [RowStatus.CONFLICT, RowStatus.DUPLICATE, RowStatus.CONFLICT]
    assert batch.valid_rows == 0
    assert batch.invalid_rows == 2
    assert batch.duplicate_rows == 1
    assert session.scalar(select(func.count()).select_from(StagedProductSku)) == 0


def test_invalid_row_does_not_become_a_duplicate(session: Session) -> None:
    invalid = valid_row(1)
    invalid["product_name"] = None

    batch = process(session, workbook_bytes([invalid, dict(invalid)]))

    statuses = list(session.scalars(select(ImportRow.validation_status)))
    assert statuses == [RowStatus.INVALID, RowStatus.INVALID]
    assert batch.invalid_rows == 2
    assert batch.duplicate_rows == 0


def test_multiple_tenants_make_the_entire_batch_conflicted(session: Session) -> None:
    rows = [valid_row(1), valid_row(2)]
    rows[1]["tenant_id"] = "another-tenant"

    batch = process(session, workbook_bytes(rows))

    assert batch.tenant_id == "MULTIPLE"
    assert batch.status == BatchStatus.REJECTED
    assert batch.valid_rows == 0
    assert batch.invalid_rows == 2
    assert session.scalar(select(func.count()).select_from(StagedProductSku)) == 0


def test_hidden_data_sheet_is_rejected(session: Session) -> None:
    content = workbook_bytes([valid_row()], hide_data_sheet=True)

    with pytest.raises(AppError) as captured:
        process(session, content)

    assert captured.value.code == ErrorCode.INVALID_TEMPLATE


def test_original_filename_is_reduced_to_a_safe_basename(session: Session) -> None:
    batch = service(session).process_upload(
        filename="../../synthetic.xlsx",
        content_type=XLSX_MIME,
        content=workbook_bytes([valid_row()]),
        created_by="pytest",
    )

    assert batch.original_filename == "synthetic.xlsx"


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_code"),
    [
        ("data.csv", "text/csv", b"csv", ErrorCode.UNSUPPORTED_FILE_TYPE),
        ("data.xlsx", "application/zip", b"zip", ErrorCode.UNSUPPORTED_FILE_TYPE),
        ("data.xlsx", XLSX_MIME, b"not-an-xlsx", ErrorCode.INVALID_TEMPLATE),
    ],
)
def test_file_checks_have_stable_errors(
    session: Session,
    filename: str,
    content_type: str,
    content: bytes,
    expected_code: ErrorCode,
) -> None:
    with pytest.raises(AppError) as captured:
        service(session).process_upload(
            filename=filename,
            content_type=content_type,
            content=content,
            created_by="pytest",
        )

    assert captured.value.code == expected_code


def test_size_row_limit_template_and_formula_guards(session: Session) -> None:
    with pytest.raises(AppError) as too_large:
        service(session, max_bytes=3).process_upload(
            filename="data.xlsx",
            content_type=XLSX_MIME,
            content=b"four",
            created_by="pytest",
        )
    assert too_large.value.code == ErrorCode.FILE_TOO_LARGE

    with pytest.raises(AppError) as too_many:
        service(session, max_rows=1).process_upload(
            filename="data.xlsx",
            content_type=XLSX_MIME,
            content=workbook_bytes([valid_row(1), valid_row(2)]),
            created_by="pytest",
        )
    assert too_many.value.code == ErrorCode.TOO_MANY_ROWS

    with pytest.raises(AppError) as invalid_template:
        process(session, workbook_bytes([valid_row()], headers=["wrong"]))
    assert invalid_template.value.code == ErrorCode.INVALID_TEMPLATE

    formula_batch = process(
        session,
        workbook_bytes([valid_row()], formula_cells={"F3": '="synthetic"'}),
    )
    formula_row = session.scalar(
        select(ImportRow).where(ImportRow.batch_id == formula_batch.id)
    )
    assert formula_row is not None
    assert formula_row.validation_status == RowStatus.INVALID
    assert ErrorCode.FORMULA_NOT_ALLOWED.value in formula_row.error_codes_json
    assert session.scalar(select(func.count()).select_from(StagedProductSku)) == 0
