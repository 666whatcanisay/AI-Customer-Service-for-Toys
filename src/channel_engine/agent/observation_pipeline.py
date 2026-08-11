from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_agent.control_v2 import AgentObservationSubmission
from channel_engine.channel import NormalizedMessage
from channel_engine.conversation import ConversationService, IntakeResult
from channel_engine.gateway import AICSGateway
from channel_engine.storage import SqlAlchemyUnitOfWork


class ObservationPipelineError(RuntimeError):
    pass


class PDDObservationPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["channel-agent-pdd-observation.v2.1"]
    platform: Literal["PDD"]
    store_id: str = Field(min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    store_name: str | None = Field(default=None, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["CUSTOMER"]
    origin: Literal["LIVE_PDD", "STARTUP_UNREAD", "SYNTHETIC"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    timestamp: AwareDatetime
    product: dict[str, object]
    order: dict[str, object]
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_evidence_hash: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    privacy_filtered: Literal[True]


class AgentObservationDecisionProjector:
    """Projects durable Agent observations through frozen Gateway Contract V1."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        gateway: AICSGateway,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway

    def __call__(self, submission: AgentObservationSubmission) -> IntakeResult:
        try:
            payload = PDDObservationPayload.model_validate(submission.payload)
        except ValueError as exc:
            raise ObservationPipelineError("Agent observation payload is invalid") from exc
        if (
            payload.store_id != submission.store_id
            or payload.conversation_id != submission.conversation_id
            or payload.external_message_id != submission.external_message_id
        ):
            raise ObservationPipelineError("Agent observation envelope scope mismatch")

        context = {
            "customer_context_version": "channel-agent-observation.v2.1",
            "store_id": payload.store_id,
            "store_name": payload.store_name,
            "conversation_id": payload.conversation_id,
            "customer_reference": payload.customer_reference,
            "product": payload.product,
            "transaction": payload.order,
            "privacy_filtered": True,
            "source": "CHANNEL_AGENT_V2_1",
        }
        service = ConversationService(
            self._uow_factory,
            self._gateway,
            decision_context_provider=lambda _message: context,
        )
        return service.receive(
            NormalizedMessage(
                channel="pdd",
                store_id=payload.store_id,
                conversation_id=payload.conversation_id,
                external_message_id=payload.external_message_id,
                sender="customer",
                content=payload.content,
                timestamp=payload.timestamp,
            )
        )


__all__ = [
    "AgentObservationDecisionProjector",
    "ObservationPipelineError",
    "PDDObservationPayload",
]
