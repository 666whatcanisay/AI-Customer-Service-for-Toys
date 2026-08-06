from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from channel_engine.models import ExecutionState, OutboxState
from channel_engine.storage.orm import (
    ControlPlaneAuditEventRow,
    ControlPlaneConfigSnapshotRow,
    ControlPlaneStateRow,
    ExecutionRow,
    OutboxRow,
    ReceiptRow,
)

from .models import (
    CONTROL_PLANE_VERSION,
    ConfigSnapshot,
    ControlPlaneAuditEvent,
    KillSwitchState,
    OperationalMetrics,
)


CONTROL_PLANE_SINGLETON_ID = "channel-engine-control-plane"


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ControlPlaneRecordNotFound(LookupError):
    pass


class ControlPlaneConcurrentModification(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ControlPlaneStateRecord:
    revision: int
    kill_switch_state: KillSwitchState
    active_config_snapshot_id: str | None
    kill_switch_updated_at: datetime
    kill_switch_updated_by: str
    kill_switch_reason: str
    updated_at: datetime
    updated_by: str
    reason: str


class ControlPlaneRepository:
    """Persistence boundary for append-only audit and immutable snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_state(self, now: datetime) -> ControlPlaneStateRecord:
        row = self.session.get(ControlPlaneStateRow, CONTROL_PLANE_SINGLETON_ID)
        if row is None:
            row = ControlPlaneStateRow(
                singleton_id=CONTROL_PLANE_SINGLETON_ID,
                control_plane_version=CONTROL_PLANE_VERSION,
                revision=0,
                kill_switch_state=KillSwitchState.DISABLED.value,
                active_config_snapshot_id=None,
                kill_switch_updated_at=_as_aware_utc(now),
                kill_switch_updated_by="system-control-plane",
                kill_switch_reason="CONTROL_PLANE_INITIALIZED",
                updated_at=_as_aware_utc(now),
                updated_by="system-control-plane",
                reason="CONTROL_PLANE_INITIALIZED",
            )
            self.session.add(row)
            self.session.flush()
        return self._state_from_row(row)

    def get_state(self) -> ControlPlaneStateRecord:
        row = self.session.get(ControlPlaneStateRow, CONTROL_PLANE_SINGLETON_ID)
        if row is None:
            raise ControlPlaneRecordNotFound("control-plane state is not initialized")
        return self._state_from_row(row)

    def get_state_for_execution_gate(
        self,
        now: datetime,
    ) -> ControlPlaneStateRecord:
        self.get_or_create_state(now)
        row = self.session.scalar(
            select(ControlPlaneStateRow)
            .where(
                ControlPlaneStateRow.singleton_id == CONTROL_PLANE_SINGLETON_ID
            )
            .with_for_update()
        )
        assert row is not None
        return self._state_from_row(row)

    def update_kill_switch(
        self,
        state: ControlPlaneStateRecord,
        *,
        target: KillSwitchState,
        updated_at: datetime,
        updated_by: str,
        reason: str,
    ) -> ControlPlaneStateRecord:
        result = self.session.execute(
            update(ControlPlaneStateRow)
            .where(
                ControlPlaneStateRow.singleton_id == CONTROL_PLANE_SINGLETON_ID,
                ControlPlaneStateRow.revision == state.revision,
            )
            .values(
                revision=state.revision + 1,
                kill_switch_state=target.value,
                kill_switch_updated_at=_as_aware_utc(updated_at),
                kill_switch_updated_by=updated_by,
                kill_switch_reason=reason,
                updated_at=_as_aware_utc(updated_at),
                updated_by=updated_by,
                reason=reason,
            )
        )
        if result.rowcount != 1:
            raise ControlPlaneConcurrentModification(
                "kill-switch state changed concurrently"
            )
        self.session.expire_all()
        return self.get_state()

    def set_active_config(
        self,
        state: ControlPlaneStateRecord,
        *,
        snapshot_id: str,
        updated_at: datetime,
        updated_by: str,
        reason: str,
    ) -> ControlPlaneStateRecord:
        if self.session.get(ControlPlaneConfigSnapshotRow, snapshot_id) is None:
            raise ControlPlaneRecordNotFound(
                f"config snapshot not found: {snapshot_id}"
            )
        result = self.session.execute(
            update(ControlPlaneStateRow)
            .where(
                ControlPlaneStateRow.singleton_id == CONTROL_PLANE_SINGLETON_ID,
                ControlPlaneStateRow.revision == state.revision,
            )
            .values(
                revision=state.revision + 1,
                active_config_snapshot_id=snapshot_id,
                updated_at=_as_aware_utc(updated_at),
                updated_by=updated_by,
                reason=reason,
            )
        )
        if result.rowcount != 1:
            raise ControlPlaneConcurrentModification(
                "active config changed concurrently"
            )
        self.session.expire_all()
        return self.get_state()

    def append_config_snapshot(self, snapshot: ConfigSnapshot) -> None:
        snapshot = ConfigSnapshot.model_validate_json(snapshot.model_dump_json())
        if (
            self.session.get(ControlPlaneConfigSnapshotRow, snapshot.snapshot_id)
            is not None
        ):
            raise ValueError(f"config snapshot is immutable: {snapshot.snapshot_id}")
        self.session.add(
            ControlPlaneConfigSnapshotRow(
                snapshot_id=snapshot.snapshot_id,
                control_plane_version=snapshot.control_plane_version,
                adapter_config_version=snapshot.adapter_config_version,
                policy_version=snapshot.policy_version,
                gateway_version=snapshot.gateway_version,
                created_at=snapshot.created_at,
                created_by=snapshot.created_by,
                reason=snapshot.reason,
            )
        )

    def get_config_snapshot(self, snapshot_id: str) -> ConfigSnapshot:
        row = self.session.get(ControlPlaneConfigSnapshotRow, snapshot_id)
        if row is None:
            raise ControlPlaneRecordNotFound(
                f"config snapshot not found: {snapshot_id}"
            )
        return self._config_from_row(row)

    def get_active_config(
        self,
        state: ControlPlaneStateRecord,
    ) -> ConfigSnapshot | None:
        if state.active_config_snapshot_id is None:
            return None
        return self.get_config_snapshot(state.active_config_snapshot_id)

    def list_config_snapshots(self, limit: int = 100) -> list[ConfigSnapshot]:
        rows = self.session.scalars(
            select(ControlPlaneConfigSnapshotRow)
            .order_by(
                ControlPlaneConfigSnapshotRow.created_at,
                ControlPlaneConfigSnapshotRow.snapshot_id,
            )
            .limit(limit)
        ).all()
        return [self._config_from_row(row) for row in rows]

    def append_audit_event(self, event: ControlPlaneAuditEvent) -> None:
        event = ControlPlaneAuditEvent.model_validate_json(event.model_dump_json())
        if self.session.get(ControlPlaneAuditEventRow, event.audit_event_id) is not None:
            raise ValueError(f"control-plane audit event exists: {event.audit_event_id}")
        self.session.add(
            ControlPlaneAuditEventRow(
                audit_event_id=event.audit_event_id,
                control_plane_version=event.control_plane_version,
                operator=event.operator,
                action=event.action.value,
                timestamp=event.timestamp,
                reason=event.reason,
                subject_id=event.subject_id,
                before=event.before.model_dump(mode="json"),
                after=event.after.model_dump(mode="json"),
            )
        )

    def list_audit_events(self, limit: int = 100) -> list[ControlPlaneAuditEvent]:
        rows = self.session.scalars(
            select(ControlPlaneAuditEventRow)
            .order_by(
                ControlPlaneAuditEventRow.timestamp,
                ControlPlaneAuditEventRow.audit_event_id,
            )
            .limit(limit)
        ).all()
        events: list[ControlPlaneAuditEvent] = []
        for row in rows:
            payload = {
                "control_plane_version": row.control_plane_version,
                "audit_event_id": row.audit_event_id,
                "operator": row.operator,
                "action": row.action,
                "timestamp": _as_aware_utc(row.timestamp).isoformat(),
                "reason": row.reason,
                "subject_id": row.subject_id,
                "before": row.before,
                "after": row.after,
            }
            events.append(
                ControlPlaneAuditEvent.model_validate_json(json.dumps(payload))
            )
        return events

    def operational_metrics(self) -> OperationalMetrics:
        execution_counts = {
            state: count
            for state, count in self.session.execute(
                select(ExecutionRow.state, func.count()).group_by(ExecutionRow.state)
            ).all()
        }
        outbox_counts = {
            state: count
            for state, count in self.session.execute(
                select(OutboxRow.status, func.count()).group_by(OutboxRow.status)
            ).all()
        }
        receipts_total = self.session.scalar(select(func.count()).select_from(ReceiptRow))
        audit_total = self.session.scalar(
            select(func.count()).select_from(ControlPlaneAuditEventRow)
        )
        config_total = self.session.scalar(
            select(func.count()).select_from(ControlPlaneConfigSnapshotRow)
        )
        latency_count, latency_avg_ms, latency_max_ms = self._execution_latency()
        return OperationalMetrics(
            execution_count=sum(execution_counts.values()),
            execution_pending=execution_counts.get(ExecutionState.PENDING.value, 0),
            execution_running=execution_counts.get(ExecutionState.RUNNING.value, 0),
            execution_success=execution_counts.get(ExecutionState.SUCCESS.value, 0),
            execution_failed=execution_counts.get(ExecutionState.FAILED.value, 0),
            execution_unknown=execution_counts.get(ExecutionState.UNKNOWN.value, 0),
            execution_latency_sample_count=latency_count,
            execution_latency_avg_ms=latency_avg_ms,
            execution_latency_max_ms=latency_max_ms,
            queue_depth=execution_counts.get(ExecutionState.PENDING.value, 0),
            adapter_healthy=0,
            adapter_degraded=0,
            adapter_disconnected=0,
            receipts_total=receipts_total or 0,
            outbox_pending=outbox_counts.get(OutboxState.PENDING.value, 0),
            outbox_processing=outbox_counts.get(OutboxState.PROCESSING.value, 0),
            outbox_published=outbox_counts.get(OutboxState.PUBLISHED.value, 0),
            outbox_failed=outbox_counts.get(OutboxState.FAILED.value, 0),
            audit_events_total=audit_total or 0,
            config_snapshots_total=config_total or 0,
        )

    def _execution_latency(self) -> tuple[int, float, float]:
        dialect = self.session.get_bind().dialect.name
        if dialect == "sqlite":
            latency_ms = (
                func.julianday(ExecutionRow.completed_at)
                - func.julianday(ExecutionRow.started_at)
            ) * 86_400_000.0
        elif dialect == "postgresql":
            latency_ms = (
                func.extract(
                    "epoch", ExecutionRow.completed_at - ExecutionRow.started_at
                )
                * 1_000.0
            )
        else:
            rows = self.session.execute(
                select(ExecutionRow.started_at, ExecutionRow.completed_at).where(
                    ExecutionRow.started_at.is_not(None),
                    ExecutionRow.completed_at.is_not(None),
                )
            ).all()
            values = [
                max((completed - started).total_seconds() * 1_000.0, 0.0)
                for started, completed in rows
            ]
            if not values:
                return 0, 0.0, 0.0
            return len(values), sum(values) / len(values), max(values)

        count, average, maximum = self.session.execute(
            select(func.count(), func.avg(latency_ms), func.max(latency_ms)).where(
                ExecutionRow.started_at.is_not(None),
                ExecutionRow.completed_at.is_not(None),
            )
        ).one()
        return int(count or 0), max(float(average or 0), 0.0), max(
            float(maximum or 0), 0.0
        )

    @staticmethod
    def _state_from_row(row: ControlPlaneStateRow) -> ControlPlaneStateRecord:
        if row.control_plane_version != CONTROL_PLANE_VERSION:
            raise ValueError("unsupported persisted control-plane version")
        return ControlPlaneStateRecord(
            revision=row.revision,
            kill_switch_state=KillSwitchState(row.kill_switch_state),
            active_config_snapshot_id=row.active_config_snapshot_id,
            kill_switch_updated_at=_as_aware_utc(row.kill_switch_updated_at),
            kill_switch_updated_by=row.kill_switch_updated_by,
            kill_switch_reason=row.kill_switch_reason,
            updated_at=_as_aware_utc(row.updated_at),
            updated_by=row.updated_by,
            reason=row.reason,
        )

    @staticmethod
    def _config_from_row(row: ControlPlaneConfigSnapshotRow) -> ConfigSnapshot:
        return ConfigSnapshot(
            control_plane_version=row.control_plane_version,
            snapshot_id=row.snapshot_id,
            adapter_config_version=row.adapter_config_version,
            policy_version=row.policy_version,
            gateway_version=row.gateway_version,
            created_at=_as_aware_utc(row.created_at),
            created_by=row.created_by,
            reason=row.reason,
        )


__all__ = [
    "CONTROL_PLANE_SINGLETON_ID",
    "ControlPlaneConcurrentModification",
    "ControlPlaneRecordNotFound",
    "ControlPlaneRepository",
    "ControlPlaneStateRecord",
]
