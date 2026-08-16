from __future__ import annotations

import pytest

from channel_engine.channel import (
    FakePDDHTTPSender,
    FakePDDSendSessionProvider,
    LedgerExecutionAuthorizationService,
    NormalizedMessage,
    PDD_PRODUCTION_CONFIRMATION_PHRASE,
    PDDApprovedExecutionContext,
    PDDControlledSendExecutionAdapter,
    PDDCredentialReference,
    PDDEnvironmentProfile,
    PDDExecutionControlBlocked,
    PDDProductionExecutionGate,
    PDDProductionSafetyDenied,
    PDDProductionSafetyGate,
    PDDProductionSafetyService,
    PDDSendTransport,
    PDDStoreStatus,
    StoreAccount,
)
from channel_engine.control.gate import PersistentExecutionControlGate
from channel_engine.control.service import ControlPlaneService
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionQueue, ExecutionWorker
from channel_engine.models import (
    DecisionState,
    EventType,
    ExecutionState,
    ReceiptOutcome,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy


STORE_ID = "pdd-integration-store-001"
CONVERSATION_ID = "pdd-integration-conversation-001"
COOKIE_REFERENCE = "secret-ref://pdd/fake/cookie-bundle"


def _configure(service: PDDProductionSafetyService) -> None:
    service.enable_production(
        confirmation_phrase=PDD_PRODUCTION_CONFIRMATION_PHRASE,
        operator="pdd-production-safety-operator",
        reason="PDD_PRODUCTION_DRY_RUN_ENABLE",
        dry_run=True,
    )
    service.allow_store(
        StoreAccount(
            store_id=STORE_ID,
            store_name="PDD Integration Fake Store",
            credential_reference=PDDCredentialReference(
                credential_ref=COOKIE_REFERENCE,
                version="v1",
            ),
            environment=PDDEnvironmentProfile.PRODUCTION,
            status=PDDStoreStatus.ALLOWLISTED,
            updated_at=utc_now(),
        ),
        operator="pdd-production-safety-operator",
        reason="PDD_STORE_ALLOWLIST_INTEGRATION",
    )


def _decision(foundation, suffix: str, conversation_id: str = CONVERSATION_ID):
    return ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(
        NormalizedMessage(
            channel="pdd",
            conversation_id=conversation_id,
            external_message_id=f"pdd-production-safety-message-{suffix}",
            sender="fake-customer",
            content=f"PDD production safety integration {suffix}",
            timestamp=utc_now(),
        )
    )


def test_full_worker_dry_run_preserves_approval_receipt_event_outbox_and_audit(
    foundation,
) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _configure(service)
    global_control = ControlPlaneService(foundation["uow_factory"])
    execution_gate = PDDProductionExecutionGate(
        delegate=PersistentExecutionControlGate()
    )
    intake = _decision(foundation, "full-flow")
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
        control_gate=execution_gate,
    ).approve_and_enqueue(intake.decision_id, "pdd-production-human")
    service.bind_execution(
        execution_id=enqueued.execution_id,
        store_id=STORE_ID,
        conversation_id=CONVERSATION_ID,
        operator="pdd-production-safety-operator",
        reason="PDD_EXECUTION_STORE_BIND_INTEGRATION",
    )
    sender = FakePDDHTTPSender()
    transport = PDDSendTransport(
        LedgerExecutionAuthorizationService(foundation["uow_factory"]),
        FakePDDSendSessionProvider(),
        sender,
        safety_gate=PDDProductionSafetyGate(
            service,
            global_control_plane=global_control,
        ),
    )
    worker = ExecutionWorker(
        foundation["uow_factory"],
        PDDControlledSendExecutionAdapter(transport),
        "pdd-production-safety-worker",
        control_gate=execution_gate,
    )

    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert sender.send_count == 1
    assert sender.real_platform_call_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        outbox = repo.list_outbox()
    assert receipt is not None
    assert receipt.details["environment"] == "PRODUCTION"
    assert receipt.details["store_id"] == STORE_ID
    assert receipt.details["dry_run"] is True
    assert receipt.details["human_approval_required"] is True
    assert receipt.details["automatic_retry_allowed"] is False
    assert receipt.details["real_platform_called"] is False
    assert receipt.details["customer_message_sent"] is False
    event_types = [item.payload["event_type"] for item in outbox]
    assert EventType.DECISION_APPROVED.value in event_types
    assert EventType.EXECUTION_STARTED.value in event_types
    assert EventType.EXECUTION_SUCCEEDED.value in event_types
    assert EventType.RECEIPT_RECORDED.value in event_types
    audit_actions = [event.action.value for event in service.list_audit_events()]
    assert "PRODUCTION_ENABLED" in audit_actions
    assert "STORE_ALLOWLISTED" in audit_actions
    assert "EXECUTION_STORE_BOUND" in audit_actions
    assert "SEND_AUTHORIZED" in audit_actions

    receipt_id = receipt.receipt_id
    outbox_count = len(outbox)
    service.enable_kill_switch(
        operator="pdd-production-safety-operator",
        reason="PDD_POST_SEND_EMERGENCY_STOP",
    )
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        retained_receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        retained_outbox = repo.list_outbox()
    assert retained_receipt is not None
    assert retained_receipt.receipt_id == receipt_id
    assert len(retained_outbox) == outbox_count
    assert any(
        event.action.value == "KILL_SWITCH_TRIGGERED"
        for event in service.list_audit_events()
    )


