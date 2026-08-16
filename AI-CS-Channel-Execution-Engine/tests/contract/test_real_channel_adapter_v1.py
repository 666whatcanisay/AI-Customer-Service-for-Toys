from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealthStatus,
    AuthorizedOutboundMessage,
    ChannelAuthenticationFailed,
    ChannelAuthenticationScheme,
    ChannelConnectionState,
    ChannelCredentialReference,
    ChannelSessionUnavailable,
    ExecutionBoundaryDenied,
    FakeChannelAuthenticationBroker,
    FakeChannelHeartbeatProbe,
    FakePlatformAdapterV1,
    FakePlatformInboundMessage,
    LedgerExecutionAuthorizationService,
    NormalizedMessage,
    OutboundMessage,
    PlatformAdapter,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionQueue
from channel_engine.models import ExecutionState, ReceiptOutcome
from channel_engine.policy import ApprovalPolicy


CHANNEL = "contract-channel"


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def credential(**updates: object) -> ChannelCredentialReference:
    values: dict[str, object] = {
        "credential_id": "secret-manager/channel/contract-account",
        "provider": "secret-manager",
        "version": "version-7",
        "account_ref": "contract-account-ref",
        "auth_scheme": ChannelAuthenticationScheme.API_TOKEN,
    }
    values.update(updates)
    return ChannelCredentialReference.model_validate(values)


def adapter_for(
    foundation,
    clock: FakeClock,
    *,
    outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
    broker: FakeChannelAuthenticationBroker | None = None,
    probe: FakeChannelHeartbeatProbe | None = None,
):
    authorization = LedgerExecutionAuthorizationService(
        foundation["uow_factory"],
        authorization_ttl=timedelta(seconds=20),
        clock=clock,
    )
    adapter = FakePlatformAdapterV1(
        CHANNEL,
        credential(),
        authorization,
        authentication_broker=broker,
        heartbeat_probe=probe,
        send_outcome=outcome,
        clock=clock,
    )
    return adapter, authorization


def approved_running_command(foundation, clock: FakeClock, suffix: str):
    inbound = NormalizedMessage(
        channel=CHANNEL,
        conversation_id=f"conversation-{suffix}",
        external_message_id=f"message-{suffix}",
        sender=f"customer-{suffix}",
        content="Please prepare a low-risk reply.",
        timestamp=clock(),
    )
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(inbound)
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "contract-human-operator")
    queue = ExecutionQueue(
        foundation["uow_factory"],
        "contract-send-worker",
        lease_duration=timedelta(seconds=30),
        clock=clock,
    )
    lease = queue.claim()
    assert lease is not None
    assert lease.execution.state is ExecutionState.RUNNING
    authorization = LedgerExecutionAuthorizationService(
        foundation["uow_factory"],
        authorization_ttl=timedelta(seconds=20),
        clock=clock,
    )
    command = authorization.issue(
        execution_id=enqueued.execution_id,
        worker_id=lease.worker_id,
        execution_lease_token=lease.lease_token,
    )
    return intake, enqueued, lease, command


def test_platform_adapter_contract_and_lifecycle_are_explicit(foundation) -> None:
    clock = FakeClock()
    probe = FakeChannelHeartbeatProbe(healthy=True)
    adapter, _authorization = adapter_for(foundation, clock, probe=probe)

    assert isinstance(adapter, PlatformAdapter)
    assert adapter.get_session() is None
    assert adapter.health_check().status is AdapterHealthStatus.UNHEALTHY

    session = adapter.connect()
    heartbeat = adapter.heartbeat()

    assert session.authenticated is True
    assert session.channel == CHANNEL
    assert session.account_ref == "contract-account-ref"
    assert heartbeat.status.value == "OK"
    assert probe.call_count == 1
    assert adapter.health_check().status is AdapterHealthStatus.HEALTHY
    assert adapter.health_check().real_platform_connected is False
    assert adapter.lifecycle.transition_history == (
        ChannelConnectionState.DISCONNECTED,
        ChannelConnectionState.CONNECTING,
        ChannelConnectionState.AUTHENTICATING,
        ChannelConnectionState.CONNECTED,
        ChannelConnectionState.CONNECTED,
    )

    adapter.disconnect()
    assert adapter.get_session() is None
    assert adapter.lifecycle.connection.state is ChannelConnectionState.DISCONNECTED


