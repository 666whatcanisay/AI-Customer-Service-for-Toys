from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import Lock

from channel_engine.channel import AdapterHealthStatus, AdapterRegistry
from channel_engine.models.entities import utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork

from .models import (
    AdapterConnectionState,
    AdapterStatus,
    ChannelEngineHealth,
    ComponentHealthState,
    EngineRuntimeState,
    EngineStatus,
    ExecutionPolicyState,
    ExecutionPolicyStatus,
    GatewayStatus,
    KillSwitchState,
    OperationalMetrics,
    OutboxRuntimeState,
    OutboxStatus,
    WorkerRuntimeState,
    WorkerStatus,
)
from .repository import ControlPlaneRepository
from .service import ControlPlaneService


class WorkerRuntimeMonitor:
    """Process-local worker liveness input for the aggregate health view."""

    def __init__(
        self,
        worker_id: str,
        *,
        clock: Callable[[], datetime] = utc_now,
        initial_state: WorkerRuntimeState = WorkerRuntimeState.STOPPED,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        self.worker_id = worker_id.strip()
        self._clock = clock
        self._lock = Lock()
        self._state = initial_state
        self._last_transition_at = clock()

    def mark_running(self) -> WorkerStatus:
        return self._transition(WorkerRuntimeState.RUNNING)

    def mark_stopped(self) -> WorkerStatus:
        return self._transition(WorkerRuntimeState.STOPPED)

    def snapshot(self) -> WorkerStatus:
        with self._lock:
            return WorkerStatus(
                worker_id=self.worker_id,
                state=self._state,
                last_transition_at=self._last_transition_at,
            )

    def _transition(self, target: WorkerRuntimeState) -> WorkerStatus:
        with self._lock:
            if self._state is not target:
                self._state = target
                self._last_transition_at = self._clock()
            return WorkerStatus(
                worker_id=self.worker_id,
                state=self._state,
                last_transition_at=self._last_transition_at,
            )


class ControlPlaneHealthAggregator:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        control_plane: ControlPlaneService,
        adapter_registry: AdapterRegistry,
        gateway_probe: Callable[[], GatewayStatus],
        worker_monitor: WorkerRuntimeMonitor,
        *,
        service_name: str,
        environment: str,
        outbox_backlog_threshold: int = 100,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if outbox_backlog_threshold < 1:
            raise ValueError("outbox backlog threshold must be positive")
        self._uow_factory = uow_factory
        self._control_plane = control_plane
        self._adapter_registry = adapter_registry
        self._gateway_probe = gateway_probe
        self._worker_monitor = worker_monitor
        self.service_name = service_name
        self.environment = environment
        self.outbox_backlog_threshold = outbox_backlog_threshold
        self._clock = clock

    def snapshot(self) -> ChannelEngineHealth:
        checked_at = self._clock()
        control = self._control_plane.status()
        with self._uow_factory() as uow:
            assert uow.session is not None
            metrics = ControlPlaneRepository(uow.session).operational_metrics()

        try:
            gateway = self._gateway_probe()
        except Exception:
            gateway = GatewayStatus(
                health=ComponentHealthState.DEGRADED,
                reachable=False,
                gateway_version=None,
                checked_at=checked_at,
            )

        adapters = tuple(
            self._adapter_status(channel, health)
            for channel, health in sorted(
                self._adapter_registry.health_check().items()
            )
        )
        metrics = OperationalMetrics.model_validate(
            {
                **metrics.model_dump(),
                "adapter_healthy": sum(
                    adapter.health is ComponentHealthState.HEALTHY
                    for adapter in adapters
                ),
                "adapter_degraded": sum(
                    adapter.connection is AdapterConnectionState.DEGRADED
                    for adapter in adapters
                ),
                "adapter_disconnected": sum(
                    adapter.connection is AdapterConnectionState.DISCONNECTED
                    for adapter in adapters
                ),
            }
        )
        worker = self._worker_monitor.snapshot()
        if metrics.outbox_failed > 0:
            outbox_state = OutboxRuntimeState.DEGRADED
        elif (
            metrics.outbox_pending + metrics.outbox_processing
            >= self.outbox_backlog_threshold
        ):
            outbox_state = OutboxRuntimeState.BACKLOG
        else:
            outbox_state = OutboxRuntimeState.HEALTHY
        outbox = OutboxStatus(
            state=outbox_state,
            pending_count=metrics.outbox_pending,
            processing_count=metrics.outbox_processing,
            failed_count=metrics.outbox_failed,
            backlog_threshold=self.outbox_backlog_threshold,
        )
        kill_switch = control.kill_switch
        blocked = kill_switch.state is KillSwitchState.ENABLED
        policy = ExecutionPolicyStatus(
            state=(
                ExecutionPolicyState.BLOCKED
                if blocked
                else ExecutionPolicyState.ENABLED
            ),
            kill_switch=kill_switch.state,
            policy_version=(
                control.active_config.policy_version
                if control.active_config is not None
                else None
            ),
            new_execution_allowed=not blocked,
            pending_claim_allowed=not blocked,
            running_execution_may_finish=True,
        )

        degraded = (
            gateway.health is ComponentHealthState.DEGRADED
            or not adapters
            or any(
                adapter.health is ComponentHealthState.DEGRADED
                for adapter in adapters
            )
            or worker.state is WorkerRuntimeState.STOPPED
            or outbox.state is not OutboxRuntimeState.HEALTHY
        )
        if blocked:
            engine_state = EngineRuntimeState.STOPPED
            reason_code = "GLOBAL_KILL_SWITCH_ENABLED"
        elif degraded:
            engine_state = EngineRuntimeState.DEGRADED
            reason_code = "CONTROL_COMPONENT_DEGRADED"
        else:
            engine_state = EngineRuntimeState.RUNNING
            reason_code = "ALL_CONTROL_COMPONENTS_HEALTHY"
        engine = EngineStatus(
            state=engine_state,
            service=self.service_name,
            environment=self.environment,
            checked_at=checked_at,
            reason_code=reason_code,
        )
        return ChannelEngineHealth(
            engine=engine,
            gateway=gateway,
            adapters=adapters,
            worker=worker,
            outbox=outbox,
            policy=policy,
            kill_switch=kill_switch,
            active_config=control.active_config,
            metrics=metrics,
            checked_at=checked_at,
        )

    @staticmethod
    def _adapter_status(channel: str, health) -> AdapterStatus:
        connection, component = {
            AdapterHealthStatus.HEALTHY: (
                AdapterConnectionState.CONNECTED,
                ComponentHealthState.HEALTHY,
            ),
            AdapterHealthStatus.DEGRADED: (
                AdapterConnectionState.DEGRADED,
                ComponentHealthState.DEGRADED,
            ),
            AdapterHealthStatus.UNHEALTHY: (
                AdapterConnectionState.DISCONNECTED,
                ComponentHealthState.DEGRADED,
            ),
        }[health.status]
        return AdapterStatus(
            adapter_name=health.adapter_name,
            channel=channel,
            connection=connection,
            health=component,
            real_platform_connected=health.real_platform_connected,
            checked_at=health.checked_at,
        )


__all__ = ["ControlPlaneHealthAggregator", "WorkerRuntimeMonitor"]
