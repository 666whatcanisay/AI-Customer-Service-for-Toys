"""Customer-facing suggestion submission and read-only reporter history."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.suggestions.models import CustomerSuggestion
from app.suggestions.schemas import SuggestionCreate, SuggestionListResponse, SuggestionResponse

router = APIRouter(prefix="/api/v1/customer-suggestions", tags=["customer-suggestions"])


def _response(item: CustomerSuggestion) -> SuggestionResponse:
    return SuggestionResponse(
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
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("", response_model=SuggestionResponse, status_code=201)
def create_customer_suggestion(
    payload: SuggestionCreate,
    session: Session = Depends(get_db),
) -> SuggestionResponse:
    item = CustomerSuggestion(
        reporter_id=payload.reporter_id,
        reporter_name=payload.reporter_name,
        store_code=payload.store_code,
        module_key=payload.module_key,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        frequency=payload.frequency,
        urgency=payload.urgency,
        status="SUBMITTED",
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _response(item)


@router.get("", response_model=SuggestionListResponse)
def list_reporter_suggestions(
    reporter_id: str = Query(min_length=1, max_length=64),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> SuggestionListResponse:
    statement = select(CustomerSuggestion).where(CustomerSuggestion.reporter_id == reporter_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(CustomerSuggestion.created_at.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return SuggestionListResponse(items=[_response(item) for item in items], page=page, size=size, total=total)
