from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from channel_agent.control_v2 import (
    AgentCommandEnvelope,
    AgentReceiptSubmission,
    ServiceApprovalDelivery,
)
from channel_agent.execution_authorization import (
    ExecutionAuthorizationClaims,
    ExecutionAuthorizationSigner,
    reply_text_sha256,
)
from channel_agent.identity import AgentIdentity, AgentIdentityStatus
from channel_engine.channel import store_scoped_conversation_ref
from channel_engine.models import (
    ApprovalState,
    DecisionAction,
    DecisionState,
    Event,
    EventType,
    ExecutionState,
    Receipt,
    ReceiptOutcome,
)
from channel_engine.storage import RecordNotFound, SqlAlchemyUnitOfWork


class ExecutionCommandDenied(PermissionError):
    """The durable ledger or a mandatory safety gate denied an edge send."""


class ExecutionSafetySnapshot(BaseModel):
    """Authoritative policy facts evaluated immediately before issuing a command."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    transport_mode: Literal["SIMULATOR", "STAGING", "PRODUCTION"]
    policy_version: str = Field(min_length=1, max_length=128)
    selector_evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    activation_grant_id: str = Field(min_length=1, max_length=160)
    customer_reference: str = Field(min_length=1, max_length=255)
    human_approval_verified: Literal[True]
    kill_switch_disabled: Literal[True]
    store_allowlisted: Literal[True]
    conversation_matches: Literal[True]
    customer_matches: Literal[True]
    risk_policy_allowed: Literal[True]
    rate_limit_allowed: Literal[True]
    selector_evidence_valid: Literal[True]
    activation_grant_valid: Literal[True]
    synthetic_send_enabled: bool = False
    real_send_enabled: bool = False
    real_platform_activation_allowed: bool = False

    @model_validator(mode="after")
    def validate_transport_boundary(self) -> ExecutionSafetySnapshot:
        if self.transport_mode == "SIMULATOR":
            if not self.synthetic_send_enabled:
                raise ValueError("simulator execution is not enabled")
            if self.real_send_enabled or self.real_platform_activation_allowed:
                raise ValueError("simulator policy cannot enable real platform execution")
        elif not (
            self.transport_mode == "PRODUCTION"
            and self.real_send_enabled
            and self.real_platform_activation_allowed
        ):
            raise ValueError("non-simulator execution is not activated")
        return self


class ExecutionSafetyPolicy(Protocol):
    def evaluate(self, delivery: ServiceApprovalDelivery) -> ExecutionSafetySnapshot: ...


class ExecutionCommandIssuer:
    """Convert one AI-CS human approval into one ledger-backed signed command."""

    def __init__(
        self,
        *,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        identity_resolver: Callable[[str], AgentIdentity | None],
        policy: ExecutionSafetyPolicy,
        signer: ExecutionAuthorizationSigner,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        lease_duration: timedelta = timedelta(seconds=90),
    ) -> None:
        if lease_duration <= timedelta(0) or lease_duration > timedelta(minutes=5):
            raise ValueError("edge execution lease duration is invalid")
        self._uow_factory = uow_factory
        self._identity_resolver = identity_resolver
        self._policy = policy
        self._signer = signer
        self._clock = clock
        self._lease_duration = lease_duration

    def __call__(self, delivery: ServiceApprovalDelivery) -> AgentCommandEnvelope:
        now = self._clock().astimezone(UTC)
        identity = self._identity_resolver(delivery.agent_id)
        if identity is None or identity.status is not AgentIdentityStatus.ACTIVE:
            raise ExecutionCommandDenied("Agent identity is not ACTIVE")
        if identity.device_id != delivery.device_id:
            raise ExecutionCommandDenied("approval device does not match Agent identity")
        if (
            identity.effective_active_store_id != delivery.store_id
            or delivery.store_id not in identity.authorized_stores
        ):
            raise ExecutionCommandDenied("approval store is not the active authorized store")

        safety = self._policy.evaluate(delivery)
        self._assert_delivery_matches_safety(delivery, safety)
        worker_id = f"edge:{delivery.agent_id}:{delivery.device_id}"
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            try:
                decision = repo.get_decision(delivery.decision_id)
                approval = repo.get_approval_for_decision(decision.decision_id)
                execution = repo.get_execution_for_decision(decision.decision_id)
                conversation = repo.get_conversation(decision.conversation_id)
            except RecordNotFound as exc:
                raise ExecutionCommandDenied("approval ledger record is missing") from exc
            if approval is None or execution is None:
                raise ExecutionCommandDenied("approval or execution ledger record is missing")
            if (
                decision.state is not DecisionState.APPROVED
                or decision.action is not DecisionAction.SUGGEST_REPLY
                or decision.proposed_content != delivery.reply_text
                or decision.message_id != delivery.message_id
                or approval.state is not ApprovalState.APPROVED
                or approval.approval_id != delivery.approval_id
                or approval.decided_by != delivery.operator_reference
                or execution.approval_id != approval.approval_id
                or conversation.external_ref
                not in {
                    delivery.conversation_id,
                    store_scoped_conversation_ref(
                        delivery.store_id, delivery.conversation_id
                    ),
                }
            ):
                raise ExecutionCommandDenied("AI-CS approval does not match the durable execution ledger")
            if execution.state is ExecutionState.PENDING:
                execution = repo.claim_pending_execution_by_id(
                    execution.execution_id,
                    worker_id,
                    now,
                    now + self._lease_duration,
                )
                if execution is None:
                    raise ExecutionCommandDenied("execution lease could not be acquired")
                repo.append_event(
                    Event(
                        aggregate_type="Execution",
                        aggregate_id=execution.execution_id,
                        event_type=EventType.EXECUTION_STARTED,
                        payload={"worker_id": worker_id, "transport": safety.transport_mode},
                        correlation_id=decision.message_id,
                        occurred_at=now,
                    )
                )
            elif not (
                execution.state is ExecutionState.RUNNING
                and execution.lease_owner == worker_id
                and execution.lease_token
                and execution.lease_expires_at
                and _aware(execution.lease_expires_at) > now
            ):
                raise ExecutionCommandDenied("execution is not safely claimable")

        assert execution.lease_token is not None
        assert execution.lease_expires_at is not None
        authorization = self._signer.issue(
            ExecutionAuthorizationClaims(
                agent_id=delivery.agent_id,
                device_id=delivery.device_id,
                store_id=delivery.store_id,
                conversation_id=delivery.conversation_id,
                customer_reference=delivery.customer_reference,
                message_id=delivery.message_id,
                decision_id=delivery.decision_id,
                approval_id=delivery.approval_id,
                execution_id=execution.execution_id,
                lease_id=execution.lease_token,
                lease_expires_at=_aware(execution.lease_expires_at),
                reply_sha256=reply_text_sha256(delivery.reply_text),
                send_key=execution.idempotency_key,
                policy_version=safety.policy_version,
                selector_evidence_hash=safety.selector_evidence_hash,
                activation_grant_id=safety.activation_grant_id,
                human_approval_verified=True,
                lease_valid=True,
                kill_switch_disabled=True,
                store_allowlisted=True,
                risk_policy_allowed=True,
                rate_limit_allowed=True,
            )
        )
        return AgentCommandEnvelope(
            command_id=command_id_for_approval(delivery.approval_delivery_id),
            command_type="SEND_MESSAGE",
            agent_id=delivery.agent_id,
            device_id=delivery.device_id,
            store_id=delivery.store_id,
            execution_authorization=authorization,
            reply_text=delivery.reply_text,
            issued_at=authorization.issued_at,
            expires_at=authorization.expires_at,
        )

    @staticmethod
    def _assert_delivery_matches_safety(
        delivery: ServiceApprovalDelivery,
        safety: ExecutionSafetySnapshot,
    ) -> None:
        if (
            safety.policy_version != delivery.policy_version
            or safety.selector_evidence_hash != delivery.selector_evidence_hash
            or safety.activation_grant_id != delivery.activation_grant_id
            or safety.customer_reference != delivery.customer_reference
        ):
            raise ExecutionCommandDenied("approval does not match current safety evidence")


class SqlAlchemyAgentReceiptReconciler:
    """Finalize the core ledger from an immutable Agent receipt, idempotently."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def __call__(self, submission: AgentReceiptSubmission) -> Receipt:
        edge = submission.receipt
        now = self._clock().astimezone(UTC)
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            execution = repo.get_execution(edge.execution_id)
            existing = repo.get_receipt_for_execution(edge.execution_id)
            if existing is not None:
                if existing.receipt_id != edge.receipt_id or existing.outcome.value != edge.outcome:
                    raise ExecutionCommandDenied("immutable core receipt conflicts with Agent receipt")
                return existing
            if (
                execution.decision_id != edge.decision_id
                or execution.approval_id != edge.approval_id
                or execution.state is not ExecutionState.RUNNING
                or execution.lease_owner != f"edge:{submission.agent_id}:{submission.device_id}"
                or execution.lease_token != edge.lease_id
                or execution.lease_expires_at is None
            ):
                raise ExecutionCommandDenied("Agent receipt does not own the active execution lease")
            completed_at = _aware(edge.created_at)
            if completed_at > now + timedelta(seconds=30) or completed_at >= _aware(
                execution.lease_expires_at
            ):
                raise ExecutionCommandDenied("Agent receipt was produced outside the execution lease")
            outcome = ReceiptOutcome(edge.outcome)
            terminal = ExecutionState(edge.outcome)
            finalized = repo.finish_claimed_execution(
                execution.execution_id,
                execution.lease_owner,
                execution.lease_token,
                terminal,
                completed_at,
                edge.error_code,
            )
            if finalized is None:
                raise ExecutionCommandDenied("execution lease was lost before receipt finalization")
            details = {
                "transport_triggered": edge.transport_triggered,
                "customer_message_sent": edge.customer_message_sent,
                "confirmation_state": edge.confirmation_state,
                "reconciliation_required": edge.reconciliation_required,
                "automatic_retry_allowed": False,
                "authorization_id": edge.authorization_id,
                "send_key": edge.send_key,
                "reply_sha256": edge.reply_sha256,
                "agent_id": submission.agent_id,
                "device_id": submission.device_id,
                "source": "CHANNEL_AGENT_V2_1",
            }
            receipt = Receipt(
                receipt_id=edge.receipt_id,
                execution_id=edge.execution_id,
                outcome=outcome,
                external_reference=edge.external_message_id,
                details=details,
                recorded_at=completed_at,
            )
            repo.append_receipt(receipt)
            decision = repo.get_decision(execution.decision_id)
            event_type = {
                ReceiptOutcome.SUCCESS: EventType.EXECUTION_SUCCEEDED,
                ReceiptOutcome.FAILED: EventType.EXECUTION_FAILED,
                ReceiptOutcome.UNKNOWN: EventType.EXECUTION_UNKNOWN,
            }[outcome]
            repo.append_event(
                Event(
                    aggregate_type="Execution",
                    aggregate_id=edge.execution_id,
                    event_type=event_type,
                    payload={"receipt_id": edge.receipt_id, "outcome": edge.outcome},
                    correlation_id=decision.message_id,
                    occurred_at=completed_at,
                )
            )
            repo.append_event(
                Event(
                    aggregate_type="Receipt",
                    aggregate_id=edge.receipt_id,
                    event_type=EventType.RECEIPT_RECORDED,
                    payload={"execution_id": edge.execution_id},
                    correlation_id=decision.message_id,
                    occurred_at=completed_at,
                )
            )
            return receipt


