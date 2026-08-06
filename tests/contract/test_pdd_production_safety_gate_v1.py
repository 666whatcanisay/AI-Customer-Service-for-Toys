from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    FakePDDHTTPSender,
    FakePDDSendSessionProvider,
    LedgerExecutionAuthorizationService,
    NormalizedMessage,
    PDD_PRODUCTION_CONFIRMATION_PHRASE,
    PDDApprovedExecutionContext,
    PDDCredentialReference,
    PDDEnvironmentProfile,
    PDDProductionSafetyDenied,
    PDDProductionSafetyGate,
    PDDProductionSafetyRepository,
    PDDProductionSafetyService,
    PDDRateLimitPolicy,
    PDDRateLimitReviewRequired,
    PDDSafetyAuditAction,
    PDDSafetyAuditEvent,
    PDDSendTransport,
    PDDStoreStatus,
    StoreAccount,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionQueue
from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy


STORE_ID = "pdd-safe-store-001"
COOKIE_REFERENCE = "secret-ref://pdd/fake/cookie-bundle"


def _account(
    *,
    store_id: str = STORE_ID,
    status: PDDStoreStatus = PDDStoreStatus.ALLOWLISTED,
    credential_ref: str = COOKIE_REFERENCE,
) -> StoreAccount:
    return StoreAccount(
        store_id=store_id,
        store_name="PDD Safety Fake Store",
        credential_reference=PDDCredentialReference(
            credential_ref=credential_ref,
            version="v1",
        ),
        environment=PDDEnvironmentProfile.PRODUCTION,
        status=status,
        updated_at=utc_now(),
    )


def _enable(
    service: PDDProductionSafetyService,
    *,
    dry_run: bool = True,
    rate_limit: PDDRateLimitPolicy | None = None,
) -> None:
    service.enable_production(
        confirmation_phrase=PDD_PRODUCTION_CONFIRMATION_PHRASE,
        operator="pdd-safety-operator",
        reason="PDD_PRODUCTION_TEST_ENABLE",
        dry_run=dry_run,
        rate_limit=rate_limit,
    )


def _approved_context(
    foundation,
    suffix: str,
    *,
    conversation_id: str | None = None,
) -> tuple[PDDApprovedExecutionContext, str]:
    external_conversation_id = conversation_id or f"pdd-safe-conversation-{suffix}"
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(
        NormalizedMessage(
            channel="pdd",
            conversation_id=external_conversation_id,
            external_message_id=f"pdd-safe-message-{suffix}",
            sender="fake-customer",
            content=f"PDD safety request {suffix}",
            timestamp=utc_now(),
        )
    )
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "pdd-safety-human")
    queue = ExecutionQueue(
        foundation["uow_factory"],
        f"pdd-safety-worker-{suffix}",
    )
    lease = queue.claim()
    assert lease is not None
    with foundation["uow_factory"]() as uow:
        approval = uow.require_repository().get_approval_for_decision(
            intake.decision_id
        )
    assert approval is not None
    return (
        PDDApprovedExecutionContext(
            execution_id=enqueued.execution_id,
            decision_id=intake.decision_id,
            approval_id=approval.approval_id,
            approved_by=approval.decided_by,
            worker_id=lease.worker_id,
            lease_token=lease.lease_token,
            lease_expires_at=lease.lease_expires_at,
        ),
        external_conversation_id,
    )


def _bind(
    service: PDDProductionSafetyService,
    context: PDDApprovedExecutionContext,
    conversation_id: str,
    *,
    store_id: str = STORE_ID,
) -> None:
    service.bind_execution(
        execution_id=context.execution_id,
        store_id=store_id,
        conversation_id=conversation_id,
        operator="pdd-safety-operator",
        reason="PDD_EXECUTION_STORE_BIND_TEST",
    )


def _transport(foundation, service: PDDProductionSafetyService):
    sender = FakePDDHTTPSender()
    sessions = FakePDDSendSessionProvider()
    transport = PDDSendTransport(
        LedgerExecutionAuthorizationService(foundation["uow_factory"]),
        sessions,
        sender,
        safety_gate=PDDProductionSafetyGate(service),
    )
    return transport, sender, sessions


def test_environment_defaults_mock_and_production_requires_exact_confirmation(
    foundation,
) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])

    state = service.status()

    assert state.environment is PDDEnvironmentProfile.MOCK
    assert state.production_enabled is False
    assert state.dry_run is True
    with pytest.raises(PDDProductionSafetyDenied) as exc_info:
        service.enable_production(
            confirmation_phrase="yes",
            operator="pdd-safety-operator",
            reason="PDD_PRODUCTION_TEST_ENABLE",
        )
    assert exc_info.value.error_code == "PDD_PRODUCTION_CONFIRMATION_REQUIRED"
    assert service.status() == state


