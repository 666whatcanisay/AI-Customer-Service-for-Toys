from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from channel_engine.channel import ChannelMessage
from channel_engine.gateway import AICSGateway, DecisionRequest
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
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway

    def receive(self, inbound: ChannelMessage) -> IntakeResult:
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            conversation = repo.find_conversation(
                inbound.channel_name, inbound.conversation_external_ref
            )
            if conversation is None:
                conversation = Conversation(
                    channel_name=inbound.channel_name,
                    external_ref=inbound.conversation_external_ref,
                )
                repo.save_conversation(conversation)

            existing_message = repo.find_message(
                conversation.conversation_id, inbound.external_message_id
            )
            if existing_message is not None:
                if existing_message.content != inbound.text:
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
                content=inbound.text,
                received_at=inbound.received_at,
            )
            repo.append_event(
                Event(
                    aggregate_type="Message",
                    aggregate_id=message.message_id,
                    event_type=EventType.MESSAGE_RECEIVED,
                    payload={
                        "conversation_id": conversation.conversation_id,
                        "channel_name": inbound.channel_name,
                    },
                    correlation_id=message.message_id,
                )
            )
            message = transition_message(message, MessageState.PROCESSING)

            response = self._gateway.decide(
                DecisionRequest(
                    conversation_id=conversation.conversation_id,
                    message_id=message.message_id,
                    customer_message=message.content,
                    context={"channel_name": inbound.channel_name},
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
