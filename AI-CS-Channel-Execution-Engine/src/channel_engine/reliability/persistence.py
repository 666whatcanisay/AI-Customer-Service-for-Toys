from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import func, select

from channel_engine.models import ApprovalState, DecisionState, ExecutionState
from channel_engine.models.entities import new_id
from channel_engine.storage import SqlAlchemyUnitOfWork
from channel_engine.storage.orm import (
    ApprovalRow,
    DecisionRow,
    ExecutionRow,
    ReceiptRow,
    RuntimeHeartbeatRow,
    RuntimeLifecycleEventRow,
    RuntimeRecoveryEventRow,
    RuntimeReliabilityStateRow,
)

from .models import (
    ApprovalRuntimeStatus,
    ComponentHealth,
    ComponentHeartbeat,
    ExecutionRuntimeStatus,
    HeartbeatReport,
    LifecycleEvent,
    RecoveryEvent,
    RecoveryState,
    RUNTIME_RELIABILITY_VERSION,
    RuntimeComponent,
    RuntimeLifecycleSnapshot,
    RuntimeLifecycleState,
)


class ConcurrentRuntimeTransition(RuntimeError):
    pass


class RuntimeReliabilityStore:
    def __init__(
        self, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    ) -> None:
        self._uow_factory = uow_factory

    def ensure_runtime(
        self, runtime_id: str, now: datetime
    ) -> RuntimeLifecycleSnapshot:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(RuntimeReliabilityStateRow, runtime_id)
            if row is None:
                row = RuntimeReliabilityStateRow(
                    runtime_id=runtime_id,
                    reliability_version=RUNTIME_RELIABILITY_VERSION,
                    state=RuntimeLifecycleState.STOPPED.value,
                    generation=0,
                    revision=0,
                    reason_code="RUNTIME_INITIALIZED",
                    started_at=None,
                    stopped_at=now,
                    updated_at=now,
                )
                uow.session.add(row)
                uow.session.add(
                    RuntimeLifecycleEventRow(
                        event_id=new_id("runtime-event"),
                        runtime_id=runtime_id,
                        reliability_version=RUNTIME_RELIABILITY_VERSION,
                        from_state=None,
                        to_state=RuntimeLifecycleState.STOPPED.value,
                        generation=0,
                        reason_code="RUNTIME_INITIALIZED",
                        occurred_at=now,
                    )
                )
                uow.session.flush()
            self._assert_version(row.reliability_version)
            return self._snapshot(row)

    def load_runtime(self, runtime_id: str) -> RuntimeLifecycleSnapshot | None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(RuntimeReliabilityStateRow, runtime_id)
            if row is None:
                return None
            self._assert_version(row.reliability_version)
            return self._snapshot(row)

    def transition(
        self,
        current: RuntimeLifecycleSnapshot,
        target: RuntimeLifecycleState,
        reason_code: str,
        now: datetime,
        *,
        generation: int | None = None,
    ) -> RuntimeLifecycleSnapshot:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(RuntimeReliabilityStateRow, current.runtime_id)
            if row is None or row.revision != current.revision:
                raise ConcurrentRuntimeTransition(
                    "runtime lifecycle revision changed; reload before transitioning"
                )
            self._assert_version(row.reliability_version)
            next_generation = current.generation if generation is None else generation
            row.state = target.value
            row.generation = next_generation
            row.revision += 1
            row.reason_code = reason_code
            row.updated_at = now
            if target is RuntimeLifecycleState.STARTING:
                row.started_at = now
                row.stopped_at = None
            elif target is RuntimeLifecycleState.STOPPED:
                row.stopped_at = now
            uow.session.add(
                RuntimeLifecycleEventRow(
                    event_id=new_id("runtime-event"),
                    runtime_id=current.runtime_id,
                    reliability_version=RUNTIME_RELIABILITY_VERSION,
                    from_state=current.state.value,
                    to_state=target.value,
                    generation=next_generation,
                    reason_code=reason_code,
                    occurred_at=now,
                )
            )
            uow.session.flush()
            return self._snapshot(row)

    def list_lifecycle_events(self, runtime_id: str) -> tuple[LifecycleEvent, ...]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            rows = uow.session.scalars(
                select(RuntimeLifecycleEventRow)
                .where(RuntimeLifecycleEventRow.runtime_id == runtime_id)
                .order_by(
                    RuntimeLifecycleEventRow.occurred_at,
                    RuntimeLifecycleEventRow.event_id,
                )
            ).all()
            return tuple(
                LifecycleEvent(
                    event_id=row.event_id,
                    runtime_id=row.runtime_id,
                    from_state=(
                        RuntimeLifecycleState(row.from_state)
                        if row.from_state is not None
                        else None
                    ),
                    to_state=RuntimeLifecycleState(row.to_state),
                    generation=row.generation,
                    reason_code=row.reason_code,
                    occurred_at=row.occurred_at,
                )
                for row in rows
            )

    def append_heartbeat(self, report: HeartbeatReport) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            for item in report.components:
                uow.session.add(
                    RuntimeHeartbeatRow(
                        heartbeat_id=item.heartbeat_id,
                        runtime_id=item.runtime_id,
                        reliability_version=RUNTIME_RELIABILITY_VERSION,
                        cycle_id=item.cycle_id,
                        component=item.component.value,
                        health=item.health.value,
                        available=int(item.available),
                        process_running=(
                            int(item.process_running)
                            if item.process_running is not None
                            else None
                        ),
                        page_available=(
                            int(item.page_available)
                            if item.page_available is not None
                            else None
                        ),
                        reason_code=item.reason_code,
                        latency_ms=item.latency_ms,
                        checked_at=item.checked_at,
                    )
                )

    def latest_heartbeat(self, runtime_id: str) -> HeartbeatReport | None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            latest = uow.session.scalar(
                select(RuntimeHeartbeatRow)
                .where(RuntimeHeartbeatRow.runtime_id == runtime_id)
                .order_by(
                    RuntimeHeartbeatRow.checked_at.desc(),
                    RuntimeHeartbeatRow.heartbeat_id.desc(),
                )
                .limit(1)
            )
            if latest is None:
                return None
            rows = uow.session.scalars(
                select(RuntimeHeartbeatRow)
                .where(
                    RuntimeHeartbeatRow.runtime_id == runtime_id,
                    RuntimeHeartbeatRow.cycle_id == latest.cycle_id,
                )
                .order_by(RuntimeHeartbeatRow.component)
            ).all()
            components = tuple(self._heartbeat(row) for row in rows)
            overall = self._overall(item.health for item in components)
            return HeartbeatReport(
                runtime_id=runtime_id,
                cycle_id=latest.cycle_id,
                overall=overall,
                components=components,
                checked_at=max(item.checked_at for item in components),
            )

    def append_recovery_event(self, event: RecoveryEvent) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            uow.session.add(
                RuntimeRecoveryEventRow(
                    recovery_event_id=event.recovery_event_id,
                    recovery_id=event.recovery_id,
                    runtime_id=event.runtime_id,
                    reliability_version=RUNTIME_RELIABILITY_VERSION,
                    component=event.component.value,
                    attempt=event.attempt,
                    state=event.state.value,
                    reason_code=event.reason_code,
                    occurred_at=event.occurred_at,
                )
            )

    def list_recovery_events(self, runtime_id: str) -> tuple[RecoveryEvent, ...]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            rows = uow.session.scalars(
                select(RuntimeRecoveryEventRow)
                .where(RuntimeRecoveryEventRow.runtime_id == runtime_id)
                .order_by(
                    RuntimeRecoveryEventRow.occurred_at,
                    RuntimeRecoveryEventRow.recovery_event_id,
                )
            ).all()
            return tuple(self._recovery(row) for row in rows)

    def latest_recovery_event(self, runtime_id: str) -> RecoveryEvent | None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.scalar(
                select(RuntimeRecoveryEventRow)
                .where(RuntimeRecoveryEventRow.runtime_id == runtime_id)
                .order_by(
                    RuntimeRecoveryEventRow.occurred_at.desc(),
                    RuntimeRecoveryEventRow.recovery_event_id.desc(),
                )
                .limit(1)
            )
            return self._recovery(row) if row is not None else None

    def execution_status(self) -> ExecutionRuntimeStatus:
        with self._uow_factory() as uow:
            assert uow.session is not None
            execution_counts = dict(
                uow.session.execute(
                    select(ExecutionRow.state, func.count())
                    .group_by(ExecutionRow.state)
                ).all()
            )
            terminal_without_receipt = uow.session.scalar(
                select(func.count())
                .select_from(ExecutionRow)
                .outerjoin(
                    ReceiptRow,
                    ReceiptRow.execution_id == ExecutionRow.execution_id,
                )
                .where(
                    ExecutionRow.state.in_(
                        [
                            ExecutionState.SUCCESS.value,
                            ExecutionState.FAILED.value,
                            ExecutionState.UNKNOWN.value,
                        ]
                    ),
                    ReceiptRow.receipt_id.is_(None),
                )
            ) or 0
            unapproved_active = uow.session.scalar(
                select(func.count())
                .select_from(ExecutionRow)
                .join(
                    ApprovalRow,
                    ApprovalRow.approval_id == ExecutionRow.approval_id,
                )
                .join(
                    DecisionRow,
                    DecisionRow.decision_id == ExecutionRow.decision_id,
                )
                .where(
                    ExecutionRow.state.in_(
                        [ExecutionState.PENDING.value, ExecutionState.RUNNING.value]
                    ),
                    (
                        (ApprovalRow.state != ApprovalState.APPROVED.value)
                        | (DecisionRow.state != DecisionState.APPROVED.value)
                    ),
                )
            ) or 0
        value = lambda state: int(execution_counts.get(state.value, 0))
        return ExecutionRuntimeStatus(
            total=sum(int(count) for count in execution_counts.values()),
            pending=value(ExecutionState.PENDING),
            running=value(ExecutionState.RUNNING),
            success=value(ExecutionState.SUCCESS),
            failed=value(ExecutionState.FAILED),
            unknown=value(ExecutionState.UNKNOWN),
            terminal_without_receipt=int(terminal_without_receipt),
            unapproved_active=int(unapproved_active),
        )

    def approval_status(self) -> ApprovalRuntimeStatus:
        with self._uow_factory() as uow:
            assert uow.session is not None
            approval_counts = dict(
                uow.session.execute(
                    select(ApprovalRow.state, func.count()).group_by(ApprovalRow.state)
                ).all()
            )
            waiting = uow.session.scalar(
                select(func.count())
                .select_from(DecisionRow)
                .where(DecisionRow.state == DecisionState.WAITING_APPROVAL.value)
            ) or 0
        return ApprovalRuntimeStatus(
            waiting=int(waiting),
            approved=int(approval_counts.get(ApprovalState.APPROVED.value, 0)),
            rejected=int(approval_counts.get(ApprovalState.REJECTED.value, 0)),
        )

    @staticmethod
    def _assert_version(version: str) -> None:
        if version != RUNTIME_RELIABILITY_VERSION:
            raise RuntimeError(
                f"unsupported runtime reliability storage version: {version}"
            )

    @staticmethod
    def _snapshot(row: RuntimeReliabilityStateRow) -> RuntimeLifecycleSnapshot:
        return RuntimeLifecycleSnapshot(
            runtime_id=row.runtime_id,
            state=RuntimeLifecycleState(row.state),
            generation=row.generation,
            revision=row.revision,
            reason_code=row.reason_code,
            started_at=row.started_at,
            stopped_at=row.stopped_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _heartbeat(row: RuntimeHeartbeatRow) -> ComponentHeartbeat:
        return ComponentHeartbeat(
            heartbeat_id=row.heartbeat_id,
            runtime_id=row.runtime_id,
            cycle_id=row.cycle_id,
            component=RuntimeComponent(row.component),
            health=ComponentHealth(row.health),
            available=bool(row.available),
            process_running=(
                bool(row.process_running)
                if row.process_running is not None
                else None
            ),
            page_available=(
                bool(row.page_available)
                if row.page_available is not None
                else None
            ),
            reason_code=row.reason_code,
            latency_ms=row.latency_ms,
            checked_at=row.checked_at,
        )

    @staticmethod
    def _recovery(row: RuntimeRecoveryEventRow) -> RecoveryEvent:
        return RecoveryEvent(
            recovery_event_id=row.recovery_event_id,
            recovery_id=row.recovery_id,
            runtime_id=row.runtime_id,
            component=RuntimeComponent(row.component),
            attempt=row.attempt,
            state=RecoveryState(row.state),
            reason_code=row.reason_code,
            occurred_at=row.occurred_at,
        )

    @staticmethod
    def _overall(healths) -> ComponentHealth:
        values = tuple(healths)
        if any(value is ComponentHealth.UNHEALTHY for value in values):
            return ComponentHealth.UNHEALTHY
        if any(value is ComponentHealth.DEGRADED for value in values):
            return ComponentHealth.DEGRADED
        return ComponentHealth.HEALTHY


__all__ = [
    "ConcurrentRuntimeTransition",
    "RuntimeReliabilityStore",
]
