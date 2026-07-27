"""Content-free B event intake plus C-to-A/Admin aggregate efficiency summaries."""

import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.customer_efficiency.models import CustomerEfficiencyEvent, utc_now
from app.customer_efficiency.schemas import (
    CustomerEfficiencyEventCreate,
    CustomerEfficiencyEventCreated,
    CustomerEfficiencySummary,
)
from app.customer_efficiency.service import build_summary
from app.database import get_db
from app.errors import AppError


event_router = APIRouter(prefix="/api/v1/customer-efficiency-events", tags=["customer-efficiency"])
ai_quality_router = APIRouter(
    prefix="/api/v1/admin/ai-quality/customer-efficiency", tags=["customer-efficiency-ai-quality"]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/customer-efficiency", tags=["admin-customer-efficiency"]
)
_REQUEST_PATH = "/api/v1/customer-efficiency-events"


def _fingerprint(payload: CustomerEfficiencyEventCreate) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _created(item: CustomerEfficiencyEvent) -> CustomerEfficiencyEventCreated:
    return CustomerEfficiencyEventCreated(
        event_id=item.event_id,
        event_type=item.event_type,
        occurred_at=item.occurred_at,
        created_at=item.created_at,
    )


def _replay_or_conflict(
    session: Session, *, idempotency_key: str, fingerprint: str
) -> CustomerEfficiencyEventCreated:
    item = session.scalar(
        select(CustomerEfficiencyEvent).where(CustomerEfficiencyEvent.idempotency_key == idempotency_key)
    )
    if item is None:
        raise AppError(
            "CUSTOMER_EFFICIENCY_IDEMPOTENCY_CONFLICT",
            "The event could not be safely reconciled after an idempotency conflict.",
            status_code=409,
        )
    if item.request_fingerprint != fingerprint:
        raise AppError(
            "CUSTOMER_EFFICIENCY_IDEMPOTENCY_CONFLICT",
            "Idempotency-Key is already bound to a different event payload.",
            status_code=409,
        )
    return _created(item)


def _summary(
    window_start: datetime | None, window_end: datetime | None, session: Session
) -> CustomerEfficiencySummary:
    if window_start is not None and window_start.tzinfo is None:
        raise AppError(
            "CUSTOMER_EFFICIENCY_INVALID_WINDOW", "window_start must include a timezone offset.", status_code=422
        )
    if window_end is not None and window_end.tzinfo is None:
        raise AppError(
            "CUSTOMER_EFFICIENCY_INVALID_WINDOW", "window_end must include a timezone offset.", status_code=422
        )
    if window_start is not None and window_end is not None and window_end <= window_start:
        raise AppError(
            "CUSTOMER_EFFICIENCY_INVALID_WINDOW", "window_end must be later than window_start.", status_code=422
        )
    return build_summary(session, window_start=window_start, window_end=window_end)


@event_router.post("", response_model=CustomerEfficiencyEventCreated, status_code=201)
def create_customer_efficiency_event(
    payload: CustomerEfficiencyEventCreate,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: Session = Depends(get_db),
) -> CustomerEfficiencyEventCreated:
    """Persist one content-free B event; same key and payload replays without a second row."""
    key = idempotency_key.strip()
    if not key:
        raise AppError(
            "CUSTOMER_EFFICIENCY_VALIDATION_FAILED", "Idempotency-Key must not be blank.", status_code=422
        )
    fingerprint = _fingerprint(payload)
    existing = session.scalar(
        select(CustomerEfficiencyEvent).where(CustomerEfficiencyEvent.idempotency_key == key)
    )
    if existing is not None:
        response.status_code = 200
        return _replay_or_conflict(session, idempotency_key=key, fingerprint=fingerprint)

    item = CustomerEfficiencyEvent(
        event_type=payload.event_type,
        occurred_at=payload.occurred_at or utc_now(),
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        response.status_code = 200
        return _replay_or_conflict(session, idempotency_key=key, fingerprint=fingerprint)
    session.refresh(item)
    return _created(item)


@ai_quality_router.get("/summary", response_model=CustomerEfficiencySummary)
def get_ai_customer_efficiency_summary(
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    session: Session = Depends(get_db),
) -> CustomerEfficiencySummary:
    """C-to-A aggregate-only efficiency summary; no event detail or customer content."""
    return _summary(window_start, window_end, session)


@admin_router.get("/summary", response_model=CustomerEfficiencySummary)
def get_admin_customer_efficiency_summary(
    window_start: datetime | None = Query(default=None),
    window_end: datetime | None = Query(default=None),
    session: Session = Depends(get_db),
) -> CustomerEfficiencySummary:
    """C Admin dashboard projection with the same aggregate-only metric definitions."""
    return _summary(window_start, window_end, session)
