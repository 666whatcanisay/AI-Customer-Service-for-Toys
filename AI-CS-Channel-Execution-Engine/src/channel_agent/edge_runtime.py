from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .control_v2 import (
    AgentCommandEnvelope,
    AgentCommandPollResponse,
    AgentObservationAck,
    AgentObservationSubmission,
    AgentReceiptAck,
    AgentReceiptSubmission,
)
from .edge_execution import (
    AuthorizedEdgeSendCommand,
    EdgeExecutionReceipt,
    EdgeExecutionService,
    EdgeReceiptStore,
)
from .edge_spool import DurableEdgeSpool, EdgeObservation, EdgeSpoolError


class EdgeControlClient(Protocol):
    def submit_observation(
        self, submission: AgentObservationSubmission
    ) -> AgentObservationAck: ...

    def poll_command(self) -> AgentCommandPollResponse: ...

    def submit_receipt(self, submission: AgentReceiptSubmission) -> AgentReceiptAck: ...


@dataclass(frozen=True, slots=True)
class CurrentPageExecutionContext:
    store_id: str
    conversation_id: str
    customer_reference: str
    selector_evidence_hash: str


class EdgeRuntime:
    """Production edge flow with durable-before-ACK ordering and receipt recovery."""

    def __init__(
        self,
        *,
        agent_id: str,
        device_id: str,
        client: EdgeControlClient,
        spool: DurableEdgeSpool,
        execution: EdgeExecutionService,
        receipt_store: EdgeReceiptStore,
        clock=lambda: datetime.now(UTC),  # type: ignore[no-untyped-def]
    ) -> None:
        self.agent_id = agent_id
        self.device_id = device_id
        self._client = client
        self._spool = spool
        self._execution = execution
        self._receipts = receipt_store
        self._clock = clock

    def capture_and_forward(self, observation: EdgeObservation) -> AgentObservationAck:
        self._assert_observation_scope(observation)
        self._spool.persist(observation)
        return self._forward(observation)

    def recover_observations(self) -> tuple[AgentObservationAck, ...]:
        return tuple(self._forward(item) for item in self._spool.pending())

    def poll_and_execute(
        self,
        context: CurrentPageExecutionContext,
    ) -> EdgeExecutionReceipt | None:
        response = self._client.poll_command()
        if response.command is None:
            return None
        command = response.command
        self._assert_command_scope(command, context)
        receipt = self._execution.execute(
            AuthorizedEdgeSendCommand(
                authorization=command.execution_authorization,
                reply_text=command.reply_text,
            ),
            current_store_id=context.store_id,
            current_conversation_id=context.conversation_id,
            current_customer_reference=context.customer_reference,
            current_selector_evidence_hash=context.selector_evidence_hash,
        )
        self._submit_receipt(receipt)
        return receipt

    def recover_receipts(self) -> tuple[AgentReceiptAck, ...]:
        return tuple(self._submit_receipt(item) for item in self._receipts.pending())

    def _forward(self, observation: EdgeObservation) -> AgentObservationAck:
        cursor = observation.source_cursor
        if cursor is None:
            raise EdgeSpoolError("edge observation source cursor is required for Host ACK")
        submission = AgentObservationSubmission(
            observation_id=observation.observation_id,
            agent_id=observation.agent_id,
            device_id=observation.device_id,
            store_id=observation.store_id,
            conversation_id=observation.conversation_id,
            external_message_id=observation.external_message_id,
            source_cursor=cursor,
            source_sequence=observation.source_sequence,
            payload_digest=observation.payload_digest,
            payload=observation.payload,
            captured_at=observation.captured_at,
        )
        ack = self._client.submit_observation(submission)
        if ack.acknowledged_cursor != cursor:
            raise EdgeSpoolError("Host ACK cursor does not match the submitted observation")
        self._spool.acknowledge(
            observation_id=observation.observation_id,
            payload_digest=observation.payload_digest,
            cursor=ack.acknowledged_cursor,
        )
        return ack

    def _submit_receipt(self, receipt: EdgeExecutionReceipt) -> AgentReceiptAck:
        ack = self._client.submit_receipt(
            AgentReceiptSubmission(
                agent_id=self.agent_id,
                device_id=self.device_id,
                receipt=receipt,
                submitted_at=self._clock().astimezone(UTC),
            )
        )
        if ack.receipt_id != receipt.receipt_id:
            raise EdgeSpoolError("Host receipt ACK does not match the submitted receipt")
        self._receipts.acknowledge(receipt.receipt_id)
        return ack

    def _assert_observation_scope(self, observation: EdgeObservation) -> None:
        if observation.agent_id != self.agent_id or observation.device_id != self.device_id:
            raise EdgeSpoolError("edge observation belongs to another Agent device")

    def _assert_command_scope(
        self,
        command: AgentCommandEnvelope,
        context: CurrentPageExecutionContext,
    ) -> None:
        if command.agent_id != self.agent_id or command.device_id != self.device_id:
            raise PermissionError("edge command belongs to another Agent device")
        if command.store_id != context.store_id:
            raise PermissionError("edge command store no longer matches the current page")
        if command.expires_at <= self._clock().astimezone(UTC):
            raise PermissionError("edge command expired before execution")


__all__ = ["CurrentPageExecutionContext", "EdgeControlClient", "EdgeRuntime"]
