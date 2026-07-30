"""Frozen C Admin HTTP interface for product-knowledge import V1."""

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.product_knowledge_import.schemas import (
    ImportAcceptedResponse,
    MergePreviewResponse,
    ProductKnowledgePreflightResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.product_knowledge_import.service import ProductKnowledgeImportService


router = APIRouter(
    prefix="/api/v1/admin/product-knowledge-imports",
    tags=["product-knowledge-import"],
)


def _service(session: Session) -> ProductKnowledgeImportService:
    settings = get_settings()
    return ProductKnowledgeImportService(
        session,
        max_upload_bytes=settings.max_upload_bytes,
        max_rows=settings.max_import_rows,
    )


@router.post("", response_model=ImportAcceptedResponse, status_code=201)
async def upload_product_knowledge(
    response: Response,
    store_ref: int = Form(...),
    template_type: str = Form(...),
    file: UploadFile = File(...),
    operator: str = Form(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> ImportAcceptedResponse:
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    result, replayed = _service(session).upload(
        store_ref=store_ref,
        template_type=template_type,
        filename=file.filename or "upload.xlsx",
        content_type=file.content_type,
        content=content,
        operator=operator,
        idempotency_key=idempotency_key,
    )
    if replayed:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return result

@router.get("/{batch_id}/preflight", response_model=ProductKnowledgePreflightResponse)
def get_product_knowledge_preflight(
    batch_id: str,
    session: Session = Depends(get_db),
) -> ProductKnowledgePreflightResponse:
    return _service(session).preflight(batch_id)


@router.get("/{batch_id}/merge-preview", response_model=MergePreviewResponse)
def get_product_knowledge_merge_preview(
    batch_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_db),
) -> MergePreviewResponse:
    return _service(session).merge_preview(batch_id, page=page, page_size=page_size)


@router.post(
    "/{batch_id}/change-sets/{change_set_id}/reviews",
    response_model=ReviewResponse,
    status_code=201,
)
def review_product_knowledge_change_set(
    batch_id: str,
    change_set_id: str,
    request: ReviewRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> ReviewResponse:
    result, replayed = _service(session).review(
        batch_id=batch_id,
        change_set_id=change_set_id,
        request=request,
        idempotency_key=idempotency_key,
    )
    if replayed:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return result
