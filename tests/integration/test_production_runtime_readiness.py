from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from channel_engine.channel import NormalizedMessage
from channel_engine.control.models import KillSwitchState
from channel_engine.control.repository import ControlPlaneRepository
from channel_engine.control.service import ControlPlaneService
from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    DuplicateWorkerOwnership,
    ExecutionCoordinator,
    ExecutionRecovery,
    ExecutionWorker,
    FakeExecutionAdapter,
    WorkerOwnershipRegistry,
)
from channel_engine.gateway import FakeGateway
from channel_engine.models import (
    Conversation,
    Event,
    EventType,
    ExecutionState,
    OutboxState,
)
from channel_engine.outbox import FakeEventPublisher, OutboxPublisher
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import (
    RUNTIME_STORAGE_VERSION,
    RuntimeStorageVersionError,
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)
from channel_engine.storage.orm import RuntimeStorageMetadataRow


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def open_runtime(database_url: str):
    engine, session_factory = create_engine_and_session(database_url)
    create_schema(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return engine, session_factory, uow_factory


def enqueue(uow_factory, suffix: str):
    intake = ConversationService(uow_factory, FakeGateway()).receive(
        NormalizedMessage(
            channel="fake-channel",
            conversation_id=f"production-runtime-{suffix}",
            external_message_id=f"production-message-{suffix}",
            content="approved fake operation",
        )
    )
    return ExecutionCoordinator(uow_factory, ApprovalPolicy()).approve_and_enqueue(
        intake.decision_id, "production-runtime-operator"
    )


def append_event(uow_factory, clock: MutableClock, suffix: str) -> str:
    conversation = Conversation(
        channel_name="fake", external_ref=f"production-outbox-{suffix}"
    )
    event = Event(
        aggregate_type="Conversation",
        aggregate_id=conversation.conversation_id,
        event_type=EventType.MESSAGE_RECEIVED,
        payload={"scenario": suffix},
        correlation_id=f"production-correlation-{suffix}",
        occurred_at=clock(),
    )
    with uow_factory() as uow:
        repo = uow.require_repository()
        repo.save_conversation(conversation)
        repo.append_event(event)
    return event.event_id


def test_running_execution_recovers_after_database_restart_without_resend(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'worker-restart.sqlite3').as_posix()}"
    clock = MutableClock()
    engine, _sessions, first_uow = open_runtime(database_url)
    enqueued = enqueue(first_uow, "worker-crash")
    adapter = FakeExecutionAdapter()
    crashed = ExecutionWorker(
        first_uow,
        adapter,
        "production-crashed-worker",
        lease_duration=timedelta(seconds=5),
        clock=clock,
    )
    claimed = crashed.claim_next()
    assert claimed is not None
    engine.dispose()

    clock.advance(timedelta(seconds=6))
    restarted_engine, _sessions, restarted_uow = open_runtime(database_url)
    recovered = ExecutionRecovery(restarted_uow, clock=clock).recover_expired()

    assert len(recovered) == 1
    assert recovered[0].execution_id == enqueued.execution_id
    assert recovered[0].execution_state is ExecutionState.UNKNOWN
    assert adapter.call_count == 0
    assert (
        ExecutionWorker(
            restarted_uow,
            adapter,
            "production-replacement-worker",
            clock=clock,
        ).run_once()
        is None
    )
    with restarted_uow() as uow:
        repo = uow.require_repository()
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        execution = repo.get_execution(enqueued.execution_id)
    assert receipt is not None
    assert receipt.details["automatic_retry_allowed"] is False
    assert execution.state is ExecutionState.UNKNOWN
    restarted_engine.dispose()


def test_outbox_recovers_unpublished_and_deduplicates_ack_gap_after_restart(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'outbox-restart.sqlite3').as_posix()}"
    clock = MutableClock()
    engine, _sessions, first_uow = open_runtime(database_url)
    unpublished_event_id = append_event(first_uow, clock, "unpublished")
    engine.dispose()

    restarted_engine, _sessions, restarted_uow = open_runtime(database_url)
    first_sink = FakeEventPublisher()
    result = OutboxPublisher(
        restarted_uow, first_sink, "production-publisher", clock=clock
    ).run_once()
    assert result is not None and result.status is OutboxState.PUBLISHED
    assert first_sink.published_events[0].event_id == unpublished_event_id

    ack_gap_event_id = append_event(restarted_uow, clock, "ack-gap")
    with restarted_uow() as uow:
        claimed = uow.require_repository().claim_outbox(
            "publisher-before-crash",
            clock(),
            clock() + timedelta(seconds=5),
        )
    assert claimed is not None and claimed.event_id == ack_gap_event_id
    durable_sink = FakeEventPublisher()
    durable_sink.publish(claimed)
    assert durable_sink.call_count == 1
    restarted_engine.dispose()

    clock.advance(timedelta(seconds=6))
    final_engine, _sessions, final_uow = open_runtime(database_url)
    replay = OutboxPublisher(
        final_uow, durable_sink, "publisher-after-crash", clock=clock
    ).run_once()
    assert replay is not None and replay.status is OutboxState.PUBLISHED
    assert replay.attempt_count == 2
    assert durable_sink.call_count == 1
    assert durable_sink.published_events[0].publish_key == ack_gap_event_id
    final_engine.dispose()


