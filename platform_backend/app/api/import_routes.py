"""Thin HTTP routes for the C-line product/SKU import workflow."""

import csv
import json
from io import StringIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.admin_pilot_store_routes import require_pilot_store
from app.admin.trial_governance import (
    TrialActor,
    TrialAuditReason,
    TrialRole,
    get_trial_reason,
    record_trial_audit_event,
    require_trial_roles,
)
from app.config import get_settings
from app.database import get_db
from app.errors import AppError
from app.ingestion.models import ImportBatch, ImportRow
from app.ingestion.repository import IngestionRepository
from app.ingestion.schemas import (
    BatchDetail,
    BatchListResponse,
    BatchSummary,
    ErrorCode,
    ImportRowListResponse,
    ImportRowResponse,
    ProductSkuPreflightResponse,
    RowStatus,
    ValidationIssue,
)
from app.ingestion.service import IngestionService

router = APIRouter(prefix="/api/v1", tags=["product-sku-ingestion"])
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "platform"
    / "templates"
    / "商品与SKU资料模板.xlsx"
)


def _repository(session: Session) -> IngestionRepository:
    return IngestionRepository(session)


def _summary(batch: ImportBatch) -> BatchSummary:
    return BatchSummary(
        id=batch.id,
        batch_id=batch.id,
        tenant_id=batch.tenant_id,
        target_store_code=batch.target_store_code,
        import_type=batch.import_type,
        original_filename=batch.original_filename,
        file_sha256=batch.file_sha256,
        status=batch.status,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        invalid_rows=batch.invalid_rows,
        duplicate_rows=batch.duplicate_rows,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        created_by=batch.created_by,
        error_message=batch.error_message,
    )


def _row_response(row: ImportRow) -> ImportRowResponse:
    return ImportRowResponse(
        id=row.id,
        batch_id=row.batch_id,
        source_row_number=row.source_row_number,
        raw_data=json.loads(row.raw_data_json),
        normalized_data=json.loads(row.normalized_data_json),
        row_hash=row.row_hash,
        validation_status=row.validation_status,
        errors=[ValidationIssue.model_validate(item) for item in json.loads(row.error_codes_json)],
        warnings=[
            ValidationIssue.model_validate(item) for item in json.loads(row.warning_codes_json)
        ],
    )


@router.get("/import-templates/product-sku")
def download_product_sku_template() -> FileResponse:
    if not TEMPLATE_PATH.is_file():
        raise AppError(
            ErrorCode.INVALID_TEMPLATE,
            "The product/SKU template is not available",
            status_code=503,
        )
    return FileResponse(
        TEMPLATE_PATH,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="商品与SKU资料模板.xlsx",
    )


@router.post(
    "/import-batches/product-sku/preflight",
    response_model=ProductSkuPreflightResponse,
)
async def preflight_product_sku(
    file: UploadFile = File(...),
    target_store_code: str | None = Form(default=None),
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> ProductSkuPreflightResponse:
    target = target_store_code.strip() if target_store_code else None
    if target:
        require_pilot_store(session, target)
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    service = IngestionService(
        None,
        max_upload_bytes=settings.max_upload_bytes,
        max_import_rows=settings.max_import_rows,
    )
    result = service.preflight_upload(
        filename=file.filename or "upload.xlsx",
        content_type=file.content_type,
        content=content,
        target_store_code=target,
    )
    record_trial_audit_event(
        session,
        actor=actor,
        action="PRODUCT_IMPORT_PREFLIGHT",
        resource_type="IMPORT_BATCH",
        resource_id=target or "unbound",
        outcome="SUCCESS" if result.can_import else "REJECTED",
        reason=reason,
        metadata={"valid_rows": result.valid_rows, "invalid_rows": result.invalid_rows},
    )
    session.commit()
    return result


@router.post("/import-batches/product-sku", response_model=BatchSummary, status_code=201)
async def upload_product_sku(
    file: UploadFile = File(...),
    created_by: str = Form("manual-import"),
    target_store_code: str | None = Form(default=None),
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> BatchSummary:
    target = target_store_code.strip() if target_store_code else None
    if target:
        require_pilot_store(session, target)
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    service = IngestionService(
        _repository(session),
        max_upload_bytes=settings.max_upload_bytes,
        max_import_rows=settings.max_import_rows,
    )
    batch = service.process_upload(
        filename=file.filename or "upload.xlsx",
        content_type=file.content_type,
        content=content,
        created_by=created_by,
        target_store_code=target,
    )
    record_trial_audit_event(
        session,
        actor=actor,
        action="PRODUCT_IMPORT_CREATE",
        resource_type="IMPORT_BATCH",
        resource_id=batch.id,
        outcome="SUCCESS" if batch.status != "REJECTED" else "REJECTED",
        reason=reason,
        metadata={"valid_rows": batch.valid_rows, "invalid_rows": batch.invalid_rows},
    )
    session.commit()
    return _summary(batch)


@router.get("/import-batches", response_model=BatchListResponse)
def list_import_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> BatchListResponse:
    items, total = _repository(session).list_batches(page=page, page_size=page_size)
    return BatchListResponse(
        items=[_summary(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/import-batches/{batch_id}", response_model=BatchDetail)
def get_import_batch(batch_id: str, session: Session = Depends(get_db)) -> BatchDetail:
    repository = _repository(session)
    batch = repository.get_batch(batch_id)
    if batch is None:
        raise AppError("BATCH_NOT_FOUND", "Import batch was not found", status_code=404)
    summary = _summary(batch).model_dump()
    return BatchDetail(**summary, staged_rows=repository.count_staged(batch_id))


@router.get("/import-batches/{batch_id}/rows", response_model=ImportRowListResponse)
def list_import_rows(
    batch_id: str,
    status: RowStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> ImportRowListResponse:
    repository = _repository(session)
    if repository.get_batch(batch_id) is None:
        raise AppError("BATCH_NOT_FOUND", "Import batch was not found", status_code=404)
    items, total = repository.list_rows(
        batch_id, status=status, page=page, page_size=page_size
    )
    return ImportRowListResponse(
        items=[_row_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/import-batches/{batch_id}/errors")
def download_error_report(batch_id: str, session: Session = Depends(get_db)) -> Response:
    repository = _repository(session)
    if repository.get_batch(batch_id) is None:
        raise AppError("BATCH_NOT_FOUND", "Import batch was not found", status_code=404)
    rows, _ = repository.list_rows(batch_id, status=None, page=1, page_size=100000)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["row_number", "error_code", "field", "raw_value", "message", "suggestion"]
    )
    for row in rows:
        for issue in json.loads(row.error_codes_json):
            writer.writerow(
                [
                    issue["row_number"],
                    issue["error_code"],
                    issue.get("field") or "",
                    str(issue.get("raw_value") or ""),
                    issue["message"],
                    issue["suggestion"],
                ]
            )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="import-{batch_id}-errors.csv"'
        },
    )
