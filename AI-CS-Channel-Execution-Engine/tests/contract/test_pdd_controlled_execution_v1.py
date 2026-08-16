from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealthStatus,
    ExecutionBoundaryDenied,
    FakeChannelAuthenticationBroker,
    FakePDDObservationTransport,
    FakePDDOutboundTransport,
    LedgerExecutionAuthorizationService,
    OutboundMessage,
    PDDControlledAdapter,
    PDDControlledExecutionAdapter,
    PDDControlledPolicyDecision,
    PDDControlledSendPolicy,
    PDDOutboundMode,
    PlatformAdapter,
)
from channel_engine.execution import ExecutionCommand
from channel_engine.models.entities import utc_now

from tests.pdd_controlled_support import pdd_credential


def test_pdd_controlled_adapter_exposes_only_fake_guarded_send(
    foundation,
) -> None:
    authorization = LedgerExecutionAuthorizationService(
        foundation["uow_factory"],
        authorization_ttl=timedelta(seconds=20),
    )
    outbound = FakePDDOutboundTransport()
    adapter = PDDControlledAdapter(
        pdd_credential(),
        FakeChannelAuthenticationBroker(),
        FakePDDObservationTransport(),
        authorization,
        outbound,
    )

    assert isinstance(adapter, PlatformAdapter)
    assert adapter.health_check().status is AdapterHealthStatus.UNHEALTHY
    session = adapter.connect()
    health = adapter.health_check()

    assert session.authenticated is True
    assert health.status is AdapterHealthStatus.HEALTHY
    assert health.real_platform_connected is False
    assert health.details["controlled_send_enabled"] is True
    assert health.details["send_policy"] == "ALLOW_SEND_MESSAGE"
    assert health.details["automatic_reply_enabled"] is False
    assert health.details["real_pdd_send_enabled"] is False
    assert outbound.real_platform_call_count == 0


def test_pdd_controlled_adapter_rejects_bare_message_and_unclaimed_execution(
    foundation,
) -> None:
    authorization = LedgerExecutionAuthorizationService(foundation["uow_factory"])
    outbound = FakePDDOutboundTransport()
    adapter = PDDControlledAdapter(
        pdd_credential(),
        FakeChannelAuthenticationBroker(),
        FakePDDObservationTransport(),
        authorization,
        outbound,
    )
    adapter.connect()
    message = OutboundMessage(
        channel="pdd",
        conversation_id="pdd-unapproved-conversation",
        execution_id="pdd-unapproved-execution",
        approved_by="unverified-operator",
        content="This message has no ledger approval.",
        idempotency_key="pdd-unapproved-send",
        requested_at=utc_now(),
    )

    with pytest.raises(ExecutionBoundaryDenied, match="bare outbound"):
        adapter.send_message(message)  # type: ignore[arg-type]
    with pytest.raises(ExecutionBoundaryDenied, match="source record is missing"):
        authorization.issue(
            execution_id="pdd-unapproved-execution",
            worker_id="forged-worker",
            execution_lease_token="forged-lease-token",
        )
    assert adapter.send_call_count == 0
    assert outbound.send_attempt_count == 0


def test_pdd_execution_bridge_rejects_direct_calls_without_worker_context(
    foundation,
) -> None:
    authorization = LedgerExecutionAuthorizationService(foundation["uow_factory"])
    adapter = PDDControlledAdapter(
        pdd_credential(),
        FakeChannelAuthenticationBroker(),
        FakePDDObservationTransport(),
        authorization,
        FakePDDOutboundTransport(),
    )
    bridge = PDDControlledExecutionAdapter(adapter, authorization)
    command = ExecutionCommand(
        execution_id="execution-direct-call",
        decision_id="decision-direct-call",
        proposed_content="Direct execution must remain forbidden.",
        idempotency_key="execution-direct-call",
    )

    with pytest.raises(ExecutionBoundaryDenied, match="claimed execution context"):
        bridge.execute(command)


def test_pdd_send_policy_has_one_allowed_operation() -> None:
    policy = PDDControlledSendPolicy()
    assert {decision.value for decision in PDDControlledPolicyDecision} == {
        "ALLOW_SEND_MESSAGE",
        "DENY",
    }

    with pytest.raises(ValidationError):
        OutboundMessage(
            channel="pdd",
            conversation_id="pdd-policy-conversation",
            execution_id="pdd-policy-execution",
            approved_by="human-operator",
            content="",
            idempotency_key="pdd-policy-send",
            requested_at=utc_now(),
        )


@pytest.mark.parametrize(
    "mode",
    [
        PDDOutboundMode.SUCCESS,
        PDDOutboundMode.FAILED,
        PDDOutboundMode.UNKNOWN,
        PDDOutboundMode.TIMEOUT,
    ],
)
def test_fake_pdd_outbound_modes_never_call_real_pdd(
    foundation,
    mode: PDDOutboundMode,
) -> None:
    outbound = FakePDDOutboundTransport(mode)
    authorization = LedgerExecutionAuthorizationService(foundation["uow_factory"])
    adapter = PDDControlledAdapter(
        pdd_credential(),
        FakeChannelAuthenticationBroker(),
        FakePDDObservationTransport(),
        authorization,
        outbound,
    )
    adapter.connect()

    assert outbound.real_platform_call_count == 0
    assert adapter.health_check().details["outbound_transport"].startswith("fake-")
