from __future__ import annotations

import pytest
from pydantic import ValidationError

from channel_engine.observability import (
    StructuredEvent,
    StructuredEventStatus,
    StructuredEventType,
    metadata_is_safe,
)


def test_structured_event_accepts_only_redacted_metadata() -> None:
    event = StructuredEvent(
        event_type=StructuredEventType.MESSAGE_NORMALIZED,
        trace_id="trace-safe",
        status=StructuredEventStatus.SUCCESS,
        metadata={"content_length": 42, "channel_name": "fake"},
    )

    assert event.metadata["content_length"] == 42
    assert metadata_is_safe(event.model_dump(mode="json")["metadata"])

    for metadata in (
        {"token": "redacted-is-still-not-allowed-as-a-key"},
        {"customer_message": "private text"},
        {"header": "Bearer credential-material"},
        {"nested": {"cookie_value": "private"}},
    ):
        with pytest.raises(ValidationError):
            StructuredEvent(
                event_type=StructuredEventType.MESSAGE_RECEIVED,
                trace_id="trace-unsafe",
                status=StructuredEventStatus.INFO,
                metadata=metadata,
            )


def test_structured_event_is_versioned_and_immutable() -> None:
    event = StructuredEvent(
        event_type=StructuredEventType.CHANNEL_CONNECTED,
        trace_id="trace-versioned",
        status=StructuredEventStatus.SUCCESS,
    )

    assert event.observability_version == "1.0"
    with pytest.raises(ValidationError):
        event.status = StructuredEventStatus.FAILED
