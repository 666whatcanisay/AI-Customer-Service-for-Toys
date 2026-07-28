"""Frozen B-facing AI-response-feedback submission and history projection."""

import hashlib
import json

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_feedback.models import (
    AIResponseFeedback,
    AIResponseFeedbackIdempotency,
)
from app.ai_feedback.schemas import (
    AIResponseFeedbackCreate,
    AIResponseFeedbackCreated,
    AIResponseFeedbackListResponse,
    AIResponseFeedbackProjection,
    AIResponseFeedbackStatus,
    AIResponseFeedbackType,
)
from app.database import get_db
from app.customer_identity.service import require_active_bound_user
from app.errors import AppError


router = APIRouter(prefix="/api/v1/ai-response-feedback", tags=["ai-response-feedback"])
_REQUEST_METHOD = "POST"
_REQUEST_PATH = "/api/v1/ai-response-feedback"


def _fingerprint(payload: AIResponseFeedbackCreate) -> str:
    normalized = json.dumps(
        payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(normalized).hexdigest()}"


def _created_response(item: AIResponseFeedback) -> AIResponseFeedbackCreated:
    return AIResponseFeedbackCreated(feedback_id=item.feedback_id, status=item.status)


def _projection(item: AIResponseFeedback) -> AIResponseFeedbackProjection:
    return AIResponseFeedbackProjection(
        feedback_id=item.feedback_id,
        revision=item.revision,
        store_code=item.store_code,
        product_id=item.product_id,
        sku_id=item.sku_id,
        feedback_type=item.feedback_type,
        status=item.status,
        analysis_status=item.analysis_status,
        created_at=item.created_at,
    )


def _idempotency_record(
    session: Session, *, created_by: str, idempotency_key: str
) -> AIResponseFeedbackIdempotency | None:
    return session.scalar(
        select(AIResponseFeedbackIdempotency).where(
            AIResponseFeedbackIdempotency.request_method == _REQUEST_METHOD,
            AIResponseFeedbackIdempotency.request_path == _REQUEST_PATH,
            AIResponseFeedbackIdempotency.created_by == created_by,
            AIResponseFeedbackIdempotency.idempotency_key == idempotency_key,
        )
    )


def _replay_or_conflict(
    session: Session,
    receipt: AIResponseFeedbackIdempotency,
    fingerprint: str,
) -> AIResponseFeedbackCreated:
    if receipt.request_fingerprint != fingerprint:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_IDEMPOTENCY_CONFLICT",
            "Idempotency-Key is already bound to a different submission payload.",
            status_code=409,
        )
    item = session.get(AIResponseFeedback, receipt.feedback_record_id)
    if item is None:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_NOT_FOUND",
            "The stored idempotency receipt no longer has its feedback record.",
            status_code=404,
        )
    return _created_response(item)


@router.post("", response_model=AIResponseFeedbackCreated, status_code=201)
def create_ai_response_feedback(
    payload: AIResponseFeedbackCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: Session = Depends(get_db),
) -> AIResponseFeedbackCreated:
    """Create exactly one C-owned NEW record for a B explicit submission."""
    key = idempotency_key.strip()
    if not key:
        raise AppError(
            "AI_RESPONSE_FEEDBACK_VALIDATION_FAILED",
            "Idempotency-Key must not be blank.",
            status_code=422,
        )
    fingerprint = _fingerprint(payload)
    receipt = _idempotency_record(session, created_by=payload.created_by, idempotency_key=key)
    if receipt is not None:
        return _replay_or_conflict(session, receipt, fingerprint)

    require_active_bound_user(session, user_id=payload.created_by, store_code=payload.store_code)

    item = AIResponseFeedback(
        store_code=payload.store_code,
        product_id=payload.product_id,
        sku_id=payload.sku_id,
        question=payload.question,
        ai_answer=payload.ai_answer,
        final_answer=payload.final_answer,
        feedback_type=payload.feedback_type,
        feedback_note=payload.feedback_note,
        created_by=payload.created_by,
        status=AIResponseFeedbackStatus.NEW,
        analysis_status=AIResponseFeedbackStatus.NEW,
        redaction_version="v1-reminder-only",
    )
    session.add(item)
    session.flush()
    session.add(
        AIResponseFeedbackIdempotency(
            request_method=_REQUEST_METHOD,
            request_path=_REQUEST_PATH,
            created_by=payload.created_by,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            feedback_record_id=item.id,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        receipt = _idempotency_record(session, created_by=payload.created_by, idempotency_key=key)
        if receipt is None:
            raise AppError(
                "AI_RESPONSE_FEEDBACK_IDEMPOTENCY_CONFLICT",
                "The submission could not be safely reconciled after an idempotency conflict.",
                status_code=409,
            ) from None
        return _replay_or_conflict(session, receipt, fingerprint)
    session.refresh(item)
    return _created_response(item)


@router.get("", response_model=AIResponseFeedbackListResponse)
def list_ai_response_feedback(
    created_by: str = Query(min_length=1, max_length=128),
    feedback_type: AIResponseFeedbackType | None = None,
    status: AIResponseFeedbackStatus | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> AIResponseFeedbackListResponse:
    """Return B's minimum personal status projection; no audit or A evidence leaks."""
    statement = select(AIResponseFeedback).where(AIResponseFeedback.created_by == created_by)
    if feedback_type is not None:
        statement = statement.where(AIResponseFeedback.feedback_type == feedback_type)
    if status is not None:
        statement = statement.where(AIResponseFeedback.status == status)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.scalars(
        statement.order_by(AIResponseFeedback.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return AIResponseFeedbackListResponse(
        items=[_projection(item) for item in items], total=total, page=page, size=size
    )
