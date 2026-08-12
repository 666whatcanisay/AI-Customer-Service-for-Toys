from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.control_v2 import AgentAssistantSnapshot, AgentObservationSubmission
from channel_agent.observation_stages import ObservationStage
from channel_engine.agent.assistant_projection import (
    AssistantProjectionReconciliation,
    AssistantProjectionReconciler,
)
from channel_engine.agent.control_store import AgentControlStore
from channel_engine.agent.observation_pipeline import AgentObservationContextProvider
from channel_engine.agent.observation_worker import (
    AgentObservationWorker,
    AgentObservationWorkerResult,
)
from channel_engine.customer_assistant import (
    AICustomerReplyService,
    AuthorizationKind,
    CustomerAssistantRuntime,
    CustomerContextCollector,
    ExecutionPreparation,
    OfflineReplyControlStore,
    PipelineStage,
    PipelineStageState,
    PipelineTraceStep,
    ReplyPolicy,
    ReplyPolicyMode,
    SQLiteConversationBuffer,
)
from channel_engine.gateway import AICSGateway
from channel_engine.operations import (
    RuntimeBackupManifest,
    RuntimeBackupSet,
    RuntimeMaintenanceBarrier,
)
from channel_engine.operations.runtime_backup import sqlite_high_water
from channel_engine.provider import ChannelMessageProvider, NormalizedChannelObservation
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


