from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from channel_agent.control_v2 import AgentReceiptSubmission, ServiceApprovalDelivery
from channel_agent.edge_execution import (
    AuthorizedEdgeSendCommand,
    EdgeExecutionService,
    EdgeReceiptStore,
    EdgeTransportResult,
)
from channel_agent.execution_authorization import (
    ExecutionAuthorizationSigner,
    ExecutionAuthorizationVerifier,
)
from channel_agent.identity import AgentIdentity, AgentIdentityStatus
from channel_engine.agent.execution_commands import (
    ExecutionCommandDenied,
    ExecutionCommandIssuer,
    ExecutionSafetySnapshot,
    SqlAlchemyAgentReceiptReconciler,
)
from channel_engine.models import (
    Approval,
    ApprovalState,
    Conversation,
    Decision,
    DecisionAction,
    DecisionState,
    Execution,
    ExecutionState,
    Message,
    MessageState,
    ReceiptOutcome,
)


NOW = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
SELECTOR_HASH = "sha256:" + "a" * 64
SECRET = b"execution-authorization-secret-material-v21"


class SimulatorPolicy:
    def evaluate(self, delivery: ServiceApprovalDelivery) -> ExecutionSafetySnapshot:
        return ExecutionSafetySnapshot(
            transport_mode="SIMULATOR",
            policy_version=delivery.policy_version,
            selector_evidence_hash=delivery.selector_evidence_hash,
            activation_grant_id=delivery.activation_grant_id,
            customer_reference=delivery.customer_reference,
            human_approval_verified=True,
            kill_switch_disabled=True,
            store_allowlisted=True,
            conversation_matches=True,
            customer_matches=True,
            risk_policy_allowed=True,
            rate_limit_allowed=True,
            selector_evidence_valid=True,
            activation_grant_valid=True,
            synthetic_send_enabled=True,
            real_send_enabled=False,
            real_platform_activation_allowed=False,
        )


class SuccessfulSyntheticTransport:
    calls = 0

    def send(self, _command: AuthorizedEdgeSendCommand) -> EdgeTransportResult:
        self.calls += 1
        return EdgeTransportResult(
            outcome="SUCCESS",
            transport_triggered=True,
            customer_message_sent=True,
            confirmation_state="CONFIRMED_SUCCESS",
            external_message_id="synthetic-sent-001",
        )


class UnknownSyntheticTransport:
    calls = 0

    def send(self, _command: AuthorizedEdgeSendCommand) -> EdgeTransportResult:
        self.calls += 1
        return EdgeTransportResult(
            outcome="UNKNOWN",
            transport_triggered=None,
            customer_message_sent=None,
            confirmation_state="UNCONFIRMED",
            error_code="SYNTHETIC_CONFIRMATION_LOST",
        )


def _ledger(foundation):
    conversation = Conversation(
        conversation_id="conv-v21",
        channel_name="pdd",
        external_ref="pdd-conversation-v21",
        created_at=NOW,
        updated_at=NOW,
    )
    message = Message(
        message_id="message-v21",
        conversation_id=conversation.conversation_id,
        external_message_id="external-message-v21",
        content="请问这款积木适合几岁？",
        state=MessageState.COMPLETED,
        received_at=NOW,
        updated_at=NOW,
    )
    decision = Decision(
        decision_id="decision-v21",
        conversation_id=conversation.conversation_id,
        message_id="message-v21",
        action=DecisionAction.SUGGEST_REPLY,
        proposed_content="您好，这款积木建议8岁以上儿童在成人陪同下使用。",
        requires_approval=True,
        state=DecisionState.APPROVED,
        gateway_version="1.0",
        created_at=NOW,
        updated_at=NOW,
    )
    approval = Approval(
        approval_id="approval-v21",
        decision_id=decision.decision_id,
        state=ApprovalState.APPROVED,
        decided_by="operator:user-001",
        reason="HUMAN_CONFIRMED_REPLY",
        decided_at=NOW,
        created_at=NOW,
    )
    execution = Execution(
        execution_id="execution-v21",
        decision_id=decision.decision_id,
        approval_id=approval.approval_id,
        idempotency_key="send-v21",
        created_at=NOW,
        updated_at=NOW,
    )
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        repo.save_conversation(conversation)
        assert uow.session is not None
        uow.session.flush()
        repo.save_message(message)
        uow.session.flush()
        repo.save_decision(decision)
        uow.session.flush()
        repo.save_approval(approval)
        uow.session.flush()
        repo.save_execution(execution)
    return decision, approval, execution


def _identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id="agent-v21",
        device_id="device-v21",
        user_id="user-001",
        store_id="store-001",
        store_ids=("store-001",),
        authorized_store_ids=("store-001",),
        active_store_id="store-001",
        status=AgentIdentityStatus.ACTIVE,
        binding_revision=2,
        created_at=NOW,
        updated_at=NOW,
    )


