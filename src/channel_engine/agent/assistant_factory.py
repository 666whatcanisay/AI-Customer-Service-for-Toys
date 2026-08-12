from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.observation_stages import ObservationStage
from channel_engine.customer_assistant import (
    AICustomerReplyService,
    BufferedCustomerMessage,
    BufferedMessageDisposition,
    CustomerAssistantRuntime,
    CustomerContextCollector,
    OfflineReplyControlStore,
    SQLiteConversationBuffer,
)
from channel_engine.gateway import (
    GatewayAdapterConfig,
    GatewayEnvironment,
    GatewayRetryPolicy,
    ProductionGatewayClient,
)
from channel_engine.pdd_adapter import PDDPrivacyFilteredMessage
from channel_engine.storage import SqlAlchemyUnitOfWork

from .control_store import AgentControlStore
from .assistant_projection import AssistantProjectionReconciler
from .observation_pipeline import AgentObservationContextProvider
from .observation_worker import AgentObservationWorker


class DurableAssistantIngestRuntime:
    """Production buffer port for HOST_INGEST/ASSISTANT_FEED stages."""

    def __init__(self, buffer: SQLiteConversationBuffer) -> None:
        self.buffer = buffer

    def ingest_redacted(
        self, message: PDDPrivacyFilteredMessage
    ) -> BufferedMessageDisposition:
        return self.buffer.append(
            BufferedCustomerMessage.from_redacted(
                store_id=message.store_id,
                conversation_id=message.conversation_id,
                external_message_id=message.external_message_id,
                content=message.content,
                timestamp=message.timestamp,
                received_at=message.captured_at,
            )
        )


@dataclass(slots=True)
class HostAssistantComposition:
    worker: AgentObservationWorker
    offline_control: OfflineReplyControlStore
    buffer: SQLiteConversationBuffer
    gateway: ProductionGatewayClient | None = None
    projection_reconciler: AssistantProjectionReconciler | None = None

    def close(self) -> None:
        if self.gateway is not None:
            self.gateway.close()


def build_host_assistant_composition(
    *,
    control_store: AgentControlStore,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    stage: ObservationStage,
    environ: Mapping[str, str] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> HostAssistantComposition:
    """Build the real offline Host composition without any PDD/send adapter."""

    source = os.environ if environ is None else environ
    runtime_root = Path(
        source.get("CHANNEL_ENGINE_OFFLINE_RUNTIME_ROOT", ".runtime/offline-complete")
    ).expanduser().resolve()
    try:
        quiet_window_ms = int(source.get("CHANNEL_ENGINE_BUFFER_QUIET_WINDOW_MS", "4000"))
    except ValueError as exc:
        raise ValueError("CHANNEL_ENGINE_BUFFER_QUIET_WINDOW_MS must be an integer") from exc
    if not 1 <= quiet_window_ms <= 60_000:
        raise ValueError("CHANNEL_ENGINE_BUFFER_QUIET_WINDOW_MS is outside policy")
    buffer = SQLiteConversationBuffer(
        runtime_root / "conversation-buffer.sqlite3",
        quiet_window=timedelta(milliseconds=quiet_window_ms),
        processing_lease=timedelta(minutes=2),
        clock=clock,
    )
    offline_control = OfflineReplyControlStore(
        runtime_root / "offline-control.sqlite3",
        clock=clock,
    )
    if not stage.allows(ObservationStage.AI_SUGGESTIONS):
        worker = AgentObservationWorker(
            control_store,
            DurableAssistantIngestRuntime(buffer),  # type: ignore[arg-type]
            stage=stage,
            offline_control=offline_control,
            clock=clock,
        )
        return HostAssistantComposition(worker, offline_control, buffer)

    secret_reference = (
        source.get("CHANNEL_ENGINE_GATEWAY_KEY_REFERENCE")
        or source.get("AI_CS_GATEWAY_KEY_REFERENCE")
        or ""
    ).strip()
    if not secret_reference:
        raise ValueError(
            "AI_SUGGESTIONS requires CHANNEL_ENGINE_GATEWAY_KEY_REFERENCE"
        )
    secret_path = Path(secret_reference).expanduser().resolve()
    secret = secret_path.read_bytes().strip()
    if len(secret) < 32:
        raise ValueError("AI-CS Gateway key reference is invalid")
    environment_name = source.get(
        "CHANNEL_ENGINE_GATEWAY_ENVIRONMENT", "mock"
    ).strip().lower()
    try:
        gateway_environment = GatewayEnvironment(environment_name)
    except ValueError as exc:
        raise ValueError("CHANNEL_ENGINE_GATEWAY_ENVIRONMENT is invalid") from exc
    gateway = ProductionGatewayClient(
        GatewayAdapterConfig(
            environment=gateway_environment,
            base_url=(
                source.get("CHANNEL_ENGINE_GATEWAY_BASE_URL")
                or source.get("AI_CS_GATEWAY_BASE_URL")
                or "http://127.0.0.1:8420"
            ),
            client_id=source.get("CHANNEL_ENGINE_GATEWAY_CLIENT_ID", "channel-engine"),
            key_id=source.get("CHANNEL_ENGINE_GATEWAY_KEY_ID", "gateway-key-v1"),
            production_enabled=False,
            timeout_seconds=float(
                source.get("CHANNEL_ENGINE_GATEWAY_TIMEOUT_SECONDS", "18")
            ),
        ),
        secret,
        retry_policy=GatewayRetryPolicy(max_attempts=1),
    )
    provider = AgentObservationContextProvider(
        control_store,
        buffer,
        offline_control=offline_control,
        clock=clock,
    )
    assistant = CustomerAssistantRuntime(
        buffer,
        CustomerContextCollector(
            provider,
            provider,
            provider,
            provider,
            clock=clock,
            visible_history_provider=provider,
        ),
        AICustomerReplyService(uow_factory, gateway, clock=clock),
        None,
        None,
        uow_factory,
        clock=clock,
        real_send_enabled=False,
    )
    worker = AgentObservationWorker(
        control_store,
        assistant,
        stage=stage,
        offline_control=offline_control,
        clock=clock,
    )
    return HostAssistantComposition(
        worker,
        offline_control,
        buffer,
        gateway,
        AssistantProjectionReconciler(
            control_store,
            assistant,
            offline_control,
            clock=clock,
        ),
    )


__all__ = [
    "DurableAssistantIngestRuntime",
    "HostAssistantComposition",
    "build_host_assistant_composition",
]
