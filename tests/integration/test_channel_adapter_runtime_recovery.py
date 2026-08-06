from __future__ import annotations

from channel_engine.channel import (
    ChannelManager,
    ChannelManagerHealthProbe,
    FakeChannelAdapter,
)
from channel_engine.reliability import (
    BrowserHealthProbe,
    ChannelRuntimeManager,
    FakeBrowserAdapter,
    HeartbeatManager,
    RecoveryState,
    RuntimeComponent,
    RuntimeLifecycleState,
    RuntimeRecoveryCoordinator,
    RuntimeReliabilityStore,
    StaticHealthProbe,
    StorageHealthProbe,
)


def test_adapter_failure_heartbeat_and_bounded_recovery(foundation) -> None:
    channel_manager = ChannelManager()
    adapter = FakeChannelAdapter(failed_recovery_attempts=1)
    channel_manager.register(adapter)
    browser = FakeBrowserAdapter()
    store = RuntimeReliabilityStore(foundation["uow_factory"])
    heartbeat = HeartbeatManager(
        "adapter-runtime",
        store,
        {
            RuntimeComponent.CHANNEL: ChannelManagerHealthProbe(channel_manager),
            RuntimeComponent.BROWSER: BrowserHealthProbe(browser),
            RuntimeComponent.GATEWAY: StaticHealthProbe(),
            RuntimeComponent.STORAGE: StorageHealthProbe(foundation["uow_factory"]),
        },
    )
    recovery = RuntimeRecoveryCoordinator(
        "adapter-runtime",
        store,
        {RuntimeComponent.CHANNEL: channel_manager.recover_all},
        max_attempts=2,
    )
    runtime = ChannelRuntimeManager(
        "adapter-runtime",
        browser,
        heartbeat,
        recovery,
        store,
        channel_start=channel_manager.start_all,
        channel_stop=channel_manager.stop_all,
    )

    assert runtime.start().state is RuntimeLifecycleState.RUNNING
    adapter.simulate_degraded("FAKE_CHANNEL_CONNECTION_LOST")
    runtime.heartbeat()
    assert runtime.status().state is RuntimeLifecycleState.DEGRADED

    result = runtime.recover(RuntimeComponent.CHANNEL)

    assert result.state is RecoveryState.RECOVERED
    assert result.attempts == 2
    assert adapter.recovery_count == 2
    assert runtime.status().state is RuntimeLifecycleState.RUNNING
    assert channel_manager.status().connected_count == 1
