from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from channel_engine.models.entities import utc_now

from .browser import BrowserManager
from .heartbeat import HeartbeatManager
from .models import (
    ComponentHealth,
    HeartbeatReport,
    RecoveryResult,
    RecoveryState,
    RuntimeComponent,
    RuntimeDashboardStatus,
    RuntimeLifecycleSnapshot,
    RuntimeLifecycleState,
)
from .persistence import RuntimeReliabilityStore
from .recovery import RuntimeRecoveryCoordinator


class InvalidRuntimeTransition(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[
    RuntimeLifecycleState, frozenset[RuntimeLifecycleState]
] = {
    RuntimeLifecycleState.STOPPED: frozenset({RuntimeLifecycleState.STARTING}),
    RuntimeLifecycleState.STARTING: frozenset(
        {
            RuntimeLifecycleState.READY,
            RuntimeLifecycleState.DEGRADED,
            RuntimeLifecycleState.FAILED,
            RuntimeLifecycleState.STOPPING,
        }
    ),
    RuntimeLifecycleState.READY: frozenset(
        {
            RuntimeLifecycleState.RUNNING,
            RuntimeLifecycleState.DEGRADED,
            RuntimeLifecycleState.STOPPING,
            RuntimeLifecycleState.FAILED,
        }
    ),
    RuntimeLifecycleState.RUNNING: frozenset(
        {
            RuntimeLifecycleState.DEGRADED,
            RuntimeLifecycleState.STOPPING,
            RuntimeLifecycleState.FAILED,
        }
    ),
    RuntimeLifecycleState.DEGRADED: frozenset(
        {
            RuntimeLifecycleState.RUNNING,
            RuntimeLifecycleState.STOPPING,
            RuntimeLifecycleState.FAILED,
        }
    ),
    RuntimeLifecycleState.STOPPING: frozenset(
        {RuntimeLifecycleState.STOPPED, RuntimeLifecycleState.FAILED}
    ),
    RuntimeLifecycleState.FAILED: frozenset(
        {RuntimeLifecycleState.STARTING, RuntimeLifecycleState.STOPPING}
    ),
}


class ChannelRuntimeManager:
    def __init__(
        self,
        runtime_id: str,
        browser: BrowserManager,
        heartbeat: HeartbeatManager,
        recovery: RuntimeRecoveryCoordinator,
        store: RuntimeReliabilityStore,
        *,
        channel_start: Callable[[], object] | None = None,
        channel_stop: Callable[[], object] | None = None,
        on_channel_state: Callable[[str], object] | None = None,
        clock: Callable = utc_now,
    ) -> None:
        if not runtime_id.strip():
            raise ValueError("runtime_id is required")
        self.runtime_id = runtime_id.strip()
        self._browser = browser
        self._heartbeat = heartbeat
        self._recovery = recovery
        self._store = store
        self._channel_start = channel_start
        self._channel_stop = channel_stop
        self._on_channel_state = on_channel_state
        self._clock = clock
        self._lock = RLock()

    def status(self) -> RuntimeLifecycleSnapshot:
        status = self._store.load_runtime(self.runtime_id)
        if status is None:
            return self._store.ensure_runtime(self.runtime_id, self._clock())
        return status

    def start(self) -> RuntimeLifecycleSnapshot:
        with self._lock:
            current = self.status()
            if current.state in {
                RuntimeLifecycleState.READY,
                RuntimeLifecycleState.RUNNING,
            }:
                return current
            current = self._transition(
                current,
                RuntimeLifecycleState.STARTING,
                "RUNTIME_START_REQUESTED",
                generation=current.generation + 1,
            )
            try:
                if self._channel_start is not None:
                    self._channel_start()
                if self._on_channel_state is not None:
                    self._on_channel_state("CONNECTED")
            except Exception:
                if self._on_channel_state is not None:
                    self._on_channel_state("FAILED")
                return self._transition(
                    current,
                    RuntimeLifecycleState.FAILED,
                    "CHANNEL_START_FAILED",
                )
            try:
                self._browser.start()
            except Exception:
                if self._channel_stop is not None:
                    try:
                        self._channel_stop()
                    except Exception:
                        pass
                return self._transition(
                    current,
                    RuntimeLifecycleState.FAILED,
                    "BROWSER_START_FAILED",
                )
            report = self._heartbeat.run_once()
            if report.overall is not ComponentHealth.HEALTHY:
                return self._transition(
                    current,
                    RuntimeLifecycleState.DEGRADED,
                    "STARTUP_HEALTH_DEGRADED",
                )
            current = self._transition(
                current,
                RuntimeLifecycleState.READY,
                "RUNTIME_COMPONENTS_READY",
            )
            return self._transition(
                current,
                RuntimeLifecycleState.RUNNING,
                "RUNTIME_RUNNING",
            )

    def stop(self) -> RuntimeLifecycleSnapshot:
        with self._lock:
            current = self.status()
            if current.state is RuntimeLifecycleState.STOPPED:
                return current
            if current.state is RuntimeLifecycleState.STOPPING:
                return current
            current = self._transition(
                current,
                RuntimeLifecycleState.STOPPING,
                "RUNTIME_STOP_REQUESTED",
            )
            stop_failed = False
            try:
                self._browser.stop()
            except Exception:
                stop_failed = True
            try:
                if self._channel_stop is not None:
                    self._channel_stop()
                if self._on_channel_state is not None:
                    self._on_channel_state("DISCONNECTED")
            except Exception:
                if self._on_channel_state is not None:
                    self._on_channel_state("FAILED")
                stop_failed = True
            if stop_failed:
                return self._transition(
                    current,
                    RuntimeLifecycleState.FAILED,
                    "RUNTIME_RESOURCE_STOP_FAILED",
                )
            return self._transition(
                current,
                RuntimeLifecycleState.STOPPED,
                "RUNTIME_STOPPED",
            )

    def heartbeat(self) -> HeartbeatReport:
        with self._lock:
            report = self._heartbeat.run_once()
            current = self.status()
            if (
                current.state
                in {RuntimeLifecycleState.RUNNING, RuntimeLifecycleState.READY}
                and report.overall is not ComponentHealth.HEALTHY
            ):
                self._transition(
                    current,
                    RuntimeLifecycleState.DEGRADED,
                    "HEARTBEAT_COMPONENT_DEGRADED",
                )
            return report

    def recover(
        self, component: RuntimeComponent | None = None
    ) -> RecoveryResult:
        with self._lock:
            current = self.status()
            if current.state is not RuntimeLifecycleState.DEGRADED:
                raise InvalidRuntimeTransition(
                    "runtime recovery requires DEGRADED state"
                )
            report = self._store.latest_heartbeat(self.runtime_id)
            if report is None:
                report = self._heartbeat.run_once()
            target = component or self._first_unhealthy_component(report)
            result = self._recovery.recover(target)
            if result.state is RecoveryState.MANUAL_INTERVENTION:
                self._transition(
                    current,
                    RuntimeLifecycleState.FAILED,
                    "MANUAL_INTERVENTION_REQUIRED",
                )
                return result
            verified = self._heartbeat.run_once()
            if verified.overall is ComponentHealth.HEALTHY:
                self._transition(
                    current,
                    RuntimeLifecycleState.RUNNING,
                    "RUNTIME_RECOVERED",
                )
            return result

    def dashboard(self, *, refresh: bool = False) -> RuntimeDashboardStatus:
        report = (
            self.heartbeat()
            if refresh
            else self._store.latest_heartbeat(self.runtime_id)
        )
        if report is None:
            report = self.heartbeat()
        execution = self._store.execution_status()
        approval = self._store.approval_status()
        health = report.overall
        if (
            execution.terminal_without_receipt > 0
            or execution.unapproved_active > 0
        ):
            health = ComponentHealth.UNHEALTHY
        return RuntimeDashboardStatus(
            runtime=self.status(),
            channel=report.for_component(RuntimeComponent.CHANNEL),
            browser=report.for_component(RuntimeComponent.BROWSER),
            gateway=report.for_component(RuntimeComponent.GATEWAY),
            storage=report.for_component(RuntimeComponent.STORAGE),
            execution=execution,
            approval=approval,
            recovery=self._store.latest_recovery_event(self.runtime_id),
            health=health,
            checked_at=report.checked_at,
        )

    @staticmethod
    def _first_unhealthy_component(report: HeartbeatReport) -> RuntimeComponent:
        for item in report.components:
            if item.health is not ComponentHealth.HEALTHY:
                return item.component
        raise InvalidRuntimeTransition("no unhealthy component requires recovery")

    def _transition(
        self,
        current: RuntimeLifecycleSnapshot,
        target: RuntimeLifecycleState,
        reason_code: str,
        *,
        generation: int | None = None,
    ) -> RuntimeLifecycleSnapshot:
        if target not in _ALLOWED_TRANSITIONS[current.state]:
            raise InvalidRuntimeTransition(
                f"invalid runtime transition: {current.state.value} -> {target.value}"
            )
        return self._store.transition(
            current,
            target,
            reason_code,
            self._clock(),
            generation=generation,
        )


__all__ = ["ChannelRuntimeManager", "InvalidRuntimeTransition"]
