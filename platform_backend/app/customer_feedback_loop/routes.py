"""B event-capture and C operations routes for Customer Feedback Loop V1."""

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.customer_feedback_loop.models import AIInteractionEvent, AIProblem
from app.customer_feedback_loop.schemas import (
    AdminInteractionEventList,
    AIProblemList,
    AIProblemProjection,
    AIProblemStatus,
    AIProblemStatusUpdate,
    AIProblemType,
    InteractionActionType,
    InteractionEventCreate,
    InteractionEventReceipt,
    KnowledgeTaskCreate,
    KnowledgeTaskProjection,
    KnowledgeTaskStatusUpdate,
    KnowledgeTaskVerification,
)
from app.customer_feedback_loop.service import (
    admin_event_projection,
    create_interaction_event,
    create_knowledge_task,
    event_receipt,
    find_idempotent_event,
    problem_or_404,
    problem_projection,
    task_or_404,
    update_knowledge_task_status,
    update_problem_status,
    verify_knowledge_task,
    task_projection,
)
from app.database import get_db
from app.errors import AppError
from app.iam.dependencies import (
    Principal, effective_user_reference, ensure_store_code_access,
    get_current_principal,
)


customer_router = APIRouter(
    prefix="/api/v1/ai-interaction-events", tags=["ai-interaction-events"]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/ai-feedback-loop", tags=["admin-ai-feedback-loop"]
)


@customer_router.post("", response_model=InteractionEventReceipt, status_code=201)
def record_interaction_event(
    payload: InteractionEventCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> InteractionEventReceipt:
    key = idempotency_key.strip()
    if not key:
        raise AppError(
            "AI_INTERACTION_EVENT_VALIDATION_FAILED",
            "Idempotency-Key must not be blank.",
            status_code=422,
        )
    ensure_store_code_access(session, principal, payload.store_code)
    payload = payload.model_copy(update={
        "created_by": effective_user_reference(principal, payload.created_by)
    })
    event = create_interaction_event(session, payload, key)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        event = find_idempotent_event(session, created_by=payload.created_by, idempotency_key=key)
        if event is None:
            raise AppError(
                "AI_INTERACTION_EVENT_IDEMPOTENCY_CONFLICT",
                "The event could not be reconciled after an idempotency conflict.",
                status_code=409,
            ) from None
        event = create_interaction_event(session, payload, key)
    session.refresh(event)
    return event_receipt(event)


@admin_router.get("/events", response_model=AdminInteractionEventList)
def list_interaction_events(
    action_type: InteractionActionType | None = None,
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=200),
    session: Session = Depends(get_db),
) -> AdminInteractionEventList:
    statement = select(AIInteractionEvent)
    if action_type is not None:
        statement = statement.where(AIInteractionEvent.action_type == action_type)
    if store_code:
        statement = statement.where(AIInteractionEvent.store_code == store_code)
    if product_id:
        statement = statement.where(AIInteractionEvent.product_id == product_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.scalars(
        statement.order_by(AIInteractionEvent.occurred_at.desc()).limit(limit)
    ).all()
    return AdminInteractionEventList(
        items=[admin_event_projection(row) for row in rows], total=total
    )


@admin_router.get("/issues", response_model=AIProblemList)
def list_ai_problems(
    status: AIProblemStatus | None = None,
    issue_type: AIProblemType | None = None,
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=200),
    session: Session = Depends(get_db),
) -> AIProblemList:
    statement = select(AIProblem)
    if status is not None:
        statement = statement.where(AIProblem.status == status)
    if issue_type is not None:
        statement = statement.where(AIProblem.issue_type == issue_type)
    if store_code:
        statement = statement.where(AIProblem.store_code == store_code)
    if product_id:
        statement = statement.where(AIProblem.product_id == product_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = session.scalars(
        statement.order_by(AIProblem.last_seen_at.desc()).limit(limit)
    ).all()
    return AIProblemList(
        items=[problem_projection(session, row) for row in rows], total=total
    )


@admin_router.patch(
    "/issues/{problem_id}/status", response_model=AIProblemProjection
)
def change_ai_problem_status(
    problem_id: str,
    payload: AIProblemStatusUpdate,
    session: Session = Depends(get_db),
) -> AIProblemProjection:
    problem = update_problem_status(session, problem_or_404(session, problem_id), payload)
    session.commit()
    session.refresh(problem)
    return problem_projection(session, problem)


@admin_router.post(
    "/issues/{problem_id}/knowledge-tasks",
    response_model=KnowledgeTaskProjection,
    status_code=201,
)
def add_knowledge_task(
    problem_id: str,
    payload: KnowledgeTaskCreate,
    session: Session = Depends(get_db),
) -> KnowledgeTaskProjection:
    task = create_knowledge_task(
        session, problem_or_404(session, problem_id), payload
    )
    session.commit()
    session.refresh(task)
    projection = task_projection(task)
    assert projection is not None
    return projection


@admin_router.patch(
    "/knowledge-tasks/{task_id}/status", response_model=KnowledgeTaskProjection
)
def change_knowledge_task_status(
    task_id: str,
    payload: KnowledgeTaskStatusUpdate,
    session: Session = Depends(get_db),
) -> KnowledgeTaskProjection:
    task = update_knowledge_task_status(session, task_or_404(session, task_id), payload)
    session.commit()
    session.refresh(task)
    projection = task_projection(task)
    assert projection is not None
    return projection


@admin_router.post(
    "/knowledge-tasks/{task_id}/verifications",
    response_model=KnowledgeTaskProjection,
)
def record_knowledge_task_verification(
    task_id: str,
    payload: KnowledgeTaskVerification,
    session: Session = Depends(get_db),
) -> KnowledgeTaskProjection:
    task = verify_knowledge_task(session, task_or_404(session, task_id), payload)
    session.commit()
    session.refresh(task)
    projection = task_projection(task)
    assert projection is not None
    return projection
