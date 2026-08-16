from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealthStatus,
    FakePDDHTTPSender,
    FakePDDHTTPSenderMode,
    FakePDDSendSessionProvider,
    LedgerExecutionAuthorizationService,
    PDDApprovedExecutionContext,
    PDDHTTPRequestBuilder,
    PDDHTTPSender,
    PDDSendSafetyError,
    PDDSendTransport,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionQueue
from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy
from channel_engine.channel import NormalizedMessage


def _approved_context(foundation, suffix: str) -> PDDApprovedExecutionContext:
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(
        NormalizedMessage(
            channel="pdd",
            conversation_id=f"pdd-send-conversation-{suffix}",
            external_message_id=f"pdd-send-inbound-{suffix}",
            sender="fake-customer",
            content=f"controlled send request {suffix}",
            timestamp=utc_now(),
        )
    )
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "pdd-send-human-operator")
    queue = ExecutionQueue(
        foundation["uow_factory"],
        f"pdd-send-worker-{suffix}",
    )
    lease = queue.claim()
    assert lease is not None
    with foundation["uow_factory"]() as uow:
        approval = uow.require_repository().get_approval_for_decision(
            intake.decision_id
        )
    assert approval is not None
    return PDDApprovedExecutionContext(
        execution_id=enqueued.execution_id,
        decision_id=intake.decision_id,
        approval_id=approval.approval_id,
        approved_by=approval.decided_by,
        worker_id=lease.worker_id,
        lease_token=lease.lease_token,
        lease_expires_at=lease.lease_expires_at,
    )


def _transport(
    foundation,
    *,
    mode: FakePDDHTTPSenderMode = FakePDDHTTPSenderMode.SUCCESS,
):
    sender = FakePDDHTTPSender(mode)
    sessions = FakePDDSendSessionProvider()
    transport = PDDSendTransport(
        LedgerExecutionAuthorizationService(foundation["uow_factory"]),
        sessions,
        sender,
    )
    return transport, sender, sessions


def test_send_contract_is_context_only_and_http_boundary_is_abstract(
    foundation,
) -> None:
    transport, sender, sessions = _transport(foundation)

    assert isinstance(sender, PDDHTTPSender)
    assert isinstance(transport.request_builder, PDDHTTPRequestBuilder)
    assert transport.health_check().status is AdapterHealthStatus.HEALTHY
    assert sessions.secret_value_access_count == 0

    with pytest.raises(PDDSendSafetyError) as exc_info:
        transport.send_message("bare reply")  # type: ignore[arg-type]
    assert exc_info.value.error_code == "PDD_APPROVED_EXECUTION_CONTEXT_REQUIRED"
    assert sender.send_count == 0


def test_v1_constructor_rejects_sender_capable_of_real_platform_calls(
    foundation,
) -> None:
    class ForbiddenRealSender(FakePDDHTTPSender):
        real_platform_transport = True

    with pytest.raises(PDDSendSafetyError) as exc_info:
        PDDSendTransport(
            LedgerExecutionAuthorizationService(foundation["uow_factory"]),
            FakePDDSendSessionProvider(),
            ForbiddenRealSender(),
        )

    assert exc_info.value.error_code == "PDD_REAL_SEND_FORBIDDEN"


