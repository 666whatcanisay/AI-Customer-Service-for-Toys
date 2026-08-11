from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from channel_engine import __version__
from channel_engine.observability.api import create_observability_router
from channel_engine.observability.device_admin_client import (
    HttpAICSDeviceAdminClient,
    OperationsAdminSessionBroker,
)
from channel_engine.observability.service import ObservabilityService
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


def create_operations_console_app() -> FastAPI:
    """Create the 18020 UI/BFF; it owns no authoritative device repository."""

    database_url = os.getenv(
        "CHANNEL_ENGINE_OPERATIONS_DATABASE_URL",
        "sqlite:///.runtime/channel-agent-lan-host/operations-console.sqlite3",
    )
    ai_cs_base_url = os.getenv(
        "CHANNEL_ENGINE_AI_CS_ADMIN_URL",
        "http://127.0.0.1:8423",
    )
    engine, session_factory = create_engine_and_session(database_url)
    uow_factory = lambda: SqlAlchemyUnitOfWork(session_factory)
    service = ObservabilityService(uow_factory)
    admin_sessions = OperationsAdminSessionBroker(ai_cs_base_url)
    device_client = HttpAICSDeviceAdminClient(ai_cs_base_url)

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        create_schema(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="AI-CS Operations Console",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(
        create_observability_router(
            service,
            device_admin_client=device_client,
            admin_sessions=admin_sessions,
        )
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "channel-engine-operations-console",
            "version": __version__,
            "device_state_source": "CHANNEL_ENGINE_HOST_CONTROL_VIA_AI_CS",
        }

    application.state.production_profile = "OPERATIONS_CONSOLE_CLIENT"
    application.state.device_repository_authority = False
    return application


app = create_operations_console_app()


__all__ = ["app", "create_operations_console_app"]
