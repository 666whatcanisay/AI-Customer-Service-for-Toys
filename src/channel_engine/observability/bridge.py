from __future__ import annotations

from channel_engine.models import Event, EventType

from .models import StructuredEvent, StructuredEventStatus, StructuredEventType


_EVENT_MAPPING: dict[
    EventType, tuple[StructuredEventType, StructuredEventStatus]
] = {
    EventType.MESSAGE_RECEIVED: (
        StructuredEventType.MESSAGE_RECEIVED,
        StructuredEventStatus.INFO,
    ),
    EventType.DECISION_CREATED: (
        StructuredEventType.DECISION_CREATED,
        StructuredEventStatus.SUCCESS,
    ),
    EventType.DECISION_WAITING_APPROVAL: (
        StructuredEventType.APPROVAL_REQUIRED,
        StructuredEventStatus.PENDING,
    ),
    EventType.DECISION_APPROVED: (
        StructuredEventType.APPROVAL_GRANTED,
        StructuredEventStatus.SUCCESS,
    ),
    EventType.DECISION_REJECTED: (
        StructuredEventType.APPROVAL_REJECTED,
        StructuredEventStatus.BLOCKED,
    ),
    EventType.EXECUTION_STARTED: (
        StructuredEventType.EXECUTION_STARTED,
        StructuredEventStatus.PENDING,
    ),
    EventType.EXECUTION_SUCCEEDED: (
        StructuredEventType.EXECUTION_SUCCESS,
        StructuredEventStatus.SUCCESS,
    ),
    EventType.EXECUTION_FAILED: (
        StructuredEventType.EXECUTION_FAILED,
        StructuredEventStatus.FAILED,
    ),
    EventType.EXECUTION_UNKNOWN: (
        StructuredEventType.EXECUTION_UNKNOWN,
        StructuredEventStatus.UNKNOWN,
    ),
    EventType.RECEIPT_RECORDED: (
        StructuredEventType.RECEIPT_CREATED,
        StructuredEventStatus.SUCCESS,
    ),
}

_SAFE_METADATA_KEYS = {
    "action",
    "attempt",
    "channel_name",
    "error_code",
    "outcome",
    "reason_code",
    "requires_approval",
}


def project_domain_event(event: Event) -> StructuredEvent | None:
    mapping = _EVENT_MAPPING.get(event.event_type)
    if mapping is None:
        return None
    event_type, status = mapping
    payload = event.payload
    aggregate = event.aggregate_type.casefold()
    return StructuredEvent(
        event_id=f"ops-{event.event_id}",
        event_type=event_type,
        trace_id=event.correlation_id,
        message_id=(
            event.aggregate_id if aggregate == "message" else event.correlation_id
        ),
        conversation_id=_text(payload.get("conversation_id")),
        request_id=(
            f"decision-request-{event.correlation_id}"
            if event.event_type
            in {EventType.DECISION_CREATED, EventType.DECISION_WAITING_APPROVAL}
            else None
        ),
        decision_id=(
            event.aggregate_id
            if aggregate == "decision"
            else _text(payload.get("decision_id"))
        ),
        approval_id=_text(payload.get("approval_id")),
        execution_id=(
            event.aggregate_id
            if aggregate == "execution"
            else _text(payload.get("execution_id"))
        ),
        receipt_id=(
            event.aggregate_id
            if aggregate == "receipt"
            else _text(payload.get("receipt_id"))
        ),
        store_id=_text(payload.get("store_id")),
        timestamp=event.occurred_at,
        status=status,
        metadata={
            key: value
            for key, value in payload.items()
            if key in _SAFE_METADATA_KEYS
        },
    )


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["project_domain_event"]