def test_fake_http_sender_builds_reference_only_request_and_success_receipt(
    foundation,
) -> None:
    context = _approved_context(foundation, "fake-success")
    transport, sender, sessions = _transport(foundation)

    receipt = transport.send_message(context)

    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.external_message_id == f"fake-pdd-http:pdd-outbound:{context.decision_id}"
    assert receipt.details["trigger_state"] == "TRIGGERED_CONFIRMED"
    assert receipt.details["automatic_retry_allowed"] is False
    assert receipt.details["real_platform_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert sender.send_count == 1
    assert sender.trigger_count == 1
    assert sender.real_platform_call_count == 0
    request = sender.requests[0]
    assert request.execution_id == context.execution_id
    assert request.decision_id == context.decision_id
    assert request.approval_id == context.approval_id
    assert request.message_id == f"pdd-outbound:{context.decision_id}"
    assert request.send_key == receipt.idempotency_key
    assert request.endpoint_reference.startswith("endpoint-ref://")
    assert request.session_reference.startswith("session-ref://")
    assert request.cookie_reference.startswith("secret-ref://")
    assert "http://" not in request.endpoint_reference
    assert "https://" not in request.endpoint_reference
    assert sessions.secret_value_access_count == 0
    health_json = transport.health_check().model_dump_json()
    assert "session-ref://" not in health_json
    assert "secret-ref://" not in health_json
    receipt_json = receipt.model_dump_json()
    assert "session-ref://" not in receipt_json
    assert "secret-ref://" not in receipt_json
    assert request.body.content not in receipt_json


def test_execution_message_and_send_key_duplicate_returns_original_receipt(
    foundation,
) -> None:
    context = _approved_context(foundation, "duplicate")
    transport, sender, _sessions = _transport(foundation)

    first = transport.send_message(context)
    replay = transport.send_message(context)

    assert replay is first
    assert replay.receipt_id == first.receipt_id
    assert sender.send_count == 1
    assert sender.trigger_count == 1
    assert transport.replay_count == 1
    record = transport.receipt_store.get_by_execution_id(context.execution_id)
    assert record is not None
    assert record.message_id == f"pdd-outbound:{context.decision_id}"
    assert record.send_key == first.idempotency_key
    assert (
        transport.receipt_store.find_any(
            execution_id=record.execution_id,
            message_id=record.message_id,
            send_key=record.send_key,
        )
        == record
    )
    with pytest.raises(ValidationError, match="frozen"):
        first.outcome = ReceiptOutcome.UNKNOWN  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mode", "expected_outcome", "expected_error", "trigger_state"),
    [
        (
            FakePDDHTTPSenderMode.FAILED,
            ReceiptOutcome.FAILED,
            "FAKE_PDD_HTTP_REJECTED",
            "NOT_TRIGGERED",
        ),
        (
            FakePDDHTTPSenderMode.PRE_TRIGGER_TIMEOUT,
            ReceiptOutcome.FAILED,
            "PDD_SEND_PRE_TRIGGER_TIMEOUT",
            "NOT_TRIGGERED",
        ),
        (
            FakePDDHTTPSenderMode.TIMEOUT,
            ReceiptOutcome.UNKNOWN,
            "PDD_SEND_TIMEOUT_UNKNOWN",
            "TRIGGERED_UNCONFIRMED",
        ),
        (
            FakePDDHTTPSenderMode.UNKNOWN,
            ReceiptOutcome.UNKNOWN,
            "FAKE_PDD_CONFIRMATION_MISSING",
            "TRIGGERED_UNCONFIRMED",
        ),
    ],
)
def test_response_and_timeout_mapping_is_fail_closed_and_never_retried(
    foundation,
    mode: FakePDDHTTPSenderMode,
    expected_outcome: ReceiptOutcome,
    expected_error: str,
    trigger_state: str,
) -> None:
    context = _approved_context(foundation, mode.value.lower())
    transport, sender, _sessions = _transport(foundation, mode=mode)

    receipt = transport.send_message(context)
    replay = transport.send_message(context)

    assert receipt.outcome is expected_outcome
    assert receipt.error_code == expected_error
    assert receipt.details["trigger_state"] == trigger_state
    assert receipt.details["automatic_retry_allowed"] is False
    assert receipt.details["reconciliation_required"] is (
        expected_outcome is ReceiptOutcome.UNKNOWN
    )
    assert replay is receipt
    assert sender.send_count == 1


def test_invalid_approval_context_fails_before_session_and_sender(foundation) -> None:
    context = _approved_context(foundation, "bad-approval")
    transport, sender, sessions = _transport(foundation)
    forged = context.model_copy(update={"approval_id": "approval-forged"})

    with pytest.raises(PDDSendSafetyError) as exc_info:
        transport.send_message(forged)

    assert exc_info.value.error_code == "PDD_APPROVED_CONTEXT_MISMATCH"
    assert sessions.lookup_count == 0
    assert sender.send_count == 0
    assert sender.trigger_count == 0


def test_expired_session_records_failed_receipt_without_trigger(foundation) -> None:
    context = _approved_context(foundation, "expired-session")
    transport, sender, sessions = _transport(foundation)
    sessions.expire()

    receipt = transport.send_message(context)
    replay = transport.send_message(context)

    assert receipt.outcome is ReceiptOutcome.FAILED
    assert receipt.error_code == "PDD_SEND_SESSION_EXPIRED"
    assert receipt.details["trigger_state"] == "NOT_TRIGGERED"
    assert replay is receipt
    assert sender.send_count == 0
    assert sender.trigger_count == 0
    assert transport.health_check().status is AdapterHealthStatus.UNHEALTHY


def test_expired_execution_lease_is_rejected_before_authorization(foundation) -> None:
    context = _approved_context(foundation, "expired-lease")
    transport, sender, sessions = _transport(foundation)
    expired = context.model_copy(
        update={"lease_expires_at": utc_now() - timedelta(seconds=1)}
    )

    with pytest.raises(PDDSendSafetyError) as exc_info:
        transport.send_message(expired)

    assert exc_info.value.error_code == "PDD_EXECUTION_LEASE_EXPIRED"
    assert sessions.lookup_count == 0
    assert sender.send_count == 0