def command_id_for_approval(approval_delivery_id: str) -> str:
    digest = hashlib.sha256(approval_delivery_id.encode("utf-8")).hexdigest()[:32]
    return f"agent-command:{digest}"


def delivery_matches_command(
    delivery: ServiceApprovalDelivery,
    command: AgentCommandEnvelope,
) -> bool:
    authorization = command.execution_authorization
    return (
        command.command_id == command_id_for_approval(delivery.approval_delivery_id)
        and command.agent_id == delivery.agent_id
        and command.device_id == delivery.device_id
        and command.store_id == delivery.store_id
        and command.reply_text == delivery.reply_text
        and authorization.conversation_id == delivery.conversation_id
        and authorization.customer_reference == delivery.customer_reference
        and authorization.message_id == delivery.message_id
        and authorization.decision_id == delivery.decision_id
        and authorization.approval_id == delivery.approval_id
        and authorization.policy_version == delivery.policy_version
        and authorization.selector_evidence_hash == delivery.selector_evidence_hash
        and authorization.activation_grant_id == delivery.activation_grant_id
    )


def _aware(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "ExecutionCommandDenied",
    "ExecutionCommandIssuer",
    "ExecutionSafetyPolicy",
    "ExecutionSafetySnapshot",
    "SqlAlchemyAgentReceiptReconciler",
    "command_id_for_approval",
    "delivery_matches_command",
]