def _delivery() -> ServiceApprovalDelivery:
    return ServiceApprovalDelivery(
        approval_delivery_id="delivery-v21",
        agent_id="agent-v21",
        device_id="device-v21",
        store_id="store-001",
        conversation_id="pdd-conversation-v21",
        customer_reference="customer-a",
        message_id="message-v21",
        decision_id="decision-v21",
        approval_id="approval-v21",
        operator_reference="operator:user-001",
        reply_text="您好，这款积木建议8岁以上儿童在成人陪同下使用。",
        policy_version="simulator-policy-v1",
        selector_evidence_hash=SELECTOR_HASH,
        activation_grant_id="synthetic-activation-grant",
        approved_at=NOW,
    )


def _command(foundation):
    _ledger(foundation)
    issuer = ExecutionCommandIssuer(
        uow_factory=foundation["uow_factory"],
        identity_resolver=lambda _agent_id: _identity(),
        policy=SimulatorPolicy(),
        signer=ExecutionAuthorizationSigner(
            key_id="execution-key-v21",
            secret=SECRET,
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    return issuer(_delivery())


@pytest.mark.parametrize(
    ("transport_type", "expected_outcome"),
    [
        (SuccessfulSyntheticTransport, ReceiptOutcome.SUCCESS),
        (UnknownSyntheticTransport, ReceiptOutcome.UNKNOWN),
    ],
)
def test_signed_agent_command_finalizes_core_ledger(
    foundation, tmp_path, transport_type, expected_outcome
) -> None:
    command = _command(foundation)
    transport = transport_type()
    service = EdgeExecutionService(
        agent_id="agent-v21",
        device_id="device-v21",
        verifier=ExecutionAuthorizationVerifier(
            key_resolver=lambda key_id: SECRET if key_id == "execution-key-v21" else b"",
            clock=lambda: NOW,
        ),
        receipt_store=EdgeReceiptStore(tmp_path / "receipts.sqlite3"),
        transport=transport,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    receipt = service.execute(
        AuthorizedEdgeSendCommand(
            authorization=command.execution_authorization,
            reply_text=command.reply_text,
        ),
        current_store_id="store-001",
        current_conversation_id="pdd-conversation-v21",
        current_customer_reference="customer-a",
        current_selector_evidence_hash=SELECTOR_HASH,
    )
    reconciler = SqlAlchemyAgentReceiptReconciler(
        foundation["uow_factory"],
        clock=lambda: NOW + timedelta(seconds=2),
    )
    core_receipt = reconciler(
        AgentReceiptSubmission(
            agent_id="agent-v21",
            device_id="device-v21",
            receipt=receipt,
            submitted_at=NOW + timedelta(seconds=2),
        )
    )

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution("execution-v21")
        persisted = repo.get_receipt_for_execution("execution-v21")
    assert execution.state.value == expected_outcome.value
    assert persisted is not None
    assert persisted.receipt_id == core_receipt.receipt_id
    assert persisted.outcome == core_receipt.outcome
    assert persisted.details == core_receipt.details
    assert transport.calls == 1
    assert core_receipt.details["source"] == "CHANNEL_AGENT_V2_1"
    assert core_receipt.details["automatic_retry_allowed"] is False
    if expected_outcome is ReceiptOutcome.UNKNOWN:
        assert core_receipt.details["transport_triggered"] is None
        assert core_receipt.details["customer_message_sent"] is None
        assert core_receipt.details["reconciliation_required"] is True
        # Reconciliation is idempotent and cannot trigger the transport again.
        replayed = reconciler(
            AgentReceiptSubmission(
                agent_id="agent-v21",
                device_id="device-v21",
                receipt=receipt,
                submitted_at=NOW + timedelta(seconds=3),
            )
        )
        assert replayed.receipt_id == core_receipt.receipt_id
        assert replayed.outcome == core_receipt.outcome
        assert replayed.details == core_receipt.details
        assert transport.calls == 1


def test_issuer_fails_closed_when_identity_is_not_active(foundation) -> None:
    _ledger(foundation)
    inactive = _identity().model_copy(update={"status": AgentIdentityStatus.BOUND})
    issuer = ExecutionCommandIssuer(
        uow_factory=foundation["uow_factory"],
        identity_resolver=lambda _agent_id: inactive,
        policy=SimulatorPolicy(),
        signer=ExecutionAuthorizationSigner(
            key_id="execution-key-v21", secret=SECRET, clock=lambda: NOW
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(ExecutionCommandDenied, match="not ACTIVE"):
        issuer(_delivery())
    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().get_execution("execution-v21").state is ExecutionState.PENDING


def test_non_simulator_policy_cannot_issue_while_real_send_is_disabled() -> None:
    with pytest.raises(ValueError, match="not activated"):
        ExecutionSafetySnapshot(
            transport_mode="STAGING",
            policy_version="policy",
            selector_evidence_hash=SELECTOR_HASH,
            activation_grant_id="grant",
            customer_reference="customer",
            human_approval_verified=True,
            kill_switch_disabled=True,
            store_allowlisted=True,
            conversation_matches=True,
            customer_matches=True,
            risk_policy_allowed=True,
            rate_limit_allowed=True,
            selector_evidence_valid=True,
            activation_grant_valid=True,
            synthetic_send_enabled=False,
            real_send_enabled=False,
            real_platform_activation_allowed=False,
        )
