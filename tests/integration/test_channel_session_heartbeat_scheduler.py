from __future__ import annotations

import time

from channel_engine.channel import FakeChannelAdapter
from channel_engine.reliability import ComponentHealth, StaticHealthProbe
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelInstanceStatus,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
    SessionHeartbeatScheduler,
)


def test_scheduler_checks_session_adapter_browser_gateway_independently(
    foundation,
) -> None:
    store = ChannelSessionStore(foundation["uow_factory"])
    references = tuple(
        CredentialReference(
            credential_ref=f"vault://scheduler/{store_id}",
            provider="test-vault",
            version="v1",
        )
        for store_id in ("store-a", "store-b")
    )
    provider = FakeCredentialProvider(references)
    delivery = MessageReliabilityService(foundation["uow_factory"], store)
    manager = ChannelInstanceManager(store, provider, delivery)
    adapters: dict[str, FakeChannelAdapter] = {}
    for store_id, credential_ref in zip(("store-a", "store-b"), references):
        adapter = FakeChannelAdapter(channel="fake", store_id=store_id)
        adapters[store_id] = adapter
        manager.create_instance(
            instance_id=f"scheduler-{store_id}",
            platform="fake",
            store_id=store_id,
            adapter_type="FakeChannelAdapter",
            credential_ref=credential_ref,
            adapter=adapter,
        )
    manager.start_all()
    browser = StaticHealthProbe()
    gateway = StaticHealthProbe()
    scheduler = SessionHeartbeatScheduler(
        manager,
        store,
        browser,
        gateway,
        interval_seconds=0.01,
    )

    healthy = scheduler.run_once()
    assert healthy.overall is ComponentHealth.HEALTHY
    assert len(healthy.instances) == 2

    adapters["store-b"].simulate_degraded("STORE_B_HEARTBEAT_FAILED")
    degraded = scheduler.run_once()
    reports = {item.instance_id: item for item in degraded.instances}
    assert reports["scheduler-store-a"].overall is ComponentHealth.HEALTHY
    assert reports["scheduler-store-b"].overall is ComponentHealth.UNHEALTHY
    assert manager.get_instance("scheduler-store-a").status is (
        ChannelInstanceStatus.CONNECTED
    )
    assert manager.get_instance("scheduler-store-b").status is (
        ChannelInstanceStatus.DEGRADED
    )
    assert len(store.latest_heartbeats()) == 2

    assert scheduler.start() is True
    deadline = time.monotonic() + 0.2
    while scheduler.run_count < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert scheduler.run_count >= 3
    assert scheduler.stop() is True
    assert scheduler.running is False
