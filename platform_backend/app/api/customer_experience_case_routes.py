"""B-facing submission and personal status projection for experience cases."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.experience_cases.models import CustomerExperienceCase
from app.experience_cases.schemas import (
    CustomerExperienceCaseCreate,
    CustomerExperienceCaseCreated,
    CustomerExperienceCaseListResponse,
    CustomerExperienceCaseProjection,
    ExperienceCaseFeedbackType,
    ExperienceCaseReviewStatus,
)
from app.iam.dependencies import (
    Principal, effective_user_reference, ensure_store_code_access,
    get_current_principal,
)

router = APIRouter(prefix="/api/v1/customer-experience-cases", tags=["customer-experience-cases"])


def _created_response(item: CustomerExperienceCase) -> CustomerExperienceCaseCreated:
    return CustomerExperienceCaseCreated(
        case_id=item.case_id,
        revision=item.revision,
        review_status=item.review_status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _projection(item: CustomerExperienceCase) -> CustomerExperienceCaseProjection:
    return CustomerExperienceCaseProjection(
        case_id=item.case_id,
        revision=item.revision,
        store_code=item.store_code,
        product_id=item.product_id,
        sku_id=item.sku_id,
        feedback_type=item.feedback_type,
        review_status=item.review_status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("", response_model=CustomerExperienceCaseCreated, status_code=201)
def create_customer_experience_case(
    payload: CustomerExperienceCaseCreate,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> CustomerExperienceCaseCreated:
    ensure_store_code_access(session, principal, payload.store_code)
    item = CustomerExperienceCase(
        source_type="CUSTOMER_SERVICE_SUBMITTED",
        store_code=payload.store_code,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        question=payload.question,
        ai_answer=payload.ai_answer,
        final_answer=payload.final_answer,
        feedback_type=payload.feedback_type,
        created_by=effective_user_reference(principal, payload.created_by),
        review_status="NEW",
        redaction_version="v1-reminder-only",
        evaluation_status="NOT_EXPORTED",
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _created_response(item)


@router.get("", response_model=CustomerExperienceCaseListResponse)
def list_customer_experience_cases(
    created_by: str = Query(min_length=1, max_length=128),
    review_status: ExperienceCaseReviewStatus | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> CustomerExperienceCaseListResponse:
    created_by = effective_user_reference(principal, created_by)
    statement = select(CustomerExperienceCase).where(CustomerExperienceCase.created_by == created_by)
    if review_status is not None:
        statement = statement.where(CustomerExperienceCase.review_status == review_status)

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(CustomerExperienceCase.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return CustomerExperienceCaseListResponse(
        items=[_projection(item) for item in items], total=total, page=page, size=size
    )