def test_pdd_kill_switch_blocks_new_execution_without_deleting_history(
    foundation,
) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _configure(service)
    execution_gate = PDDProductionExecutionGate(
        delegate=PersistentExecutionControlGate()
    )
    first = _decision(foundation, "history", "pdd-safety-history-conversation")
    first_execution = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
        control_gate=execution_gate,
    ).approve_and_enqueue(first.decision_id, "pdd-production-human")
    service.enable_kill_switch(
        operator="pdd-production-safety-operator",
        reason="PDD_KILL_SWITCH_INTEGRATION",
    )
    blocked = _decision(foundation, "blocked", "pdd-safety-blocked-conversation")

    with pytest.raises(PDDExecutionControlBlocked):
        ExecutionCoordinator(
            foundation["uow_factory"],
            ApprovalPolicy(),
            control_gate=execution_gate,
        ).approve_and_enqueue(blocked.decision_id, "pdd-production-human")

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        historical = repo.get_execution(first_execution.execution_id)
        blocked_decision = repo.get_decision(blocked.decision_id)
        blocked_execution = repo.get_execution_for_decision(blocked.decision_id)
    assert historical.state is ExecutionState.PENDING
    assert blocked_decision.state is DecisionState.WAITING_APPROVAL
    assert blocked_execution is None
    assert any(
        event.action.value == "KILL_SWITCH_TRIGGERED"
        for event in service.list_audit_events()
    )


def test_global_control_plane_kill_switch_also_blocks_pdd_send(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _configure(service)
    intake = _decision(foundation, "global-kill", "pdd-global-kill-conversation")
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "pdd-production-human")
    service.bind_execution(
        execution_id=enqueued.execution_id,
        store_id=STORE_ID,
        conversation_id="pdd-global-kill-conversation",
        operator="pdd-production-safety-operator",
        reason="PDD_EXECUTION_STORE_BIND_INTEGRATION",
    )
    queue = ExecutionQueue(foundation["uow_factory"], "pdd-global-kill-worker")
    lease = queue.claim()
    assert lease is not None
    with foundation["uow_factory"]() as uow:
        approval = uow.require_repository().get_approval_for_decision(
            intake.decision_id
        )
    assert approval is not None
    global_control = ControlPlaneService(foundation["uow_factory"])
    global_control.enable_kill_switch(
        operator="control-plane-operator",
        reason="GLOBAL_EMERGENCY_STOP",
    )
    sender = FakePDDHTTPSender()
    transport = PDDSendTransport(
        LedgerExecutionAuthorizationService(foundation["uow_factory"]),
        FakePDDSendSessionProvider(),
        sender,
        safety_gate=PDDProductionSafetyGate(
            service,
            global_control_plane=global_control,
        ),
    )

    with pytest.raises(PDDProductionSafetyDenied) as exc_info:
        transport.send_message(
            PDDApprovedExecutionContext(
                execution_id=enqueued.execution_id,
                decision_id=intake.decision_id,
                approval_id=approval.approval_id,
                approved_by=approval.decided_by,
                worker_id=lease.worker_id,
                lease_token=lease.lease_token,
                lease_expires_at=lease.lease_expires_at,
            )
        )

    assert exc_info.value.error_code == "PDD_GLOBAL_KILL_SWITCH_ENABLED"
    assert sender.send_count == 0
