from __future__ import annotations

from collections.abc import Callable

from channel_engine.control.models import ChannelEngineHealth
from channel_engine.models.entities import utc_now
from channel_engine.reliability.models import RuntimeDashboardStatus
from channel_engine.storage import SqlAlchemyUnitOfWork

from .models import (
    ApprovalMonitorItem,
    ApprovalReviewDetail,
    ExecutionLedgerItem,
    OpsComponentStatus,
    OpsConsoleSnapshot,
    OpsRuntimeStatus,
    RecoveryRecord,
    StructuredEventPage,
    StructuredEventStatus,
    StructuredEventType,
    TraceStopReason,
    WorkflowTrace,
)
from .repository import ObservabilityRepository


class TraceNotFound(LookupError):
    pass


class ObservabilityService:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        runtime_status: Callable[[], RuntimeDashboardStatus] | None = None,
        control_health: Callable[[], ChannelEngineHealth] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._runtime_status = runtime_status
        self._control_health = control_health

    def events(
        self,
        *,
        trace_id: str | None = None,
        event_type: StructuredEventType | None = None,
        status: StructuredEventStatus | None = None,
        store_id: str | None = None,
        since=None,
        limit: int = 100,
        newest_first: bool = True,
    ) -> StructuredEventPage:
        with self._uow_factory() as uow:
            return ObservabilityRepository(uow.require_repository().session).events(
                trace_id=trace_id,
                event_type=event_type,
                status=status,
                store_id=store_id,
                since=since,
                limit=limit,
                newest_first=newest_first,
            )

    def trace(self, identifier: str) -> WorkflowTrace:
        with self._uow_factory() as uow:
            repo = ObservabilityRepository(uow.require_repository().session)
            trace_id = repo.resolve_trace_id(identifier)
            if trace_id is None:
                raise TraceNotFound(f"trace not found: {identifier}")
            events = repo.events(
                trace_id=trace_id,
                limit=500,
                newest_first=False,
            ).items
        if not events:
            raise TraceNotFound(f"trace not found: {identifier}")
        stop_reason, current_step, next_step = self._trace_state(events)

        def first(field: str):
            return next(
                (getattr(event, field) for event in events if getattr(event, field)),
                None,
            )

        return WorkflowTrace(
            trace_id=trace_id,
            message_id=first("message_id"),
            conversation_id=first("conversation_id"),
            request_id=first("request_id"),
            decision_id=first("decision_id"),
            approval_id=first("approval_id"),
            execution_id=first("execution_id"),
            receipt_id=first("receipt_id"),
            store_id=first("store_id"),
            current_step=current_step,
            why_stopped=stop_reason,
            next_step=next_step,
            events=events,
            started_at=events[0].timestamp,
            updated_at=events[-1].timestamp,
        )

    def approvals(
        self, *, waiting_only: bool = False, limit: int = 100
    ) -> tuple[ApprovalMonitorItem, ...]:
        with self._uow_factory() as uow:
            return ObservabilityRepository(
                uow.require_repository().session
            ).approvals(waiting_only=waiting_only, limit=limit)

    def approval_review(self, decision_id: str) -> ApprovalReviewDetail:
        """Load only the business material an operator must review.

        Gateway Contract V1 does not persist citations or a risk level on the
        Decision entity.  The console reports that absence explicitly instead
        of fabricating either value and keeps the approval gate fail-closed.
        """

        with self._uow_factory() as uow:
            repo = uow.require_repository()
            decision = repo.get_decision(decision_id)
            message = repo.get_message(decision.message_id)
        return ApprovalReviewDetail(
            decision_id=decision.decision_id,
            conversation_id=decision.conversation_id,
            message_id=decision.message_id,
            customer_question=message.content,
            ai_suggestion=decision.proposed_content,
            knowledge_sources=(),
            knowledge_source_status="NOT_PROVIDED",
            risk_level="UNSPECIFIED",
            risk_basis="当前 AI 接口未提供可持久化风险等级，必须人工复核。",
            state=decision.state.value,
            action=decision.action.value,
            requires_approval=decision.requires_approval,
            gateway_version=decision.gateway_version,
            next_step=(
                "核对客户问题、AI 建议与知识来源后，人工批准进入待执行队列；"
                "如内容不适合发送，请拒绝并填写原因。"
            ),
        )

    def executions(self, *, limit: int = 100) -> tuple[ExecutionLedgerItem, ...]:
        with self._uow_factory() as uow:
            return ObservabilityRepository(
                uow.require_repository().session
            ).executions(limit=limit)

    def recoveries(self, *, limit: int = 100) -> tuple[RecoveryRecord, ...]:
        with self._uow_factory() as uow:
            return ObservabilityRepository(
                uow.require_repository().session
            ).recoveries(limit=limit)

    def runtime_status(self) -> OpsRuntimeStatus:
        runtime = self._runtime_status() if self._runtime_status else None
        control = self._control_health() if self._control_health else None
        with self._uow_factory() as uow:
            repo = ObservabilityRepository(uow.require_repository().session)
            pending = repo.pending_approval_count()
            count, latest = repo.event_count_and_latest()

        def component(name: str, status: str, reason: str) -> OpsComponentStatus:
            return OpsComponentStatus(
                component=name,
                status=status,
                reason_code=reason,
            )

        if runtime is None:
            runtime_item = component("runtime", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            channel = component("channel", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            browser = component("browser", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            gateway = component("gateway", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            storage = component("storage", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            overall = "UNKNOWN"
            unknown_count = 0
            queue_depth = 0
        else:
            runtime_item = component(
                "runtime", runtime.runtime.state.value, runtime.runtime.reason_code
            )
            channel = component(
                "channel", runtime.channel.health.value, runtime.channel.reason_code
            )
            browser = component(
                "browser", runtime.browser.health.value, runtime.browser.reason_code
            )
            gateway = component(
                "gateway", runtime.gateway.health.value, runtime.gateway.reason_code
            )
            storage = component(
                "storage", runtime.storage.health.value, runtime.storage.reason_code
            )
            overall = runtime.health.value
            unknown_count = runtime.execution.unknown
            queue_depth = runtime.execution.pending

        if control is None:
            worker = component("worker", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            outbox = component("outbox", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
            policy = component("policy", "UNKNOWN", "STATUS_PROVIDER_UNAVAILABLE")
        else:
            worker = component(
                "worker", control.worker.state.value, "WORKER_STATUS_REPORTED"
            )
            outbox = component(
                "outbox", control.outbox.state.value, "OUTBOX_STATUS_REPORTED"
            )
            policy = component(
                "policy",
                control.policy.state.value,
                (
                    "EXECUTION_POLICY_ENABLED"
                    if control.policy.new_execution_allowed
                    else "EXECUTION_POLICY_BLOCKED"
                ),
            )
            queue_depth = control.metrics.queue_depth
            unknown_count = control.metrics.execution_unknown

        return OpsRuntimeStatus(
            overall=overall,
            runtime=runtime_item,
            channel=channel,
            browser=browser,
            gateway=gateway,
            storage=storage,
            worker=worker,
            outbox=outbox,
            policy=policy,
            pending_approvals=pending,
            execution_queue_depth=queue_depth,
            execution_unknown=unknown_count,
            event_count=count,
            latest_event_at=latest,
            checked_at=utc_now(),
        )

    def snapshot(self) -> OpsConsoleSnapshot:
        return OpsConsoleSnapshot(
            runtime=self.runtime_status(),
            recent_events=self.events(limit=50).items,
            pending_approvals=self.approvals(waiting_only=True, limit=50),
            recent_executions=self.executions(limit=50),
            generated_at=utc_now(),
        )

    @staticmethod
    def _trace_state(events) -> tuple[TraceStopReason, str, str]:
        types = {event.event_type for event in events}
        if any(
            event.event_type is StructuredEventType.DECISION_REQUEST_SENT
            and event.status is StructuredEventStatus.UNKNOWN
            for event in events
        ):
            return (
                TraceStopReason.MANUAL_INTERVENTION,
                "Decision 请求结果未知",
                "保持不执行；检查 AI-CS Gateway 后人工重放消息",
            )
        if StructuredEventType.EXECUTION_UNKNOWN in types:
            return (
                TraceStopReason.EXECUTION_UNKNOWN,
                "Execution UNKNOWN",
                "禁止自动重试；人工核验渠道侧结果",
            )
        if StructuredEventType.RECOVERY_MANUAL_INTERVENTION in types:
            return (
                TraceStopReason.MANUAL_INTERVENTION,
                "人工介入",
                "运行人员处理根因后再恢复",
            )
        if (
            StructuredEventType.RECOVERY_STARTED in types
            and StructuredEventType.RECOVERY_COMPLETED not in types
        ):
            return TraceStopReason.RECOVERY, "恢复中", "等待有限恢复流程结束"
        if StructuredEventType.EXECUTION_FAILED in types:
            return (
                TraceStopReason.EXECUTION_FAILED,
                "Execution FAILED",
                "检查错误码并人工决定后续动作",
            )
        if (
            StructuredEventType.EXECUTION_SUCCESS in types
            and StructuredEventType.RECEIPT_CREATED in types
        ):
            return TraceStopReason.COMPLETED, "Receipt 已记录", "无需后续动作"
        if StructuredEventType.EXECUTION_STARTED in types:
            return (
                TraceStopReason.EXECUTION_RUNNING,
                "Execution RUNNING",
                "等待 Adapter 结果与 Receipt",
            )
        if StructuredEventType.APPROVAL_GRANTED in types:
            return (
                TraceStopReason.EXECUTION_PENDING,
                "已批准，Execution PENDING",
                "等待 Worker 安全领取",
            )
        if StructuredEventType.APPROVAL_REQUIRED in types:
            return (
                TraceStopReason.WAITING_APPROVAL,
                "WAITING_APPROVAL",
                "等待人工批准或拒绝",
            )
        if StructuredEventType.DECISION_REQUEST_SENT in types:
            return (
                TraceStopReason.REQUESTING_DECISION,
                "请求 AI-CS Decision",
                "等待并验证 Decision Response",
            )
        return TraceStopReason.RECEIVING, "消息接收与标准化", "请求 AI-CS Decision"


__all__ = ["ObservabilityService", "TraceNotFound"]