def test_duplicate_worker_id_is_fenced_until_ownership_expires(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'worker-owner.sqlite3').as_posix()}"
    clock = MutableClock()
    engine, _sessions, uow_factory = open_runtime(database_url)
    first = WorkerOwnershipRegistry(
        uow_factory,
        "singleton-production-worker",
        lease_duration=timedelta(seconds=10),
        clock=clock,
    )
    duplicate = WorkerOwnershipRegistry(
        uow_factory,
        "singleton-production-worker",
        lease_duration=timedelta(seconds=10),
        clock=clock,
    )

    ownership = first.ensure_owned()
    assert ownership.runtime_storage_version == RUNTIME_STORAGE_VERSION
    with pytest.raises(DuplicateWorkerOwnership):
        duplicate.ensure_owned()
    enqueue(uow_factory, "duplicate-worker")
    duplicate_adapter = FakeExecutionAdapter()
    duplicate_process = ExecutionWorker(
        uow_factory,
        duplicate_adapter,
        "singleton-production-worker",
        clock=clock,
        ownership_registry=duplicate,
    )
    with pytest.raises(DuplicateWorkerOwnership):
        duplicate_process.run_once()
    assert duplicate_adapter.call_count == 0

    clock.advance(timedelta(seconds=11))
    takeover = duplicate.ensure_owned()
    assert takeover.owner_token == duplicate.owner_token
    with pytest.raises(DuplicateWorkerOwnership):
        first.ensure_owned()
    engine.dispose()


def test_config_and_kill_switch_restore_after_process_restart(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'control-restore.sqlite3').as_posix()}"
    engine, _sessions, first_uow = open_runtime(database_url)
    first_control = ControlPlaneService(first_uow)
    snapshot = first_control.save_config_snapshot(
        adapter_config_version="pdd.adapter.v7",
        policy_version="send-policy.v4",
        gateway_version="gateway.v1",
        operator="production-operator",
        reason="PRODUCTION_CONFIG_CAPTURED",
    )
    first_control.activate_config_snapshot(
        snapshot.snapshot_id,
        operator="production-operator",
        reason="PRODUCTION_CONFIG_ACTIVATED",
    )
    first_control.enable_kill_switch(
        operator="production-operator",
        reason="PRODUCTION_SAFETY_STOP",
    )
    engine.dispose()

    restarted_engine, _sessions, restarted_uow = open_runtime(database_url)
    restored = ControlPlaneService(restarted_uow)
    status = restored.status()
    assert status.kill_switch.state is KillSwitchState.ENABLED
    assert status.active_config == snapshot
    assert len(restored.list_audit_events()) == 3
    restarted_engine.dispose()


def test_runtime_metrics_include_counts_latency_queue_and_adapter_slots(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'runtime-metrics.sqlite3').as_posix()}"
    clock = MutableClock()
    engine, _sessions, uow_factory = open_runtime(database_url)
    enqueue(uow_factory, "latency")
    worker = ExecutionWorker(
        uow_factory, FakeExecutionAdapter(), "metrics-worker", clock=clock
    )
    lease = worker.claim_next()
    assert lease is not None
    clock.advance(timedelta(milliseconds=250))
    worker.process_claim(lease)

    with uow_factory() as uow:
        assert uow.session is not None
        metrics = ControlPlaneRepository(uow.session).operational_metrics()
    assert metrics.execution_count == 1
    assert metrics.execution_success == 1
    assert metrics.execution_failed == 0
    assert metrics.execution_unknown == 0
    assert metrics.execution_latency_sample_count == 1
    assert metrics.execution_latency_avg_ms == pytest.approx(250, abs=2)
    assert metrics.execution_latency_max_ms == pytest.approx(250, abs=2)
    assert metrics.queue_depth == 0
    assert metrics.adapter_healthy == 0
    engine.dispose()


def test_incompatible_runtime_storage_manifest_fails_closed(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'version-fence.sqlite3').as_posix()}"
    engine, session_factory, _uow_factory = open_runtime(database_url)
    with session_factory.begin() as session:
        session.execute(
            update(RuntimeStorageMetadataRow).values(
                runtime_storage_version="99.0"
            )
        )
    with pytest.raises(RuntimeStorageVersionError):
        create_schema(engine)
    engine.dispose()