def test_authentication_failure_and_heartbeat_degradation_fail_closed(
    foundation,
) -> None:
    clock = FakeClock()
    rejected_broker = FakeChannelAuthenticationBroker(
        clock=clock,
        reject_authentication=True,
    )
    rejected, _authorization = adapter_for(
        foundation,
        clock,
        broker=rejected_broker,
    )

    with pytest.raises(ChannelAuthenticationFailed):
        rejected.connect()
    assert (
        rejected.lifecycle.connection.state
        is ChannelConnectionState.AUTHENTICATION_FAILED
    )
    assert rejected.health_check().status is AdapterHealthStatus.UNHEALTHY

    probe = FakeChannelHeartbeatProbe(healthy=False)
    degraded, _authorization = adapter_for(foundation, clock, probe=probe)
    degraded.connect()
    heartbeat = degraded.heartbeat()
    assert heartbeat.status.value == "FAILED"
    assert degraded.health_check().status is AdapterHealthStatus.DEGRADED
    with pytest.raises(ChannelSessionUnavailable):
        degraded.receive_message()

    probe.healthy = True
    assert degraded.heartbeat().status.value == "OK"
    assert degraded.health_check().status is AdapterHealthStatus.HEALTHY

    clock.advance(timedelta(minutes=11))
    assert degraded.heartbeat().status.value == "SESSION_EXPIRED"
    assert degraded.health_check().status is AdapterHealthStatus.DEGRADED


def test_credentials_and_sessions_never_contain_plaintext_secrets(foundation) -> None:
    clock = FakeClock()
    reference = credential()
    adapter, _authorization = adapter_for(foundation, clock)
    session = adapter.connect()

    reference_payload = reference.model_dump(mode="json")
    session_payload = session.model_dump(mode="json")
    prohibited = {"token", "secret", "password", "cookie", "session_token"}

    assert prohibited.isdisjoint(reference_payload)
    assert prohibited.isdisjoint(session_payload)
    assert reference_payload["credential_id"].startswith("secret-manager/")
    assert "plaintext-platform-value" not in reference.model_dump_json()
    assert "plaintext-platform-value" not in session.model_dump_json()
    with pytest.raises(ValidationError):
        ChannelCredentialReference.model_validate(
            {
                **reference_payload,
                "token": "plaintext-platform-value",
            }
        )
    health_text = adapter.health_check().model_dump_json()
    assert "plaintext-platform-value" not in health_text
    assert '"automatic_send_enabled":false' in health_text


def test_external_message_is_normalized_and_idempotent(foundation) -> None:
    clock = FakeClock()
    adapter, _authorization = adapter_for(foundation, clock)
    raw = FakePlatformInboundMessage(
        conversation_ref="external-conversation-1",
        message_ref="external-message-1",
        sender_ref="external-customer-1",
        text="Where is the synthetic order?",
        occurred_at=clock(),
    )

    assert adapter.enqueue_external_message(raw) is True
    assert adapter.enqueue_external_message(raw) is False
    with pytest.raises(ChannelSessionUnavailable):
        adapter.receive_message()

    adapter.connect()
    normalized = adapter.receive_message()

    assert normalized == NormalizedMessage(
        channel=CHANNEL,
        conversation_id="external-conversation-1",
        external_message_id="external-message-1",
        sender="external-customer-1",
        content="Where is the synthetic order?",
        timestamp=clock(),
    )
    assert adapter.receive_message() is None
    with pytest.raises(ValueError, match="different content"):
        adapter.enqueue_external_message(
            raw.model_copy(update={"text": "Changed content"})
        )


