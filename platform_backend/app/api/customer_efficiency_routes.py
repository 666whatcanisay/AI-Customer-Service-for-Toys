"""B-facing immutable, privacy-minimized customer-efficiency event endpoint."""

import hashlib
import json

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_feedback.models import AIResponseFeedback
from app.customer_efficiency.models import CustomerEfficiencyEvent, CustomerEfficiencyEventIdempotency
from app.customer_efficiency.schemas import (
    CustomerEfficiencyEventAccepted,
    CustomerEfficiencyEventCreate,
    CustomerEfficiencyEventType,
    SCHEMA_VERSION,
    TERMINAL_EVENT_TYPES,
)
from app.customer_identity.service import require_active_bound_user
from app.database import get_db
from app.errors import AppError


router = APIRouter(prefix="/api/v1/customer-efficiency", tags=["customer-efficiency"])
_REQUEST_METHOD = "POST"
_REQUEST_PATH = "/api/v1/customer-efficiency/events"


def _fingerprint(payload: CustomerEfficiencyEventCreate) -> str:
    normalized = json.dumps(
        payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(normalized).hexdigest()}"


def _acknowledgement(item: CustomerEfficiencyEvent) -> CustomerEfficiencyEventAccepted:
    return CustomerEfficiencyEventAccepted(
        event_id=item.event_id,
        event_type=item.event_type,
        created_at=item.created_at,
        accepted=True,
    )


def _existing_receipt(
    session: Session, *, operator_id: str, idempotency_key: str
) -> CustomerEfficiencyEventIdempotency | None:
    return session.scalar(
        select(CustomerEfficiencyEventIdempotency).where(
            CustomerEfficiencyEventIdempotency.request_method == _REQUEST_METHOD,
            CustomerEfficiencyEventIdempotency.request_path == _REQUEST_PATH,
            CustomerEfficiencyEventIdempotency.operator_id == operator_id,
            CustomerEfficiencyEventIdempotency.idempotency_key == idempotency_key,
        )
    )


def _replay_or_conflict(
    session: Session, receipt: CustomerEfficiencyEventIdempotency, fingerprint: str
) -> CustomerEfficiencyEventAccepted:
    if receipt.request_fingerprint != fingerprint:
        raise AppError(
            "CUSTOMER_EFFICIENCY_IDEMPOTENCY_CONFLICT",
            "Idempotency-Key is already bound to a different event payload.",
            status_code=409,
        )
    item = session.get(CustomerEfficiencyEvent, receipt.event_record_id)
    if item is None:
        raise AppError(
            "CUSTOMER_EFFICIENCY_EVENT_NOT_FOUND",
            "The stored event receipt no longer has its event record.",
            status_code=404,
        )
    return _acknowledgement(item)


def _validate_sequence(session: Session, payload: CustomerEfficiencyEventCreate) -> None:
    if payload.event_type == CustomerEfficiencyEventType.AI_REQUEST:
        duplicate = session.scalar(
            select(CustomerEfficiencyEvent.id).where(
                CustomerEfficiencyEvent.event_type == CustomerEfficiencyEventType.AI_REQUEST,
                CustomerEfficiencyEvent.interaction_id == payload.interaction_id,
            )
        )
        if duplicate is not None:
            raise AppError(
                "CUSTOMER_EFFICIENCY_EVENT_SEQUENCE_INVALID",
                "This AI interaction already has a request event.",
                status_code=409,
            )
    if payload.event_type in TERMINAL_EVENT_TYPES:
        request_exists = session.scalar(
            select(CustomerEfficiencyEvent.id).where(
                CustomerEfficiencyEvent.event_type == CustomerEfficiencyEventType.AI_REQUEST,
                CustomerEfficiencyEvent.interaction_id == payload.interaction_id,
            )
        )
        terminal_exists = session.scalar(
            select(CustomerEfficiencyEvent.id).where(
                CustomerEfficiencyEvent.event_type.in_(TERMINAL_EVENT_TYPES),
                CustomerEfficiencyEvent.interaction_id == payload.interaction_id,
            )
        )
        if request_exists is None or terminal_exists is not None:
            raise AppError(
                "CUSTOMER_EFFICIENCY_EVENT_SEQUENCE_INVALID",
                "Terminal events require exactly one earlier AI request and no earlier terminal result.",
                status_code=409,
            )


def _validate_feedback_reference(session: Session, payload: CustomerEfficiencyEventCreate) -> None:
    if payload.event_type != CustomerEfficiencyEventType.AI_FEEDBACK_SUBMIT:
        return
    feedback = session.scalar(
        select(AIResponseFeedback).where(AIResponseFeedback.feedback_id == payload.feedback_id)
    )
    if (
        feedback is None
        or feedback.created_by != payload.operator_id
        or feedback.store_code != payload.store_code
    ):
        raise AppError(
            "CUSTOMER_EFFICIENCY_FEEDBACK_REFERENCE_INVALID",
            "feedback_id must reference the selected user's feedback in the selected store.",
            status_code=422,
        )


@router.post("/events", response_model=CustomerEfficiencyEventAccepted, status_code=201)
def create_customer_efficiency_event(
    payload: CustomerEfficiencyEventCreate,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: Session = Depends(get_db),
) -> CustomerEfficiencyEventAccepted:
    key = idempotency_key.strip()
    if not key:
        raise AppError(
            "CUSTOMER_EFFICIENCY_EVENT_VALIDATION_FAILED",
            "Idempotency-Key must not be blank.",
            status_code=422,
        )
    if payload.schema_version != SCHEMA_VERSION:
        raise AppError(
            "CUSTOMER_EFFICIENCY_SCHEMA_VERSION_UNSUPPORTED",
            "schema_version is not supported by this endpoint.",
            status_code=400,
        )
    fingerprint = _fingerprint(payload)
    receipt = _existing_receipt(session, operator_id=payload.operator_id, idempotency_key=key)
    if receipt is not None:
        response.status_code = 200
        return _replay_or_conflict(session, receipt, fingerprint)

    require_active_bound_user(session, user_id=payload.operator_id, store_code=payload.store_code)
    _validate_sequence(session, payload)
    _validate_feedback_reference(session, payload)
    item = CustomerEfficiencyEvent(**payload.model_dump(mode="json"))
    session.add(item)
    session.flush()
    session.add(
        CustomerEfficiencyEventIdempotency(
            request_method=_REQUEST_METHOD,
            request_path=_REQUEST_PATH,
            operator_id=payload.operator_id,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            event_record_id=item.id,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        receipt = _existing_receipt(session, operator_id=payload.operator_id, idempotency_key=key)
        if receipt is not None:
            response.status_code = 200
            return _replay_or_conflict(session, receipt, fingerprint)
        raise AppError(
            "CUSTOMER_EFFICIENCY_EVENT_SEQUENCE_INVALID",
            "The event could not be safely accepted after a concurrent sequence conflict.",
            status_code=409,
        ) from None
    session.refresh(item)
    return _acknowledgement(item)
