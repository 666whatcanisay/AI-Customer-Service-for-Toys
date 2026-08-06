from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealth,
    AdapterHealthStatus,
    AdapterRegistry,
    ChannelConversation,
    ChannelSendReceipt,
    NormalizedMessage,
    OutboundMessage,
)
from channel_engine.control.gate import (
    ExecutionControlBlocked,
    PersistentExecutionControlGate,
)
from channel_engine.control.health import (
    ControlPlaneHealthAggregator,
    WorkerRuntimeMonitor,
)
from channel_engine.control.models import (
    AdapterConnectionState,
    ComponentHealthState,
    EngineRuntimeState,
    ExecutionPolicyState,
    GatewayStatus,
    KillSwitchState,
    OutboxRuntimeState,
    WorkerRuntimeState,
)
from channel_engine.control.service import ControlPlaneService
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.models import DecisionState, ExecutionState, ReceiptOutcome
from channel_engine.policy import ApprovalPolicy


class ControlClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int = 1) -> None:
        self.current += timedelta(seconds=seconds)


def create_waiting_decision(foundation, suffix: str):
    return ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(
        NormalizedMessage(
            channel="fake-control",
            conversation_id=f"control-conversation-{suffix}",
            external_message_id=f"control-message-{suffix}",
            sender="synthetic-control-customer",
            content=f"synthetic control request {suffix}",
            timestamp=datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc),
        )
    )


def test_kill_switch_blocks_new_and_pending_but_running_execution_finishes(
    foundation,
) -> None:
    clock = ControlClock()
    control = ControlPlaneService(foundation["uow_factory"], clock=clock)
    gate = PersistentExecutionControlGate(clock=clock)
    coordinator = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
        control_gate=gate,
    )
    worker = ExecutionWorker(
        foundation["uow_factory"],
        foundation["executor"],
        "control-plane-worker",
        clock=clock,
        control_gate=gate,
    )

    blocked_decision = create_waiting_decision(foundation, "blocked-new")
    control.enable_kill_switch(
        operator="incident.operator",
        reason="INCIDENT_CONTAINMENT",
    )
    with pytest.raises(ExecutionControlBlocked):
        coordinator.approve_and_enqueue(
            blocked_decision.decision_id,
            "human.operator",
        )
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        decision = repo.get_decision(blocked_decision.decision_id)
        assert decision.state is DecisionState.WAITING_APPROVAL
        assert repo.get_approval_for_decision(blocked_decision.decision_id) is None
        assert repo.get_execution_for_decision(blocked_decision.decision_id) is None

    clock.advance()
    control.disable_kill_switch(
        operator="incident.operator",
        reason="CONTROLLED_EXECUTION_RESUME",
    )
    pending = coordinator.approve_and_enqueue(
        blocked_decision.decision_id,
        "human.operator",
    )
    clock.advance()
    control.enable_kill_switch(
        operator="incident.operator",
        reason="PAUSE_PENDING_EXECUTIONS",
    )
    assert worker.run_once() is None
    assert foundation["executor"].call_count == 0
    with foundation["uow_factory"]() as uow:
        assert (
            uow.require_repository().get_execution(pending.execution_id).state
            is ExecutionState.PENDING
        )

    clock.advance()
    control.disable_kill_switch(
        operator="incident.operator",
        reason="ALLOW_ONE_CONTROLLED_EXECUTION",
    )
    running_lease = worker.claim_next()
    assert running_lease is not None
    assert running_lease.execution.state is ExecutionState.RUNNING
    clock.advance()
    control.enable_kill_switch(
        operator="incident.operator",
        reason="STOP_AFTER_RUNNING_EXECUTION",
    )

    completed = worker.process_claim(running_lease)

    assert completed.execution_state is ExecutionState.SUCCESS
    assert completed.receipt_outcome is ReceiptOutcome.SUCCESS
    assert foundation["executor"].call_count == 1
    assert worker.run_once() is None
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        receipt = repo.get_receipt_for_execution(pending.execution_id)
        execution = repo.get_execution(pending.execution_id)
    assert receipt is not None and receipt.outcome is ReceiptOutcome.SUCCESS
    assert execution.state is ExecutionState.SUCCESS

    kill = control.kill_switch_status()
    assert kill.state is KillSwitchState.ENABLED
    audits = control.list_audit_events()
    assert len(audits) == 5
    assert audits[0].before.kill_switch is KillSwitchState.DISABLED
    assert audits[0].after.kill_switch is KillSwitchState.ENABLED
    assert audits[-1].operator == "incident.operator"
    serialized = "".join(event.model_dump_json() for event in audits).lower()
    for prohibited in (
        '"secret"',
        '"token"',
        '"customer_message"',
        '"content"',
    ):
        assert prohibited not in serialized


