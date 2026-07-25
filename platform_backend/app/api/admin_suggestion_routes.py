"""Internal-test administration endpoints for customer-suggestion lifecycle handling."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.errors import AppError
from app.suggestions.models import CustomerSuggestion
from app.suggestions.schemas import (
    ALLOWED_STATUS_TRANSITIONS,
    AdminSuggestionListResponse,
    AdminSuggestionResponse,
    AdminSuggestionUpdate,
    SuggestionStatus,
)

router = APIRouter(prefix="/api/v1/admin/customer-suggestions", tags=["admin-customer-suggestions"])


def _response(item: CustomerSuggestion) -> AdminSuggestionResponse:
    return AdminSuggestionResponse(
        id=item.id,
        reporter_id=item.reporter_id,
        reporter_name=item.reporter_name,
        store_code=item.store_code,
        module_key=item.module_key,
        category=item.category,
        title=item.title,
        description=item.description,
        frequency=item.frequency,
        urgency=item.urgency,
        status=item.status,
        internal_note=item.internal_note,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=AdminSuggestionListResponse)
def list_customer_suggestions(
    status: SuggestionStatus | None = None,
    module_key: str | None = Query(default=None, max_length=64),
    store_code: str | None = Query(default=None, max_length=96),
    urgency: str | None = Query(default=None, max_length=32),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> AdminSuggestionListResponse:
    statement = select(CustomerSuggestion)
    if status:
        statement = statement.where(CustomerSuggestion.status == status)
    if module_key:
        statement = statement.where(CustomerSuggestion.module_key == module_key)
    if store_code:
        statement = statement.where(CustomerSuggestion.store_code == store_code)
    if urgency:
        statement = statement.where(CustomerSuggestion.urgency == urgency)
    if keyword:
        statement = statement.where(CustomerSuggestion.title.ilike(f"%{keyword}%"))

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(CustomerSuggestion.updated_at.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return AdminSuggestionListResponse(
        items=[_response(item) for item in items], page=page, size=size, total=total
    )


@router.patch("/{suggestion_id}", response_model=AdminSuggestionResponse)
def update_customer_suggestion(
    suggestion_id: str,
    payload: AdminSuggestionUpdate,
    session: Session = Depends(get_db),
) -> AdminSuggestionResponse:
    item = session.get(CustomerSuggestion, suggestion_id)
    if item is None:
        raise AppError("CUSTOMER_SUGGESTION_NOT_FOUND", "Customer suggestion was not found", status_code=404)

    if payload.status is not None:
        current_status = SuggestionStatus(item.status)
        if payload.status != current_status and payload.status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
            raise AppError(
                "SUGGESTION_INVALID_STATUS_TRANSITION",
                f"Cannot transition a suggestion from {current_status} to {payload.status}",
                status_code=409,
            )
        item.status = payload.status
    if "internal_note" in payload.model_fields_set:
        item.internal_note = payload.internal_note

    session.commit()
    session.refresh(item)
    return _response(item)
