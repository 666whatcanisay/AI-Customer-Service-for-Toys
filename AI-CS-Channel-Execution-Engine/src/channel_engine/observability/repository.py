from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from channel_engine.models import ApprovalState, DecisionState, ExecutionState
from channel_engine.storage.orm import (
    ApprovalRow,
    DecisionRow,
    ExecutionRow,
    ObservabilityEventRow,
    ReceiptRow,
)

from .models import (
    ApprovalMonitorItem,
    ApprovalMonitorState,
    ExecutionLedgerItem,
    RecoveryRecord,
    RecoveryRecordState,
    StructuredEvent,
    StructuredEventPage,
    StructuredEventStatus,
    StructuredEventType,
)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ObservabilityConflict(ValueError):
    pass


class ObservabilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: StructuredEvent) -> StructuredEvent:
        existing = self.session.get(ObservabilityEventRow, event.event_id)
        if existing is not None:
            replay = self._event_from_row(existing)
            if replay == event:
                return replay
            raise ObservabilityConflict(
                f"observability event is immutable: {event.event_id}"
            )
        self.session.add(
            ObservabilityEventRow(
                event_id=event.event_id,
                observability_version=event.observability_version,
                event_type=event.event_type.value,
                trace_id=event.trace_id,
                message_id=event.message_id,
                conversation_id=event.conversation_id,
                request_id=event.request_id,
                decision_id=event.decision_id,
                approval_id=event.approval_id,
                execution_id=event.execution_id,
                receipt_id=event.receipt_id,
                store_id=event.store_id,
                timestamp=event.timestamp,
                status=event.status.value,
                metadata_json=event.metadata,
            )
        )
        return event

    def events(
        self,
        *,
        trace_id: str | None = None,
        event_type: StructuredEventType | None = None,
        status: StructuredEventStatus | None = None,
        store_id: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
        newest_first: bool = True,
    ) -> StructuredEventPage:
        conditions = []
        if trace_id is not None:
            conditions.append(ObservabilityEventRow.trace_id == trace_id)
        if event_type is not None:
            conditions.append(ObservabilityEventRow.event_type == event_type.value)
        if status is not None:
            conditions.append(ObservabilityEventRow.status == status.value)
        if store_id is not None:
            conditions.append(ObservabilityEventRow.store_id == store_id)
        if since is not None:
            conditions.append(ObservabilityEventRow.timestamp >= since)

        total = self.session.scalar(
            select(func.count(ObservabilityEventRow.event_id)).where(*conditions)
        ) or 0
        order = (
            ObservabilityEventRow.timestamp.desc()
            if newest_first
            else ObservabilityEventRow.timestamp.asc()
        )
        id_order = (
            ObservabilityEventRow.event_id.desc()
            if newest_first
            else ObservabilityEventRow.event_id.asc()
        )
        rows = self.session.scalars(
            select(ObservabilityEventRow)
            .where(*conditions)
            .order_by(order, id_order)
            .limit(limit)
        ).all()
        return StructuredEventPage(
            items=tuple(self._event_from_row(row) for row in rows),
            count=int(total),
            limit=limit,
            newest_first=newest_first,
        )

    def resolve_trace_id(self, identifier: str) -> str | None:
        return self.session.scalar(
            select(ObservabilityEventRow.trace_id)
            .where(
                or_(
                    ObservabilityEventRow.trace_id == identifier,
                    ObservabilityEventRow.message_id == identifier,
                    ObservabilityEventRow.conversation_id == identifier,
                    ObservabilityEventRow.request_id == identifier,
                    ObservabilityEventRow.decision_id == identifier,
                    ObservabilityEventRow.approval_id == identifier,
                    ObservabilityEventRow.execution_id == identifier,
                    ObservabilityEventRow.receipt_id == identifier,
                )
            )
            .order_by(ObservabilityEventRow.timestamp)
            .limit(1)
        )

    def event_count_and_latest(self) -> tuple[int, datetime | None]:
        count, latest = self.session.execute(
            select(
                func.count(ObservabilityEventRow.event_id),
                func.max(ObservabilityEventRow.timestamp),
            )
        ).one()
        return int(count or 0), as_utc(latest)

    def approvals(
        self, *, waiting_only: bool = False, limit: int = 100
    ) -> tuple[ApprovalMonitorItem, ...]:
        statement = (
            select(DecisionRow, ApprovalRow)
            .outerjoin(ApprovalRow, ApprovalRow.decision_id == DecisionRow.decision_id)
            .order_by(DecisionRow.created_at.desc(), DecisionRow.decision_id.desc())
            .limit(limit)
        )
        if waiting_only:
            statement = statement.where(
                DecisionRow.state == DecisionState.WAITING_APPROVAL.value
            )
        results: list[ApprovalMonitorItem] = []
        for decision, approval in self.session.execute(statement).all():
            if approval is None:
                state = ApprovalMonitorState.WAITING
            elif approval.state == ApprovalState.APPROVED.value:
                state = ApprovalMonitorState.APPROVED
            else:
                state = ApprovalMonitorState.REJECTED
            results.append(
                ApprovalMonitorItem(
                    decision_id=decision.decision_id,
                    conversation_id=decision.conversation_id,
                    message_id=decision.message_id,
                    approval_id=approval.approval_id if approval else None,
                    store_id=self._store_for_trace(decision.message_id),
                    state=state,
                    requires_approval=bool(decision.requires_approval),
                    waiting_since=as_utc(decision.created_at),
                    decided_at=as_utc(approval.decided_at) if approval else None,
                    decided_by=approval.decided_by if approval else None,
                    action=decision.action,
                )
            )
        return tuple(results)

    def executions(self, *, limit: int = 100) -> tuple[ExecutionLedgerItem, ...]:
        rows = self.session.execute(
            select(ExecutionRow, ReceiptRow, DecisionRow)
            .join(DecisionRow, DecisionRow.decision_id == ExecutionRow.decision_id)
            .outerjoin(ReceiptRow, ReceiptRow.execution_id == ExecutionRow.execution_id)
            .order_by(ExecutionRow.created_at.desc(), ExecutionRow.execution_id.desc())
            .limit(limit)
        ).all()
        results: list[ExecutionLedgerItem] = []
        for execution, receipt, decision in rows:
            state = ExecutionState(execution.state)
            if state is ExecutionState.PENDING:
                next_step = "等待 Worker 领取"
            elif state is ExecutionState.RUNNING:
                next_step = "等待 Adapter 结果并写入 Receipt"
            elif state is ExecutionState.UNKNOWN:
                next_step = "禁止自动重试；需要人工核验"
            elif state is ExecutionState.FAILED:
                next_step = "检查失败原因后人工决定"
            else:
                next_step = "已完成"
            results.append(
                ExecutionLedgerItem(
                    execution_id=execution.execution_id,
                    decision_id=execution.decision_id,
                    approval_id=execution.approval_id,
                    trace_id=self.resolve_trace_id(execution.execution_id)
                    or decision.message_id,
                    state=execution.state,
                    attempt=execution.attempt,
                    error_code=execution.error_code,
                    receipt_id=receipt.receipt_id if receipt else None,
                    receipt_outcome=receipt.outcome if receipt else None,
                    created_at=as_utc(execution.created_at),
                    started_at=as_utc(execution.started_at),
                    completed_at=as_utc(execution.completed_at),
                    recorded_at=as_utc(receipt.recorded_at) if receipt else None,
                    automatic_retry_allowed=False,
                    next_step=next_step,
                )
            )
        return tuple(results)

    def pending_approval_count(self) -> int:
        return int(
            self.session.scalar(
                select(func.count(DecisionRow.decision_id)).where(
                    DecisionRow.state == DecisionState.WAITING_APPROVAL.value
                )
            )
            or 0
        )

    def recoveries(self, *, limit: int = 100) -> tuple[RecoveryRecord, ...]:
        recovery_types = {
            StructuredEventType.RECOVERY_STARTED.value,
            StructuredEventType.RECOVERY_COMPLETED.value,
            StructuredEventType.RECOVERY_MANUAL_INTERVENTION.value,
        }
        rows = self.session.scalars(
            select(ObservabilityEventRow)
            .where(ObservabilityEventRow.event_type.in_(recovery_types))
            .order_by(
                ObservabilityEventRow.timestamp,
                ObservabilityEventRow.event_id,
            )
            .limit(5000)
        ).all()
        grouped: dict[str, list[ObservabilityEventRow]] = {}
        for row in rows:
            grouped.setdefault(row.trace_id, []).append(row)

        records: list[RecoveryRecord] = []
        for recovery_id, recovery_rows in grouped.items():
            first = recovery_rows[0]
            last = recovery_rows[-1]
            types = {row.event_type for row in recovery_rows}
            attempts = max(
                (
                    int(row.metadata_json.get("attempt", 1))
                    for row in recovery_rows
                    if isinstance(row.metadata_json.get("attempt", 1), int)
                ),
                default=1,
            )
            if (
                StructuredEventType.RECOVERY_MANUAL_INTERVENTION.value
                in types
            ):
                state = RecoveryRecordState.MANUAL_INTERVENTION
                next_step = "Operator intervention is required before recovery resumes"
            elif StructuredEventType.RECOVERY_COMPLETED.value in types:
                if last.status == StructuredEventStatus.UNKNOWN.value:
                    state = RecoveryRecordState.UNKNOWN
                    next_step = "Do not retry automatically; verify the external outcome"
                else:
                    state = RecoveryRecordState.RECOVERED
                    next_step = "Recovery completed; continue health monitoring"
            else:
                state = RecoveryRecordState.RECOVERING
                next_step = "Wait for bounded recovery to complete"
            metadata = last.metadata_json or first.metadata_json
            records.append(
                RecoveryRecord(
                    recovery_id=recovery_id,
                    component=str(metadata.get("component", "UNKNOWN")),
                    state=state,
                    attempts=attempts,
                    reason_code=str(metadata.get("reason_code", "RECOVERY_RECORDED")),
                    execution_id=next(
                        (
                            row.execution_id
                            for row in recovery_rows
                            if row.execution_id is not None
                        ),
                        None,
                    ),
                    started_at=as_utc(first.timestamp),
                    completed_at=(
                        as_utc(last.timestamp)
                        if state is not RecoveryRecordState.RECOVERING
                        else None
                    ),
                    requires_manual_action=state
                    in {
                        RecoveryRecordState.UNKNOWN,
                        RecoveryRecordState.MANUAL_INTERVENTION,
                    },
                    next_step=next_step,
                )
            )
        records.sort(key=lambda item: item.started_at, reverse=True)
        return tuple(records[:limit])

    def _store_for_trace(self, trace_id: str) -> str | None:
        return self.session.scalar(
            select(ObservabilityEventRow.store_id)
            .where(
                ObservabilityEventRow.trace_id == trace_id,
                ObservabilityEventRow.store_id.is_not(None),
            )
            .order_by(ObservabilityEventRow.timestamp)
            .limit(1)
        )

    @staticmethod
    def _event_from_row(row: ObservabilityEventRow) -> StructuredEvent:
        return StructuredEvent(
            observability_version=row.observability_version,
            event_id=row.event_id,
            event_type=StructuredEventType(row.event_type),
            trace_id=row.trace_id,
            message_id=row.message_id,
            conversation_id=row.conversation_id,
            request_id=row.request_id,
            decision_id=row.decision_id,
            approval_id=row.approval_id,
            execution_id=row.execution_id,
            receipt_id=row.receipt_id,
            store_id=row.store_id,
            timestamp=as_utc(row.timestamp),
            status=StructuredEventStatus(row.status),
            metadata=row.metadata_json,
        )


__all__ = ["ObservabilityConflict", "ObservabilityRepository", "as_utc"]
