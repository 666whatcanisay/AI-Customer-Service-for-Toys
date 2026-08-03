from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from channel_engine.models import (
    Approval,
    Conversation,
    Decision,
    Event,
    Execution,
    Message,
    OutboxState,
    Receipt,
)
from channel_engine.models.entities import utc_now

from .orm import (
    ApprovalRow,
    ConversationRow,
    DecisionRow,
    EventRow,
    ExecutionRow,
    MessageRow,
    OutboxRow,
    ReceiptRow,
)


class RecordNotFound(LookupError):
    pass


class OutboxItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outbox_id: str
    event_id: str
    topic: str
    payload: dict[str, Any]
    status: OutboxState
    created_at: datetime


class ChannelEngineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_conversation(self, channel_name: str, external_ref: str) -> Conversation | None:
        row = self.session.scalar(
            select(ConversationRow).where(
                ConversationRow.channel_name == channel_name,
                ConversationRow.external_ref == external_ref,
            )
        )
        return self._conversation_from_row(row) if row else None

    def save_conversation(self, item: Conversation) -> None:
        row = self.session.get(ConversationRow, item.conversation_id)
        values = item.model_dump()
        if row is None:
            self.session.add(ConversationRow(**values))
        else:
            self._assign(row, values)

    def save_message(self, item: Message) -> None:
        row = self.session.get(MessageRow, item.message_id)
        values = item.model_dump()
        if row is None:
            self.session.add(MessageRow(**values))
        else:
            self._assign(row, values)

    def find_message(self, conversation_id: str, external_message_id: str) -> Message | None:
        row = self.session.scalar(
            select(MessageRow).where(
                MessageRow.conversation_id == conversation_id,
                MessageRow.external_message_id == external_message_id,
            )
        )
        return Message.model_validate(self._row_dict(row)) if row else None

    def save_decision(self, item: Decision) -> None:
        row = self.session.get(DecisionRow, item.decision_id)
        values = item.model_dump()
        values["requires_approval"] = int(item.requires_approval)
        if row is None:
            self.session.add(DecisionRow(**values))
        else:
            self._assign(row, values)

    def save_approval(self, item: Approval) -> None:
        row = self.session.get(ApprovalRow, item.approval_id)
        values = item.model_dump()
        if row is None:
            self.session.add(ApprovalRow(**values))
        else:
            self._assign(row, values)

    def save_execution(self, item: Execution) -> None:
        row = self.session.get(ExecutionRow, item.execution_id)
        values = item.model_dump()
        if row is None:
            self.session.add(ExecutionRow(**values))
        else:
            self._assign(row, values)

    def append_receipt(self, item: Receipt) -> None:
        if self.session.get(ReceiptRow, item.receipt_id) is not None:
            raise ValueError(f"receipt already exists: {item.receipt_id}")
        values = item.model_dump(mode="json")
        values["recorded_at"] = item.recorded_at
        self.session.add(ReceiptRow(**values))

    def append_event(self, item: Event) -> None:
        if self.session.get(EventRow, item.event_id) is not None:
            raise ValueError(f"event already exists: {item.event_id}")
        self.session.add(
            EventRow(
                event_id=item.event_id,
                aggregate_type=item.aggregate_type,
                aggregate_id=item.aggregate_id,
                event_type=item.event_type.value,
                payload=item.payload,
                correlation_id=item.correlation_id,
                occurred_at=item.occurred_at,
            )
        )
        self.session.add(
            OutboxRow(
                outbox_id=f"outbox-{item.event_id}",
                event_id=item.event_id,
                topic=item.event_type.value,
                payload=item.model_dump(mode="json"),
                status=OutboxState.PENDING.value,
                created_at=item.occurred_at,
            )
        )

    def get_message(self, message_id: str) -> Message:
        row = self.session.get(MessageRow, message_id)
        if row is None:
            raise RecordNotFound(f"message not found: {message_id}")
        return Message.model_validate(self._row_dict(row))

    def get_decision(self, decision_id: str) -> Decision:
        row = self.session.get(DecisionRow, decision_id)
        if row is None:
            raise RecordNotFound(f"decision not found: {decision_id}")
        values = self._row_dict(row)
        values["requires_approval"] = bool(values["requires_approval"])
        return Decision.model_validate(values)

    def find_decision_for_message(self, message_id: str) -> Decision | None:
        row = self.session.scalar(
            select(DecisionRow).where(DecisionRow.message_id == message_id)
        )
        if row is None:
            return None
        values = self._row_dict(row)
        values["requires_approval"] = bool(values["requires_approval"])
        return Decision.model_validate(values)

    def get_approval_for_decision(self, decision_id: str) -> Approval | None:
        row = self.session.scalar(
            select(ApprovalRow).where(ApprovalRow.decision_id == decision_id)
        )
        return Approval.model_validate(self._row_dict(row)) if row else None

    def get_execution(self, execution_id: str) -> Execution:
        row = self.session.get(ExecutionRow, execution_id)
        if row is None:
            raise RecordNotFound(f"execution not found: {execution_id}")
        return Execution.model_validate(self._row_dict(row))

    def get_receipt_for_execution(self, execution_id: str) -> Receipt | None:
        row = self.session.scalar(
            select(ReceiptRow).where(ReceiptRow.execution_id == execution_id)
        )
        return Receipt.model_validate(self._row_dict(row)) if row else None

    def list_pending_outbox(self, limit: int = 100) -> list[OutboxItem]:
        rows = self.session.scalars(
            select(OutboxRow)
            .where(OutboxRow.status == OutboxState.PENDING.value)
            .order_by(OutboxRow.created_at)
            .limit(limit)
        ).all()
        return [
            OutboxItem(
                outbox_id=row.outbox_id,
                event_id=row.event_id,
                topic=row.topic,
                payload=row.payload,
                status=OutboxState(row.status),
                created_at=row.created_at,
            )
            for row in rows
        ]

    def mark_outbox_published(self, outbox_id: str, published_at: datetime | None = None) -> None:
        row = self.session.get(OutboxRow, outbox_id)
        if row is None:
            raise RecordNotFound(f"outbox item not found: {outbox_id}")
        row.status = OutboxState.PUBLISHED.value
        row.published_at = published_at or utc_now()
        row.last_error = None

    @staticmethod
    def _assign(row: object, values: dict[str, Any]) -> None:
        for key, value in values.items():
            setattr(row, key, value.value if hasattr(value, "value") else value)

    @staticmethod
    def _row_dict(row: object) -> dict[str, Any]:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}  # type: ignore[attr-defined]

    @staticmethod
    def _conversation_from_row(row: ConversationRow) -> Conversation:
        return Conversation.model_validate(ChannelEngineRepository._row_dict(row))
