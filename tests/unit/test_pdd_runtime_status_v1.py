from __future__ import annotations

from datetime import datetime, timezone

from channel_engine.browser import (
    BrowserLoginState,
    BrowserPageObserverHeartbeat,
    BrowserPageObserverState,
)
from channel_engine.pdd_adapter import (
    PDDMessageReaderHealth,
    PDDMessageReaderState,
    PDDRecoveryRuntimeStatus,
    PDDRuntimeHealth,
    PDDRuntimeStatusMonitor,
)
from channel_engine.session import (
    ChannelSession,
    ChannelSessionStatus,
    CredentialReference,
    MessageCursor,
)


NOW = datetime(2026, 8, 5, 16, 0, tzinfo=timezone.utc)


def test_pdd_runtime_status_aggregates_all_required_components() -> None:
    monitor = PDDRuntimeStatusMonitor(clock=lambda: NOW)
    session = ChannelSession(
        session_id="pdd-monitor-session",
        instance_id="pdd-monitor-instance",
        status=ChannelSessionStatus.CONNECTED,
        credential_ref=CredentialReference(
            credential_ref="vault://pdd/monitor/store-a",
            provider="test-vault",
            version="v1",
        ),
        credential_lease_ref="credential-lease-ref://pdd/monitor",
        heartbeat_time=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    cursor = MessageCursor(
        instance_id="pdd-monitor-instance",
        cursor_value="browser:cursor-4",
        last_sequence=4,
        last_acked_sequence=2,
        revision=6,
        updated_at=NOW,
    )
    browser = BrowserPageObserverHeartbeat(
        stream_id="pdd-browser:pdd-monitor-instance",
        observer_state=BrowserPageObserverState.ATTACHED,
        healthy=True,
        checked_at=NOW,
        page_context_id="pdd-monitor-page",
        page_generation=1,
        login_state=BrowserLoginState.AUTHENTICATED,
        page_write_operations=0,
    )
    adapter = PDDMessageReaderHealth(
        state=PDDMessageReaderState.CONNECTED,
        checked_at=NOW,
    )

    status = monitor.update(
        session=session,
        cursor=cursor,
        browser=browser,
        adapter=adapter,
        recovery=PDDRecoveryRuntimeStatus(
            health=PDDRuntimeHealth.DEGRADED,
            reason_code="PDD_RECOVERY_RETRY_SCHEDULED",
            attempts=2,
        ),
    )

    assert status.session.health is PDDRuntimeHealth.HEALTHY
    assert status.cursor.health is PDDRuntimeHealth.DEGRADED
    assert status.browser.health is PDDRuntimeHealth.HEALTHY
    assert status.adapter.health is PDDRuntimeHealth.HEALTHY
    assert status.recovery.health is PDDRuntimeHealth.DEGRADED
    assert status.cursor_backlog == 2
    assert status.recovery_attempts == 2
    assert status.overall is PDDRuntimeHealth.DEGRADED
    assert status.observe_only is True
    assert status.send_enabled is False
    assert status.real_platform_connected is False


def test_pdd_runtime_monitor_defaults_to_disabled_fail_closed() -> None:
    status = PDDRuntimeStatusMonitor(clock=lambda: NOW).snapshot()

    assert status.overall is PDDRuntimeHealth.DISABLED
    assert status.send_enabled is False
    assert status.real_platform_connected is False
    assert status.session.reason_code == "PDD_SESSION_DISABLED"
