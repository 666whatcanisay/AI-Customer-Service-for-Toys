from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from threading import Event as StopEvent
from threading import Lock
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from channel_engine.gateway import CONTRACT_VERSION, Event as GatewayEvent
from channel_engine.models import OutboxState
from channel_engine.models.entities import utc_now
from channel_engine.storage import OutboxItem, SqlAlchemyUnitOfWork


class EventPublisher(Protocol):
    def publish(self, item: OutboxItem) -> None:
        """Publish with ``publish_key`` as the transport idempotency key."""


class FakePublishError(RuntimeError):
    pass


class FakePublishConflict(ValueError):
    pass


class PublishedEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    publish_key: str
    topic: str
    payload: dict[str, object]


class FakeEventPublisher:
    """In-memory idempotent publisher with deterministic failure injection."""

    def __init__(self, *, failures_before_success: int = 0) -> None:
        if failures_before_success < 0:
            raise ValueError("failures_before_success cannot be negative")
        self.failures_before_success = failures_before_success
        self.call_count = 0
        self._attempts: dict[str, int] = {}
        self._published: dict[str, PublishedEvent] = {}
        self._lock = Lock()

    @property
    def published_events(self) -> list[PublishedEvent]:
        with self._lock:
            return list(self._published.values())

    def attempts_for(self, event_id: str) -> int:
        with self._lock:
            return self._attempts.get(event_id, 0)

    def publish(self, item: OutboxItem) -> None:
        with self._lock:
            proposed = PublishedEvent(
                event_id=item.event_id,
                publish_key=item.publish_key,
                topic=item.topic,
                payload=item.payload,
            )
            existing = self._published.get(item.publish_key)
            if existing is not None:
                if existing != proposed:
                    raise FakePublishConflict(
                        f"event_id was reused with different content: {item.event_id}"
                    )
                return
            self.call_count += 1
            attempt = self._attempts.get(item.publish_key, 0) + 1
            self._attempts[item.publish_key] = attempt
            if attempt <= self.failures_before_success:
                raise FakePublishError(
                    f"simulated publish failure {attempt} for {item.event_id}"
                )
            self._published[item.publish_key] = proposed


class OutboxPublishResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outbox_id: str
    event_id: str
    status: OutboxState
    attempt_count: int
    error: str | None = None
    lease_lost: bool = False


class OutboxPublisher:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        publisher: EventPublisher,
        publisher_id: str,
        *,
        lease_duration: timedelta = timedelta(seconds=30),
        max_attempts: int = 5,
        base_retry_delay: timedelta = timedelta(seconds=1),
        max_retry_delay: timedelta = timedelta(minutes=5),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not publisher_id.strip():
            raise ValueError("publisher_id is required")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if base_retry_delay <= timedelta(0) or max_retry_delay < base_retry_delay:
            raise ValueError("retry delays are invalid")
        self._uow_factory = uow_factory
        self._publisher = publisher
        self.publisher_id = publisher_id.strip()
        self.lease_duration = lease_duration
        self.max_attempts = max_attempts
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self._clock = clock

    def run_once(self) -> OutboxPublishResult | None:
        now = self._clock()
        with self._uow_factory() as uow:
            item = uow.require_repository().claim_outbox(
                self.publisher_id,
                now,
                now + self.lease_duration,
            )
        if item is None:
            return None
        assert item.lease_token is not None

        try:
            publish_item = self._as_gateway_contract_event(item)
            self._publisher.publish(publish_item)
        except Exception as exc:
            failed_at = self._clock()
            terminal = item.attempt_count >= self.max_attempts
            retry_delay = min(
                self.base_retry_delay * (2 ** (item.attempt_count - 1)),
                self.max_retry_delay,
            )
            next_attempt_at = failed_at if terminal else failed_at + retry_delay
            error = f"{type(exc).__name__}: {exc}"
            with self._uow_factory() as uow:
                updated = uow.require_repository().fail_outbox_publish(
                    item.outbox_id,
                    self.publisher_id,
                    item.lease_token,
                    error,
                    failed_at,
                    next_attempt_at,
                    terminal,
                )
            actual_status = (
                OutboxState.PROCESSING
                if not updated
                else (OutboxState.FAILED if terminal else OutboxState.PENDING)
            )
            return OutboxPublishResult(
                outbox_id=item.outbox_id,
                event_id=item.event_id,
                status=actual_status,
                attempt_count=item.attempt_count,
                error=error,
                lease_lost=not updated,
            )

        published_at = self._clock()
        with self._uow_factory() as uow:
            updated = uow.require_repository().complete_outbox_publish(
                item.outbox_id,
                self.publisher_id,
                item.lease_token,
                published_at,
            )
        return OutboxPublishResult(
            outbox_id=item.outbox_id,
            event_id=item.event_id,
            status=(OutboxState.PUBLISHED if updated else OutboxState.PROCESSING),
            attempt_count=item.attempt_count,
            lease_lost=not updated,
        )

    def run_until_idle(self, max_items: int = 100) -> list[OutboxPublishResult]:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        results: list[OutboxPublishResult] = []
        while len(results) < max_items:
            result = self.run_once()
            if result is None:
                break
            results.append(result)
        return results

    def run_forever(
        self,
        stop_event: StopEvent,
        *,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        while not stop_event.is_set():
            if self.run_once() is None:
                stop_event.wait(poll_interval_seconds)

    @staticmethod
    def _as_gateway_contract_event(item: OutboxItem) -> OutboxItem:
        payload = item.payload
        if "contract_version" not in payload:
            payload = {
                "contract_version": CONTRACT_VERSION,
                "event_id": payload.get("event_id", item.event_id),
                "correlation_id": payload.get("correlation_id"),
                "causation_id": None,
                "source": "CHANNEL_ENGINE",
                "event_type": payload.get("event_type", item.topic),
                "aggregate_type": payload.get("aggregate_type"),
                "aggregate_id": payload.get("aggregate_id"),
                "payload": payload.get("payload", {}),
                "occurred_at": payload.get("occurred_at"),
            }
        event = GatewayEvent.model_validate_json(json.dumps(payload))
        return item.model_copy(update={"payload": event.model_dump(mode="json")})