def test_production_not_enabled_blocks_send_before_fake_sender(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    context, conversation_id = _approved_context(foundation, "not-enabled")
    _bind(service, context, conversation_id)
    transport, sender, sessions = _transport(foundation, service)

    with pytest.raises(PDDProductionSafetyDenied) as exc_info:
        transport.send_message(context)

    assert exc_info.value.error_code == "PDD_PRODUCTION_NOT_ENABLED"
    assert sender.send_count == 0
    assert sessions.secret_value_access_count == 0
    assert service.list_audit_events()[-1].action is PDDSafetyAuditAction.SEND_BLOCKED


def test_store_removed_from_allowlist_blocks_bound_execution(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _enable(service)
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    context, conversation_id = _approved_context(foundation, "store-blocked")
    _bind(service, context, conversation_id)
    service.set_store_status(
        STORE_ID,
        PDDStoreStatus.SUSPENDED,
        operator="pdd-safety-operator",
        reason="PDD_STORE_SUSPEND_TEST",
    )
    transport, sender, _sessions = _transport(foundation, service)

    with pytest.raises(PDDProductionSafetyDenied) as exc_info:
        transport.send_message(context)

    assert exc_info.value.error_code == "PDD_STORE_NOT_ALLOWLISTED"
    assert sender.send_count == 0


def test_pdd_kill_switch_immediately_blocks_new_send(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _enable(service)
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    context, conversation_id = _approved_context(foundation, "kill-switch")
    _bind(service, context, conversation_id)
    service.enable_kill_switch(
        operator="pdd-safety-operator",
        reason="PDD_EMERGENCY_STOP_TEST",
    )
    transport, sender, _sessions = _transport(foundation, service)

    with pytest.raises(PDDProductionSafetyDenied) as exc_info:
        transport.send_message(context)

    assert exc_info.value.error_code == "PDD_KILL_SWITCH_ENABLED"
    assert sender.send_count == 0
    actions = [event.action for event in service.list_audit_events()]
    assert PDDSafetyAuditAction.KILL_SWITCH_TRIGGERED in actions
    assert PDDSafetyAuditAction.SEND_BLOCKED in actions


def test_production_dry_run_completes_flow_without_real_send(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _enable(service, dry_run=True)
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    context, conversation_id = _approved_context(foundation, "dry-run")
    _bind(service, context, conversation_id)
    transport, sender, sessions = _transport(foundation, service)

    receipt = transport.send_message(context)

    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["environment"] == "PRODUCTION"
    assert receipt.details["store_id"] == STORE_ID
    assert receipt.details["dry_run"] is True
    assert receipt.details["real_platform_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert sender.send_count == 1
    assert sender.real_platform_call_count == 0
    assert sessions.secret_value_access_count == 0


def test_duplicate_dry_run_send_returns_original_receipt(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _enable(service)
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    context, conversation_id = _approved_context(foundation, "duplicate")
    _bind(service, context, conversation_id)
    transport, sender, _sessions = _transport(foundation, service)

    first = transport.send_message(context)
    duplicate = transport.send_message(context)
    restarted_transport, restarted_sender, _restarted_sessions = _transport(
        foundation,
        service,
    )
    restart_duplicate = restarted_transport.send_message(context)

    assert duplicate == first
    assert duplicate.receipt_id == first.receipt_id
    assert restart_duplicate == first
    assert restart_duplicate.receipt_id == first.receipt_id
    assert sender.send_count == 1
    assert restarted_sender.send_count == 0
    assert transport.replay_count == 1
    assert restarted_transport.replay_count == 1


def test_store_rate_limit_blocks_for_manual_review(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _enable(
        service,
        rate_limit=PDDRateLimitPolicy(
            store_per_minute=1,
            conversation_per_minute=1,
            store_per_day=10,
        ),
    )
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    first_context, first_conversation = _approved_context(foundation, "rate-first")
    second_context, second_conversation = _approved_context(
        foundation,
        "rate-second",
    )
    _bind(service, first_context, first_conversation)
    _bind(service, second_context, second_conversation)
    transport, sender, _sessions = _transport(foundation, service)

    first = transport.send_message(first_context)
    with pytest.raises(PDDRateLimitReviewRequired) as exc_info:
        transport.send_message(second_context)

    assert first.outcome is ReceiptOutcome.SUCCESS
    assert exc_info.value.error_code == "PDD_STORE_PER_MINUTE_REVIEW_REQUIRED"
    assert sender.send_count == 1
    blocked = [
        event
        for event in service.list_audit_events()
        if event.action is PDDSafetyAuditAction.SEND_BLOCKED
    ]
    assert blocked[-1].after["error_code"] == (
        "PDD_STORE_PER_MINUTE_REVIEW_REQUIRED"
    )


def test_conversation_and_rolling_daily_rate_dimensions_are_enforced(
    foundation,
) -> None:
    now = utc_now()
    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        repo = PDDProductionSafetyRepository(uow.session)
        first_allowed, first_error = repo.reserve_rate(
            execution_id="rate-dimension-execution-1",
            store_id=STORE_ID,
            conversation_id="rate-dimension-conversation-1",
            policy=PDDRateLimitPolicy(
                store_per_minute=5,
                conversation_per_minute=1,
                store_per_day=10,
            ),
            now=now,
        )
        conversation_allowed, conversation_error = repo.reserve_rate(
            execution_id="rate-dimension-execution-2",
            store_id=STORE_ID,
            conversation_id="rate-dimension-conversation-1",
            policy=PDDRateLimitPolicy(
                store_per_minute=5,
                conversation_per_minute=1,
                store_per_day=10,
            ),
            now=now,
        )
        daily_allowed, daily_error = repo.reserve_rate(
            execution_id="rate-dimension-execution-3",
            store_id=STORE_ID,
            conversation_id="rate-dimension-conversation-2",
            policy=PDDRateLimitPolicy(
                store_per_minute=1,
                conversation_per_minute=1,
                store_per_day=1,
            ),
            now=now + timedelta(seconds=61),
        )

    assert first_allowed is True and first_error is None
    assert conversation_allowed is False
    assert conversation_error == "PDD_CONVERSATION_RATE_REVIEW_REQUIRED"
    assert daily_allowed is False
    assert daily_error == "PDD_STORE_DAILY_REVIEW_REQUIRED"


def test_restart_with_reservation_but_no_receipt_fails_closed(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    _enable(service)
    service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    context, conversation_id = _approved_context(foundation, "crash-window")
    _bind(service, context, conversation_id)
    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        reserved, error = PDDProductionSafetyRepository(uow.session).reserve_rate(
            execution_id=context.execution_id,
            store_id=STORE_ID,
            conversation_id=conversation_id,
            policy=service.status().rate_limit,
            now=utc_now(),
        )
    assert reserved is True and error is None
    transport, sender, _sessions = _transport(foundation, service)

    with pytest.raises(PDDRateLimitReviewRequired) as exc_info:
        transport.send_message(context)

    assert exc_info.value.error_code == "PDD_SEND_RESERVATION_REVIEW_REQUIRED"
    assert sender.send_count == 0


def test_credential_reference_only_and_audit_leakage_scan(foundation) -> None:
    service = PDDProductionSafetyService(foundation["uow_factory"])
    account = service.allow_store(
        _account(),
        operator="pdd-safety-operator",
        reason="PDD_STORE_ALLOWLIST_TEST",
    )
    rotated = service.change_credential(
        STORE_ID,
        PDDCredentialReference(
            credential_ref="secret-ref://pdd/fake/cookie-bundle-v2",
            version="v2",
            expires_at=utc_now() + timedelta(days=1),
        ),
        operator="pdd-safety-operator",
        reason="PDD_CREDENTIAL_ROTATED",
    )

    assert account.credential_reference.credential_ref == COOKIE_REFERENCE
    assert rotated.credential_reference.version == "v2"
    with pytest.raises(ValidationError):
        PDDCredentialReference(  # type: ignore[call-arg]
            credential_ref="secret-ref://pdd/fake/ref",
            version="v1",
            cookie="raw-cookie-value",
        )
    with pytest.raises(ValidationError, match="sensitive"):
        PDDSafetyAuditEvent(
            audit_event_id="audit-leak-test",
            operator="pdd-safety-operator",
            action=PDDSafetyAuditAction.CREDENTIAL_CHANGED,
            timestamp=utc_now(),
            reason="PDD_CREDENTIAL_ROTATED",
            after={"cookie": "raw-cookie-value"},
        )
    audit_json = "\n".join(
        event.model_dump_json() for event in service.list_audit_events()
    )
    assert COOKIE_REFERENCE not in audit_json
    assert "cookie-bundle-v2" not in audit_json
    assert "raw-cookie-value" not in audit_json
    assert "token=" not in audit_json.casefold()
