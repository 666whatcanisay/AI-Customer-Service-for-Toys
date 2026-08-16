from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy.engine import make_url

from channel_agent.control_v2 import (
    AgentCommandEnvelope,
    AgentObservationSubmission,
    ServiceApprovalDelivery,
)
from channel_agent.observation_stages import ObservationStage
from channel_engine import __version__
from channel_engine.agent.assistant_factory import (
    HostAssistantComposition,
    build_host_assistant_composition,
)
from channel_engine.agent.binding_repository import (
    SqlAlchemyActiveStoreGuard,
    SqlAlchemyAgentIdentityRepository,
    SqlAlchemyEnrollmentGrantRepository,
)
from channel_engine.agent.control_store import (
    AgentControlStore,
    SqlAlchemyReplayNonceStore,
)
from channel_engine.agent.control_v2 import (
    create_channel_agent_control_v2_router,
    create_channel_agent_service_v2_router,
)
from channel_engine.agent.execution_commands import SqlAlchemyAgentReceiptReconciler
from channel_engine.agent.host_control import (
    build_agent_control_v2_from_env,
    build_ai_cs_service_verifier_from_env,
)
from channel_engine.agent.node_api import ChannelAgentNodeRegistry
from channel_engine.agent.observation_worker import (
    AgentObservationWorker,
    AgentObservationWorkerRunner,
)
from channel_engine.config import Settings
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    validate_schema,
)
from channel_engine.storage.runtime_database_identity import validate_runtime_database


def _observation_stage_from_env() -> ObservationStage:
    raw = os.getenv("CHANNEL_ENGINE_OBSERVATION_STAGE", "DISABLED").strip().upper()
    try:
        return ObservationStage(raw)
    except ValueError as exc:
        raise ValueError("CHANNEL_ENGINE_OBSERVATION_STAGE is invalid") from exc


def create_host_control_app(
    settings: Settings | None = None,
    *,
    approval_command_factory: Callable[
        [ServiceApprovalDelivery], AgentCommandEnvelope
    ]
    | None = None,
    observation_handler: Callable[[AgentObservationSubmission], object] | None = None,
    observation_worker: AgentObservationWorker | None = None,
) -> FastAPI:
    """Create the production LAN control-plane application.

    Deliberately excluded: V1 Agent routes, Fake/Sandbox/Pilot adapters, browser
    automation and execution test endpoints.  Those remain available only from
    ``channel_engine.app`` for explicit development/test use.
    """

    active_settings = settings or Settings.from_env()
    worker_injected = observation_worker is not None
    engine, session_factory = create_engine_and_session(active_settings.database_url)
    control_store = AgentControlStore(session_factory)
    uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory)
    receipt_reconciler = SqlAlchemyAgentReceiptReconciler(uow_factory)
    replay_nonce_store = SqlAlchemyReplayNonceStore(session_factory)
    agent_repository = SqlAlchemyAgentIdentityRepository(session_factory)
    registry = ChannelAgentNodeRegistry(
        identity_repository=agent_repository,
        runtime_repository=agent_repository,
        enrollment_grant_repository=SqlAlchemyEnrollmentGrantRepository(session_factory),
        active_store_guard=SqlAlchemyActiveStoreGuard(session_factory),
    )
    configured_stage = _observation_stage_from_env()
    assistant_composition: HostAssistantComposition | None = None
    if (
        observation_worker is None
        and configured_stage.allows(ObservationStage.HOST_INGEST)
    ):
        assistant_composition = build_host_assistant_composition(
            control_store=control_store,
            uow_factory=uow_factory,
            stage=configured_stage,
        )
        observation_worker = assistant_composition.worker
    worker_runner = (
        AgentObservationWorkerRunner(observation_worker)
        if observation_worker is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        validate_schema(engine)
        if active_settings.require_database_identity:
            database_path = _local_sqlite_path(active_settings.database_url)
            if (
                active_settings.database_binding_path is None
                or active_settings.database_environment_id is None
            ):
                raise ValueError("Channel Engine runtime database identity is required")
            validate_runtime_database(
                database_path,
                active_settings.database_binding_path,
                expected_environment_id=active_settings.database_environment_id,
            )
        if (
            assistant_composition is not None
            and assistant_composition.projection_reconciler is not None
        ):
            application.state.channel_agent_projection_reconciliation = (
                assistant_composition.projection_reconciler.reconcile()
            )
        if worker_runner is not None:
            worker_runner.start()
        try:
            yield
        finally:
            if worker_runner is not None:
                worker_runner.stop()
            if assistant_composition is not None:
                assistant_composition.close()
            engine.dispose()

    application = FastAPI(
        title="AI-CS Channel Engine Host Control",
        version=__version__,
        lifespan=lifespan,
    )

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "channel-engine-host-control",
            "version": __version__,
            "agent_control_protocol": "2.1",
        }

    pairing = None
    configured_control = build_agent_control_v2_from_env(
        server_version=__version__,
        nonce_store=replay_nonce_store,
    )
    if configured_control is not None:
        pairing, verifier = configured_control
        application.include_router(
            create_channel_agent_control_v2_router(
                registry,
                pairing,
                verifier,
                control_store,
                receipt_reconciler,
                observation_handler,
                offline_control=(
                    assistant_composition.offline_control
                    if assistant_composition is not None
                    else None
                ),
            )
        )
        application.state.channel_agent_control_v2_pairing = pairing
        application.state.channel_agent_control_v2_verifier = verifier

    service_verifier = build_ai_cs_service_verifier_from_env(
        nonce_store=replay_nonce_store,
    )
    if service_verifier is not None:
        application.include_router(
            create_channel_agent_service_v2_router(
                registry,
                service_verifier,
                control_store,
                pairing=pairing,
                approval_command_factory=approval_command_factory,
                offline_control=(
                    assistant_composition.offline_control
                    if assistant_composition is not None
                    else None
                ),
            )
        )
        application.state.channel_agent_service_v2_verifier = service_verifier

    application.state.channel_agent_node_registry = registry
    application.state.channel_agent_control_store = control_store
    application.state.channel_agent_observation_worker = worker_runner
    application.state.channel_agent_offline_control = (
        assistant_composition.offline_control
        if assistant_composition is not None
        else None
    )
    application.state.channel_agent_observation_stage = (
        ObservationStage.AI_SUGGESTIONS.value
        if worker_injected
        else configured_stage.value
    )
    application.state.production_profile = "HOST_CONTROL"
    return application


def _local_sqlite_path(database_url: str) -> Path:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        raise ValueError("production Host Control requires an explicit SQLite database")
    path = Path(parsed.database).expanduser()
    if not path.is_absolute():
        raise ValueError("production Host Control SQLite path must be absolute")
    return path.resolve(strict=False)


def run() -> None:
    """Run only the production Host Control composition."""

    import uvicorn

    uvicorn.run(
        "channel_engine.production_app:create_host_control_app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        factory=True,
    )


__all__ = ["create_host_control_app", "run"]