def test_adapter_rejects_direct_send_and_pending_execution(foundation) -> None:
    clock = FakeClock()
    adapter, authorization = adapter_for(foundation, clock)
    adapter.connect()
    raw_message = OutboundMessage(
        channel=CHANNEL,
        conversation_id="external-conversation",
        execution_id="execution-without-proof",
        approved_by="unverified-operator",
        content="This must not be sent.",
        idempotency_key="send-without-proof",
        requested_at=clock(),
    )
    with pytest.raises(ExecutionBoundaryDenied, match="without execution"):
        adapter.send_message(raw_message)  # type: ignore[arg-type]

    inbound = NormalizedMessage(
        channel=CHANNEL,
        conversation_id="pending-conversation",
        external_message_id="pending-message",
        sender="pending-customer",
        content="Prepare a reply but do not send it.",
        timestamp=clock(),
    )
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(inbound)
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "contract-human-operator")
    with pytest.raises(ExecutionBoundaryDenied, match="not RUNNING"):
        authorization.issue(
            execution_id=enqueued.execution_id,
            worker_id="contract-send-worker",
            execution_lease_token="forged-lease-token",
        )
    assert adapter.send_call_count == 0


@pytest.mark.parametrize(
    "outcome",
    [
        ReceiptOutcome.SUCCESS,
        ReceiptOutcome.FAILED,
        ReceiptOutcome.UNKNOWN,
    ],
)
def test_authorized_fake_send_returns_immutable_idempotent_receipt(
    foundation,
    outcome: ReceiptOutcome,
) -> None:
    clock = FakeClock()
    adapter, _authorization = adapter_for(foundation, clock, outcome=outcome)
    adapter.connect()
    _intake, _enqueued, _lease, command = approved_running_command(
        foundation,
        clock,
        outcome.value.lower(),
    )

    first = adapter.send_message(command)
    replay = adapter.send_message(command)

    assert replay == first
    assert command.authorization.operation == "SEND_MESSAGE"
    assert command.authorization.execution_risk == "LOW"
    assert first.outcome is outcome
    assert first.details["real_platform_called"] is False
    assert first.details["customer_message_sent"] is False
    assert first.details["refund_performed"] is False
    assert first.details["order_modified"] is False
    assert adapter.send_call_count == 1
    with pytest.raises(ValidationError):
        first.outcome = ReceiptOutcome.UNKNOWN  # type: ignore[misc]


def test_ledger_verifier_rejects_tampering_forged_lease_and_expiry(
    foundation,
) -> None:
    clock = FakeClock()
    adapter, authorization = adapter_for(foundation, clock)
    adapter.connect()
    _intake, _enqueued, _lease, command = approved_running_command(
        foundation,
        clock,
        "tamper",
    )

    tampered = command.model_copy(
        update={
            "message": command.message.model_copy(
                update={"content": "Unapproved replacement content"}
            )
        }
    )
    with pytest.raises(ExecutionBoundaryDenied, match="does not match"):
        adapter.send_message(tampered)

    forged = AuthorizedOutboundMessage(
        message=command.message,
        authorization=command.authorization.model_copy(
            update={"execution_lease_token": "forged-current-lease"}
        ),
    )
    with pytest.raises(ExecutionBoundaryDenied, match="no longer authorizes"):
        adapter.send_message(forged)

    expanded_operation = AuthorizedOutboundMessage(
        message=command.message,
        authorization=command.authorization.model_copy(
            update={"operation": "REFUND", "execution_risk": "HIGH"}
        ),
    )
    with pytest.raises(ExecutionBoundaryDenied, match="low-risk message send"):
        adapter.send_message(expanded_operation)

    clock.advance(timedelta(seconds=21))
    with pytest.raises(ExecutionBoundaryDenied, match="expired"):
        authorization.verify(command)
    assert adapter.send_call_count == 0