class OfflineCompleteRuntime:
    """One-computer black-box composition ending at EXECUTION_PREPARED."""

    profile = "OFFLINE_COMPLETE"
    real_pdd_enabled = False
    real_send_enabled = False

    def __init__(
        self,
        root: str | Path,
        gateway: AICSGateway,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        quiet_window: timedelta = timedelta(milliseconds=1),
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._maintenance = RuntimeMaintenanceBarrier()
        self._engine, sessions = create_engine_and_session(
            f"sqlite:///{(self.root / 'host.sqlite3').as_posix()}"
        )
        create_schema(self._engine)
        self.control_store = AgentControlStore(sessions, clock=clock)
        self._uow_factory = lambda: SqlAlchemyUnitOfWork(sessions)
        self.buffer = SQLiteConversationBuffer(
            self.root / "conversation-buffer.sqlite3",
            quiet_window=quiet_window,
            processing_lease=timedelta(minutes=2),
            clock=clock,
        )
        self.offline_control = OfflineReplyControlStore(
            self.root / "offline-control.sqlite3", clock=clock
        )
        context_provider = AgentObservationContextProvider(
            self.control_store,
            self.buffer,
            offline_control=self.offline_control,
            clock=clock,
        )
        assistant = CustomerAssistantRuntime(
            self.buffer,
            CustomerContextCollector(
                context_provider,
                context_provider,
                context_provider,
                context_provider,
                clock=clock,
                visible_history_provider=context_provider,
            ),
            AICustomerReplyService(self._uow_factory, gateway, clock=clock),
            None,
            None,
            self._uow_factory,
            clock=clock,
            real_send_enabled=False,
        )
        self._worker = AgentObservationWorker(
            self.control_store,
            assistant,
            stage=ObservationStage.AI_SUGGESTIONS,
            offline_control=self.offline_control,
            clock=clock,
            fault_injector=fault_injector,
        )
        self._reconciler = AssistantProjectionReconciler(
            self.control_store,
            assistant,
            self.offline_control,
            clock=clock,
        )
        self.last_reconciliation = self._reconciler.reconcile()

    def ingest_provider(
        self,
        provider: ChannelMessageProvider,
        *,
        agent_id: str = "offline-agent",
        device_id: str = "offline-device",
        limit: int = 100,
    ) -> int:
        with self._maintenance.operation():
            observations = provider.poll(limit=max(1, min(limit, 100)))
            for value in observations:
                self._accept(value, agent_id=agent_id, device_id=device_id)
            return len(observations)

    def drain(self, *, limit: int = 100) -> AgentObservationWorkerResult:
        with self._maintenance.operation():
            return self._worker.run_once(limit=limit)

    def reconcile_projections(self) -> AssistantProjectionReconciliation:
        self.last_reconciliation = self._reconciler.reconcile()
        return self.last_reconciliation

    def set_policy(
        self,
        store_id: str,
        mode: ReplyPolicyMode,
        *,
        authorized_by: str = "offline:operator",
    ) -> ReplyPolicy:
        with self._maintenance.operation():
            return self.offline_control.set_policy(
                store_id, mode, authorized_by=authorized_by
            )

    def prepare_manually(
        self,
        decision_id: str,
        *,
        authorized_by: str,
        store_id: str,
        conversation_id: str,
        customer_reference: str,
    ) -> ExecutionPreparation:
        with self._maintenance.operation():
            prepared = self.offline_control.prepare(
                decision_id,
                authorization_kind=AuthorizationKind.HUMAN,
                authorized_by=authorized_by,
                expected_store_id=store_id,
                expected_conversation_id=conversation_id,
                expected_customer_reference=customer_reference,
            )
            self.control_store.mark_snapshot_execution_prepared(prepared)
            return prepared

    def create_backup(
        self,
        destination: str | Path,
        *,
        assets: dict[str, str | Path] | None = None,
        timeout_seconds: float = 30.0,
    ) -> RuntimeBackupManifest:
        with self._maintenance.quiesce(timeout_seconds=timeout_seconds):
            reconciliation = self._reconciler.reconcile()
            self.last_reconciliation = reconciliation
            databases = {
                "HOST_CONTROL": self.root / "host.sqlite3",
                "CONVERSATION_BUFFER": self.root / "conversation-buffer.sqlite3",
                "OFFLINE_CONTROL": self.root / "offline-control.sqlite3",
            }
            high_water = {
                role: sqlite_high_water(path) for role, path in databases.items()
            }
            return RuntimeBackupSet(
                databases,
                assets=assets,
                clock=self._clock,
            ).create(
                destination,
                projection_reconciliation={
                    "durable_replies": reconciliation.durable_replies,
                    "decisions_repaired": reconciliation.decisions_repaired,
                    "snapshots_rebuilt": reconciliation.snapshots_rebuilt,
                    "unchanged": reconciliation.unchanged,
                    "unroutable": reconciliation.unroutable,
                },
                high_water_marks=high_water,
            )

    def conversations(
        self,
        *,
        agent_id: str = "offline-agent",
        device_id: str = "offline-device",
    ) -> tuple[AgentAssistantSnapshot, ...]:
        return self.control_store.assistant_snapshots(agent_id, device_id, limit=100)

    def trace(self, trace_id: str) -> tuple[PipelineTraceStep, ...]:
        return self.offline_control.trace(trace_id)

    def close(self) -> None:
        self._engine.dispose()

    def _accept(
        self,
        value: NormalizedChannelObservation,
        *,
        agent_id: str,
        device_id: str,
    ) -> None:
        self.offline_control.record_trace(
            value.trace_id,
            PipelineStage.PROVIDER_READ,
            PipelineStageState.SUCCEEDED,
            "PROVIDER_OBSERVATION_NORMALIZED",
        )
        self.offline_control.record_trace(
            value.trace_id,
            PipelineStage.EDGE_SPOOL,
            PipelineStageState.SUCCEEDED,
            "OFFLINE_EDGE_COMMITTED",
        )
        payload = value.pdd_payload()
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        identity = f"{value.provider_id}\0{value.store_id}\0{value.external_message_id}"
        self.control_store.persist_observation(
            AgentObservationSubmission(
                observation_id="provider-observation:"
                + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                agent_id=agent_id,
                device_id=device_id,
                store_id=value.store_id,
                conversation_id=value.conversation_id,
                external_message_id=value.external_message_id,
                source_cursor=value.source_cursor,
                source_sequence=value.source_sequence,
                payload_digest="sha256:" + hashlib.sha256(canonical).hexdigest(),
                payload=payload,
                captured_at=value.captured_at,
            )
        )
        self.offline_control.record_trace(
            value.trace_id,
            PipelineStage.HOST_PERSIST,
            PipelineStageState.SUCCEEDED,
            "HOST_ACK_COMMITTED",
        )


__all__ = ["OfflineCompleteRuntime"]
