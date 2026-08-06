from __future__ import annotations

from datetime import datetime, timedelta, timezone

from channel_engine.channel import ChannelMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker, FakeExecutionAdapter
from channel_engine.models import (
    Approval,
    ApprovalState,
    Execution,
    ExecutionState,
    ReceiptOutcome,
)
from channel_engine.policy import ApprovalPolicy
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


class TickClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(milliseconds=1)
        return value


def build_runtime(foundation, *, failed_recovery_attempts: int = 0):
    clock = TickClock()
    store = RuntimeReliabilityStore(foundation["uow_factory"])
    browser = FakeBrowserAdapter(
        failed_recovery_attempts=failed_recovery_attempts,
        clock=clock,
    )
    channel = StaticHealthProbe()
    gateway = StaticHealthProbe()
    heartbeat = HeartbeatManager(
        "test-runtime",
        store,
        {
            RuntimeComponent.CHANNEL: channel,
            RuntimeComponent.BROWSER: BrowserHealthProbe(browser),
            RuntimeComponent.GATEWAY: gateway,
            RuntimeComponent.STORAGE: StorageHealthProbe(foundation["uow_factory"]),
        },
        clock=clock,
    )
    recovery = RuntimeRecoveryCoordinator(
        "test-runtime",
        store,
        {
            RuntimeComponent.BROWSER: browser.recover,
            RuntimeComponent.CHANNEL: channel.recover,
            RuntimeComponent.GATEWAY: gateway.recover,
        },
        max_attempts=2,
        clock=clock,
    )
    manager = ChannelRuntimeManager(
        "test-runtime",
        browser,
        heartbeat,
        recovery,
        store,
        clock=clock,
    )
    return manager, store, browser, channel, gateway


def test_lifecycle_state_machine_is_persistent_and_versioned(foundation) -> None:
    manager, store, browser, _, _ = build_runtime(foundation)

    assert manager.status().state is RuntimeLifecycleState.STOPPED
    running = manager.start()
    stopped = manager.stop()

    assert running.state is RuntimeLifecycleState.RUNNING
    assert running.generation == 1
    assert stopped.state is RuntimeLifecycleState.STOPPED
    assert browser.start_count == 1
    assert browser.stop_count == 1
    assert [event.to_state for event in store.list_lifecycle_events("test-runtime")] == [
        RuntimeLifecycleState.STOPPED,
        RuntimeLifecycleState.STARTING,
        RuntimeLifecycleState.READY,
        RuntimeLifecycleState.RUNNING,
        RuntimeLifecycleState.STOPPING,
        RuntimeLifecycleState.STOPPED,
    ]
    assert all(
        event.reliability_version == "1.0"
        for event in store.list_lifecycle_events("test-runtime")
    )

    replacement, _, _, _, _ = build_runtime(foundation)
    assert replacement.status().state is RuntimeLifecycleState.STOPPED
    assert replacement.status().revision == stopped.revision


def test_heartbeat_records_all_components_and_degrades_runtime(foundation) -> None:
    manager, store, browser, _, _ = build_runtime(foundation)
    manager.start()
    browser.simulate_failure()

    report = manager.heartbeat()

    assert report.overall is ComponentHealth.UNHEALTHY
    assert {item.component for item in report.components} == set(RuntimeComponent)
    assert manager.status().state is RuntimeLifecycleState.DEGRADED
    persisted = store.latest_heartbeat("test-runtime")
    assert persisted is not None
    assert persisted.cycle_id == report.cycle_id
    assert persisted.for_component(RuntimeComponent.BROWSER).reason_code == (
        "FAKE_PAGE_UNAVAILABLE"
    )
    assert persisted.for_component(RuntimeComponent.BROWSER).process_running is True
    assert persisted.for_component(RuntimeComponent.BROWSER).page_available is False
    assert persisted.for_component(RuntimeComponent.BROWSER).available is False


def test_browser_start_failure_is_fail_closed(foundation) -> None:
    manager, _, browser, _, _ = build_runtime(foundation)
    browser.fail_start = True

    status = manager.start()

    assert status.state is RuntimeLifecycleState.FAILED
    assert status.reason_code == "BROWSER_START_FAILED"
    assert browser.health_check().real_browser_connected is False


