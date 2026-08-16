from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, JsonValue

from channel_engine.channel import NormalizedMessage, store_scoped_conversation_ref
from channel_engine.gateway import AICSGateway, CONTRACT_VERSION, DecisionRequest
from channel_engine.models import (
    Conversation,
    Decision,
    DecisionState,
    Event,
    EventType,
    Message,
    MessageState,
    transition_decision,
    transition_message,
)
from channel_engine.models.entities import utc_now
from channel_engine.observability import (
    StructuredEvent,
    StructuredEventStatus,
    StructuredEventType,
)
from channel_engine.storage import SqlAlchemyUnitOfWork


class IntakeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation_id: str
    message_id: str
    message_state: MessageState
    decision_id: str
    decision_state: DecisionState
    requires_approval: bool
    proposed_content: str | None


class ConversationService:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        gateway: AICSGateway,
        *,
        decision_context_provider: (
            Callable[[NormalizedMessage], Mapping[str, JsonValue]] | None
        ) = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._decision_context_provider = decision_context_provider

    def receive(self, inbound: NormalizedMessage) -> IntakeResult:
        try:
            return self._receive_once(inbound)
        except Exception as exc:
            # The business transaction deliberately rolls back on gateway or
            # intake failure.  Record only an opaque, redacted failure trace in
            # a fresh transaction so operators can still see why work stopped.
            self._record_intake_failure(inbound, exc)
            raise

    def _record_intake_failure(
        self, inbound: NormalizedMessage, error: Exception
    ) -> None:
        opaque = sha256(
            "|".join(
                (
                    inbound.channel,
                    inbound.store_id or "no-store",
                    inbound.conversation_id,
                    inbound.external_message_id,
                )
            ).encode("utf-8")
        ).hexdigest()[:32]
        trace_id = f"failed-intake-{opaque}"
        error_code = "".join(
            character if character.isalnum() else "_"
            for character in type(error).__name__.upper()
        )[:80]
        with self._uow_factory() as uow:
            uow.require_repository().append_observability_event(
                StructuredEvent(
                    event_type=StructuredEventType.DECISION_REQUEST_SENT,
                    trace_id=trace_id,
                    request_id=f"decision-request-{trace_id}",
                    store_id=inbound.store_id,
                    status=StructuredEventStatus.UNKNOWN,
                    metadata={
                        "channel_name": inbound.channel,
                        "error_code": error_code or "INTAKE_FAILED",
                        "reason_code": "INTAKE_TRANSACTION_ROLLED_BACK",
                        "automatic_retry_allowed": False,
                    },
                )
            )

    def _receive_once(self, inbound: NormalizedMessage) -> IntakeResult:
        # Platform conversation identifiers are only store-local.  Qualifying
        # the repository key prevents two stores on the same platform from
        # sharing a Conversation while retaining the external id on the
        # normalized message.
        conversation_ref = (
            inbound.conversation_id
            if inbound.store_id is None
            else store_scoped_conversation_ref(
                inbound.store_id,
                inbound.conversation_id,
            )
        )
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            conversation = repo.find_conversation(
                inbound.channel, conversation_ref
            )
            if conversation is None:
                conversation = Conversation(
                    channel_name=inbound.channel,
                    external_ref=conversation_ref,
                )
                repo.save_conversation(conversation)

            existing_message = repo.find_message(
                conversation.conversation_id, inbound.external_message_id
            )
            if existing_message is not None:
                if existing_message.content != inbound.content:
                    raise ValueError(
                        "external_message_id already exists with different content"
                    )
                existing_decision = repo.find_decision_for_message(
                    existing_message.message_id
                )
                if existing_decision is None:
                    raise ValueError(
                        "existing message has no decision; manual reconciliation required"
                    )
                return IntakeResult(
                    conversation_id=conversation.conversation_id,
                    message_id=existing_message.message_id,
                    message_state=existing_message.state,
                    decision_id=existing_decision.decision_id,
                    decision_state=existing_decision.state,
                    requires_approval=existing_decision.requires_approval,
                    proposed_content=existing_decision.proposed_content,
                )

            message = Message(
                conversation_id=conversation.conversation_id,
                external_message_id=inbound.external_message_id,
                content=inbound.content,
                received_at=inbound.timestamp,
            )
            repo.append_event(
                Event(
                    aggregate_type="Message",
                    aggregate_id=message.message_id,
                    event_type=EventType.MESSAGE_RECEIVED,
                    payload={
                        "conversation_id": conversation.conversation_id,
                        "channel_name": inbound.channel,
                        "sender": inbound.sender,
                        "store_id": inbound.store_id,
                    },
                    correlation_id=message.message_id,
                )
            )
            repo.append_observability_event(
                StructuredEvent(
                    event_type=StructuredEventType.MESSAGE_NORMALIZED,
                    trace_id=message.message_id,
                    message_id=message.message_id,
                    conversation_id=conversation.conversation_id,
                    store_id=inbound.store_id,
                    status=StructuredEventStatus.SUCCESS,
                    metadata={
                        "channel_name": inbound.channel,
                        "content_length": len(inbound.content),
                    },
                )
            )
            message = transition_message(message, MessageState.PROCESSING)

            decision_context: dict[str, JsonValue] = {
                "channel_name": inbound.channel,
                "sender": inbound.sender,
            }
            if inbound.store_id is not None:
                decision_context["store_id"] = inbound.store_id
            if self._decision_context_provider is not None:
                decision_context.update(self._decision_context_provider(inbound))

            request_id = f"decision-request-{message.message_id}"
            repo.append_observability_event(
                StructuredEvent(
                    event_type=StructuredEventType.DECISION_REQUEST_SENT,
                    trace_id=message.message_id,
                    message_id=message.message_id,
                    conversation_id=conversation.conversation_id,
                    request_id=request_id,
                    store_id=inbound.store_id,
                    status=StructuredEventStatus.PENDING,
                    metadata={"gateway_version": CONTRACT_VERSION},
                )
            )
            response = self._gateway.decide(
                DecisionRequest(
                    contract_version=CONTRACT_VERSION,
                    request_id=request_id,
                    idempotency_key=f"decision-{message.message_id}",
                    correlation_id=message.message_id,
                    conversation_id=conversation.conversation_id,
                    message_id=message.message_id,
                    customer_message=message.content,
                    context=decision_context,
                    requested_at=utc_now(),
                )
            )
            decision = Decision(
                decision_id=response.decision_id,
                conversation_id=conversation.conversation_id,
                message_id=message.message_id,
                action=response.action,
                proposed_content=response.proposed_content,
                requires_approval=response.requires_approval,
                gateway_version=response.gateway_version,
            )
            repo.append_event(
                Event(
                    aggregate_type="Decision",
                    aggregate_id=decision.decision_id,
                    event_type=EventType.DECISION_CREATED,
                    payload={"action": decision.action.value},
                    correlation_id=message.message_id,
                )
            )
            decision = transition_decision(decision, DecisionState.WAITING_APPROVAL)
            message = transition_message(message, MessageState.COMPLETED)

            # Persist the FK parents before append_event performs a duplicate check
            # that may trigger SQLAlchemy autoflush.
            repo.save_message(message)
            repo.save_decision(decision)
            repo.append_event(
                Event(
                    aggregate_type="Decision",
                    aggregate_id=decision.decision_id,
                    event_type=EventType.DECISION_WAITING_APPROVAL,
                    payload={"requires_approval": True},
                    correlation_id=message.message_id,
                )
            )
            repo.append_event(
                Event(
                    aggregate_type="Message",
                    aggregate_id=message.message_id,
                    event_type=EventType.MESSAGE_COMPLETED,
                    payload={"decision_id": decision.decision_id},
                    correlation_id=message.message_id,
                )
            )

            return IntakeResult(
                conversation_id=conversation.conversation_id,
                message_id=message.message_id,
                message_state=message.state,
                decision_id=decision.decision_id,
                decision_state=decision.state,
                requires_approval=decision.requires_approval,
                proposed_content=decision.proposed_content,
            )