class MutableHealthAdapter:
    channel = "health-channel"
    adapter_name = "MutableHealthAdapter"

    def __init__(self, clock: ControlClock) -> None:
        self.clock = clock
        self.status = AdapterHealthStatus.HEALTHY

    def receive_message(self) -> NormalizedMessage | None:
        return None

    def send_message(self, message: OutboundMessage) -> ChannelSendReceipt:
        del message
        raise RuntimeError("health adapter does not execute")

    def get_conversation(self, conversation_id: str) -> ChannelConversation | None:
        del conversation_id
        return None

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=self.status,
            checked_at=self.clock(),
            real_platform_connected=False,
            details={"mode": "CONTROL_TEST", "real_platform_called": False},
        )


class MutableGatewayProbe:
    def __init__(self, clock: ControlClock) -> None:
        self.clock = clock
        self.healthy = True

    def __call__(self) -> GatewayStatus:
        return GatewayStatus(
            health=(
                ComponentHealthState.HEALTHY
                if self.healthy
                else ComponentHealthState.DEGRADED
            ),
            reachable=self.healthy,
            gateway_version="gateway-health-test.v1" if self.healthy else None,
            checked_at=self.clock(),
        )


def test_health_aggregation_tracks_gateway_adapter_worker_outbox_and_policy(
    foundation,
) -> None:
    clock = ControlClock()
    control = ControlPlaneService(foundation["uow_factory"], clock=clock)
    registry = AdapterRegistry()
    adapter = MutableHealthAdapter(clock)
    registry.register(adapter)
    gateway = MutableGatewayProbe(clock)
    worker = WorkerRuntimeMonitor("health-worker", clock=clock)
    worker.mark_running()
    aggregator = ControlPlaneHealthAggregator(
        foundation["uow_factory"],
        control,
        registry,
        gateway,
        worker,
        service_name="channel-engine-control-test",
        environment="test",
        outbox_backlog_threshold=1,
        clock=clock,
    )

    healthy = aggregator.snapshot()
    assert healthy.control_plane_version == "1.0"
    assert healthy.engine.state is EngineRuntimeState.RUNNING
    assert healthy.gateway.health is ComponentHealthState.HEALTHY
    assert healthy.adapters[0].connection is AdapterConnectionState.CONNECTED
    assert healthy.worker.state is WorkerRuntimeState.RUNNING
    assert healthy.outbox.state is OutboxRuntimeState.HEALTHY
    assert healthy.policy.state is ExecutionPolicyState.ENABLED
    assert healthy.metrics.adapter_healthy == 1
    assert healthy.metrics.adapter_disconnected == 0

    gateway.healthy = False
    assert aggregator.snapshot().engine.state is EngineRuntimeState.DEGRADED
    gateway.healthy = True
    adapter.status = AdapterHealthStatus.UNHEALTHY
    disconnected = aggregator.snapshot()
    assert disconnected.adapters[0].connection is AdapterConnectionState.DISCONNECTED
    assert disconnected.metrics.adapter_healthy == 0
    assert disconnected.metrics.adapter_disconnected == 1
    assert disconnected.engine.state is EngineRuntimeState.DEGRADED
    adapter.status = AdapterHealthStatus.HEALTHY
    worker.mark_stopped()
    assert aggregator.snapshot().worker.state is WorkerRuntimeState.STOPPED

    worker.mark_running()
    create_waiting_decision(foundation, "health-outbox")
    backlog = aggregator.snapshot()
    assert backlog.outbox.state is OutboxRuntimeState.BACKLOG
    assert backlog.metrics.outbox_pending >= 1
    assert backlog.engine.state is EngineRuntimeState.DEGRADED

    control.enable_kill_switch(
        operator="health.operator",
        reason="OPERATIONAL_SAFETY_STOP",
    )
    stopped = aggregator.snapshot()
    assert stopped.engine.state is EngineRuntimeState.STOPPED
    assert stopped.kill_switch.state is KillSwitchState.ENABLED
    assert stopped.policy.state is ExecutionPolicyState.BLOCKED
    assert stopped.policy.new_execution_allowed is False
    assert stopped.policy.pending_claim_allowed is False
    assert stopped.policy.running_execution_may_finish is True


def test_sensitive_audit_reason_rolls_back_control_change(foundation) -> None:
    control = ControlPlaneService(foundation["uow_factory"])

    with pytest.raises(ValidationError, match="prohibited marker"):
        control.enable_kill_switch(
            operator="security.operator",
            reason="TOKEN_EXPOSURE_DETAILS",
        )

    assert control.kill_switch_status().state is KillSwitchState.DISABLED
    assert control.list_audit_events() == []