def test_restart_loads_durable_state_and_detects_process_loss(foundation) -> None:
    manager, _, _, _, _ = build_runtime(foundation)
    running = manager.start()

    replacement, _, replacement_browser, _, _ = build_runtime(foundation)

    assert replacement.status().state is RuntimeLifecycleState.RUNNING
    assert replacement.status().revision == running.revision
    assert replacement_browser.health_check().process_running is False
    replacement.heartbeat()
    assert replacement.status().state is RuntimeLifecycleState.DEGRADED


def test_recovery_is_bounded_and_returns_to_running(foundation) -> None:
    manager, store, browser, _, _ = build_runtime(
        foundation, failed_recovery_attempts=1
    )
    manager.start()
    browser.simulate_failure()
    manager.heartbeat()

    result = manager.recover(RuntimeComponent.BROWSER)

    assert result.state is RecoveryState.RECOVERED
    assert result.attempts == 2
    assert [event.state for event in result.events] == [
        RecoveryState.RECOVERING,
        RecoveryState.RECOVERING,
        RecoveryState.RECOVERED,
    ]
    assert browser.recovery_count == 2
    assert manager.status().state is RuntimeLifecycleState.RUNNING
    assert store.latest_recovery_event("test-runtime").state is RecoveryState.RECOVERED


def test_recovery_budget_exhaustion_requires_manual_intervention(foundation) -> None:
    manager, store, browser, _, _ = build_runtime(
        foundation, failed_recovery_attempts=10
    )
    manager.start()
    browser.simulate_failure()
    manager.heartbeat()

    result = manager.recover(RuntimeComponent.BROWSER)

    assert result.state is RecoveryState.MANUAL_INTERVENTION
    assert result.attempts == 2
    assert browser.recovery_count == 2
    assert manager.status().state is RuntimeLifecycleState.FAILED
    assert store.latest_recovery_event("test-runtime").reason_code == (
        "RECOVERY_BUDGET_EXHAUSTED"
    )


def test_unapproved_execution_is_never_claimed_or_sent(foundation) -> None:
    conversation = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    )
    intake = conversation.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="unapproved-runtime-conversation",
            external_message_id="unapproved-runtime-message",
            text="must not execute without approval",
        )
    )
    approval = Approval(
        decision_id=intake.decision_id,
        state=ApprovalState.PENDING,
    )
    execution = Execution(
        decision_id=intake.decision_id,
        approval_id=approval.approval_id,
        idempotency_key="unsafe-execution-must-be-blocked",
    )
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        repo.save_approval(approval)
        repo.save_execution(execution)

    adapter = FakeExecutionAdapter()
    worker = ExecutionWorker(foundation["uow_factory"], adapter, "safety-worker")
    manager, store, _, _, _ = build_runtime(foundation)

    assert worker.run_once() is None
    assert adapter.call_count == 0
    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().get_execution(execution.execution_id).state is (
            ExecutionState.PENDING
        )
    status = store.execution_status()
    assert status.unapproved_active == 1
    assert manager.dashboard().health is ComponentHealth.UNHEALTHY


def test_unknown_has_receipt_and_is_not_automatically_retried(foundation) -> None:
    conversation = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    )
    intake = conversation.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="unknown-reliability-conversation",
            external_message_id="unknown-reliability-message",
            text="simulate uncertain outcome",
        )
    )
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    ).approve_and_enqueue(intake.decision_id, "human-operator")
    adapter = FakeExecutionAdapter(outcome=ReceiptOutcome.UNKNOWN)
    worker = ExecutionWorker(foundation["uow_factory"], adapter, "unknown-worker")

    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_id is not None
    assert worker.run_once() is None
    assert adapter.call_count == 1
    store = RuntimeReliabilityStore(foundation["uow_factory"])
    status = store.execution_status()
    assert status.unknown == 1
    assert status.terminal_without_receipt == 0
    assert status.unknown_auto_retry_allowed is False
    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        ) is not None
