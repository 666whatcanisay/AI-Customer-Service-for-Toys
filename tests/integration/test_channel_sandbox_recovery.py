from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from channel_engine.channel import (
    SandboxAckFailure,
    SandboxChannelAdapter,
    SandboxClock,
    SandboxDependencyProbe,
    SandboxGateway,
    SandboxGatewayTimeout,
    SandboxScenarioController,
    store_scoped_conversation_ref,
)
from channel_engine.conversation import ConversationService
from channel_engine.gateway import FakeGateway
from channel_engine.reliability import ComponentHealth
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelInstanceStatus,
    ChannelSessionStatus,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
    SessionHeartbeatScheduler,
)


NOW = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)


def sandbox_runtime(foundation):
    clock = SandboxClock(NOW)
    store = ChannelSessionStore(foundation["uow_factory"])
    credential = CredentialReference(
        credential_ref="vault://sandbox/store-a",
        provider="sandbox-vault",
        version="v1",
    )
    provider = FakeCredentialProvider(
        (credential,),
        lease_ttl=timedelta(minutes=5),
        clock=clock,
    )
    delivery = MessageReliabilityService(
        foundation["uow_factory"], store, clock=clock
    )
    manager = ChannelInstanceManager(store, provider, delivery, clock=clock)
    adapter = SandboxChannelAdapter(store_id="store-a", clock=clock)
    instance = manager.create_instance(
        instance_id="sandbox-instance-store-a",
        platform="sandbox",
        store_id="store-a",
        adapter_type="SandboxChannelAdapter",
        credential_ref=credential,
        adapter=adapter,
    )
    manager.start_instance(instance.instance_id)
    browser = SandboxDependencyProbe(
        healthy_reason="SANDBOX_BROWSER_HEALTHY", clock=clock
    )
    gateway = SandboxDependencyProbe(
        healthy_reason="SANDBOX_GATEWAY_HEALTHY", clock=clock
    )
    scheduler = SessionHeartbeatScheduler(
        manager,
        store,
        browser,
        gateway,
        interval_seconds=30,
        clock=clock,
    )
    scenario = SandboxScenarioController(
        adapter=adapter,
        manager=manager,
        instance_id=instance.instance_id,
        clock=clock,
        browser_probe=browser,
    )
    return clock, store, delivery, manager, adapter, scheduler, scenario


def test_ack_failure_replays_persisted_message_without_duplicate_processing(
    foundation,
) -> None:
    _clock, _store, delivery, manager, adapter, _scheduler, _scenario = (
        sandbox_runtime(foundation)
    )
    adapter.customer_message_received(
        message_id="sandbox-ack-message",
        conversation_id="sandbox-ack-conversation",
        content="synthetic message for persist-before-ACK",
    )
    adapter.ack_failure()

    with pytest.raises(SandboxAckFailure):
        manager.poll_messages("sandbox-instance-store-a")

    cursor_after_failure = delivery.get_cursor("sandbox-instance-store-a")
    assert cursor_after_failure.last_sequence == 1
    assert cursor_after_failure.last_acked_sequence == 0
    assert adapter.pending_count == 1

    replay = manager.poll_messages("sandbox-instance-store-a")
    assert len(replay) == 1
    acknowledged = delivery.ack(
        "sandbox-instance-store-a", replay[0].delivery_id
    )
    assert acknowledged.duplicate is False

    adapter.message_duplicate("sandbox-ack-message")
    assert manager.poll_messages("sandbox-instance-store-a") == ()
    final_cursor = delivery.get_cursor("sandbox-instance-store-a")
    assert final_cursor.last_sequence == 1
    assert final_cursor.last_acked_sequence == 1
    assert adapter.pending_count == 0
    assert adapter.source_ack_count == 1


def test_fault_heartbeat_recovery_isolated_and_bounded(foundation) -> None:
    _clock, store, _delivery, manager, adapter, scheduler, scenario = (
        sandbox_runtime(foundation)
    )
    initial_session = manager.view("sandbox-instance-store-a").session
    assert initial_session is not None

    adapter.network_failure()
    network_report = scheduler.run_once()
    assert network_report.overall is ComponentHealth.UNHEALTHY
    assert manager.get_instance("sandbox-instance-store-a").status is (
        ChannelInstanceStatus.DEGRADED
    )
    network_recovered = scenario.recover_channel()
    assert network_recovered.instance.status is ChannelInstanceStatus.CONNECTED
    assert network_recovered.session is not None
    assert network_recovered.session.session_id != initial_session.session_id

    adapter.adapter_crashed()
    scheduler.run_once()
    assert manager.get_instance("sandbox-instance-store-a").status is (
        ChannelInstanceStatus.DEGRADED
    )
    crash_recovered = scenario.recover_channel()
    assert crash_recovered.instance.status is ChannelInstanceStatus.CONNECTED

    scenario.disconnect_browser()
    browser_report = scheduler.run_once()
    assert browser_report.overall is ComponentHealth.UNHEALTHY
    assert manager.get_instance("sandbox-instance-store-a").status is (
        ChannelInstanceStatus.DEGRADED
    )
    scenario.recover_browser()
    browser_recovered = scenario.recover_channel()
    assert browser_recovered.instance.status is ChannelInstanceStatus.CONNECTED

    before_expiry = browser_recovered.session
    assert before_expiry is not None
    expired = scenario.expire_session()
    assert expired.instance.status is ChannelInstanceStatus.AUTH_REQUIRED
    assert expired.session is not None
    assert expired.session.status is ChannelSessionStatus.EXPIRED
    session_recovered = scenario.recover_channel()
    assert session_recovered.instance.status is ChannelInstanceStatus.CONNECTED
    assert session_recovered.session is not None
    assert session_recovered.session.status is ChannelSessionStatus.CONNECTED
    assert session_recovered.session.session_id != before_expiry.session_id
    assert len(store.list_sessions("sandbox-instance-store-a")) == 4


def test_gateway_timeout_keeps_inbox_recoverable_and_creates_no_partial_state(
    foundation,
) -> None:
    clock, _store, delivery, manager, adapter, _scheduler, _scenario = (
        sandbox_runtime(foundation)
    )
    adapter.customer_message_received(
        message_id="sandbox-gateway-message",
        conversation_id="sandbox-gateway-conversation",
        content="synthetic gateway timeout message",
    )
    first_delivery = manager.poll_messages("sandbox-instance-store-a")[0]
    gateway = SandboxGateway(FakeGateway())
    gateway.timeout_next()
    service = ConversationService(foundation["uow_factory"], gateway)

    with pytest.raises(SandboxGatewayTimeout):
        service.receive(first_delivery.message.to_runtime_message())

    scoped_ref = store_scoped_conversation_ref(
        "store-a", "sandbox-gateway-conversation"
    )
    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().find_conversation(
            "sandbox", scoped_ref
        ) is None

    delivery.mark_retry(
        "sandbox-instance-store-a",
        first_delivery.delivery_id,
        reason_code="GATEWAY_TIMEOUT",
        retry_after=timedelta(seconds=1),
    )
    clock.advance(timedelta(seconds=1))
    gateway.recover()
    retried = delivery.receive_pending("sandbox-instance-store-a")
    assert len(retried) == 1
    assert retried[0].delivery_attempt == 2
    assert retried[0].retry_marker is not None
    intake = service.receive(retried[0].message.to_runtime_message())
    delivery.ack("sandbox-instance-store-a", retried[0].delivery_id)

    assert intake.requires_approval is True
    assert gateway.timeout_count == 1
    assert delivery.get_cursor(
        "sandbox-instance-store-a"
    ).last_acked_sequence == 1
