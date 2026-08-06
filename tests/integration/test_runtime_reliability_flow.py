from __future__ import annotations

from channel_engine.reliability import (
    BrowserHealthProbe,
    ChannelRuntimeManager,
    ComponentHealth,
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


def test_start_degrade_recover_stop_integration(foundation) -> None:
    store = RuntimeReliabilityStore(foundation["uow_factory"])
    browser = FakeBrowserAdapter()
    channel = StaticHealthProbe()
    gateway = StaticHealthProbe()
    heartbeat = HeartbeatManager(
        "integration-runtime",
        store,
        {
            RuntimeComponent.CHANNEL: channel,
            RuntimeComponent.BROWSER: BrowserHealthProbe(browser),
            RuntimeComponent.GATEWAY: gateway,
            RuntimeComponent.STORAGE: StorageHealthProbe(foundation["uow_factory"]),
        },
    )
    recovery = RuntimeRecoveryCoordinator(
        "integration-runtime",
        store,
        {RuntimeComponent.BROWSER: browser.recover},
        max_attempts=2,
    )
    manager = ChannelRuntimeManager(
        "integration-runtime",
        browser,
        heartbeat,
        recovery,
        store,
    )

    assert manager.start().state is RuntimeLifecycleState.RUNNING
    assert manager.dashboard().health is ComponentHealth.HEALTHY

    browser.simulate_failure("FAKE_PAGE_CRASHED")
    pulse = manager.heartbeat()
    assert pulse.for_component(RuntimeComponent.BROWSER).health is (
        ComponentHealth.UNHEALTHY
    )
    assert manager.status().state is RuntimeLifecycleState.DEGRADED

    recovered = manager.recover()
    assert recovered.state is RecoveryState.RECOVERED
    assert manager.status().state is RuntimeLifecycleState.RUNNING
    assert manager.dashboard().health is ComponentHealth.HEALTHY

    assert manager.stop().state is RuntimeLifecycleState.STOPPED
    assert len(store.list_recovery_events("integration-runtime")) == 2
