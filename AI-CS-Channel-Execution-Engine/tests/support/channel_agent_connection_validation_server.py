from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from channel_agent.contract import ManagedAgentConfig
from channel_engine.agent.binding_repository import SqlAlchemyAgentIdentityRepository
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.security.rbac import (
    OperatorAccessDenied,
    OperatorIdentityProvider,
    OperatorPermission,
    OperatorPrincipal,
    OperatorRole,
)
from channel_engine.storage import create_engine_and_session, create_schema


VALIDATION_ADMIN_SESSION = "channel-agent-validation-admin"


class ValidationIdentityProvider(OperatorIdentityProvider):
    """Synthetic identity provider used only by the local validation harness."""

    def authenticate(self, session_reference: str) -> OperatorPrincipal:
        if session_reference != VALIDATION_ADMIN_SESSION:
            raise OperatorAccessDenied(OperatorPermission.AGENT_IDENTITY_READ)
        return OperatorPrincipal(
            principal_id="channel-agent-validation-admin",
            roles=frozenset({OperatorRole.ADMIN}),
            identity_provider="local-production-connection-validation",
            authenticated_at=datetime.now(UTC),
        )


def create_validation_app(database: Path) -> FastAPI:
    engine, session_factory = create_engine_and_session(
        f"sqlite:///{database.resolve().as_posix()}"
    )
    create_schema(engine)
    registry = ChannelAgentNodeRegistry(
        managed_config=ManagedAgentConfig(
            revision="production-connection-validation-v1",
            heartbeat_interval_seconds=0.1,
        ),
        identity_repository=SqlAlchemyAgentIdentityRepository(session_factory),
    )
    app = FastAPI(title="Channel Agent Production Connection Validation")
    app.state.channel_agent_node_registry = registry
    app.state.validation_engine = engine
    app.include_router(
        create_channel_agent_node_router(
            registry,
            identity_provider=ValidationIdentityProvider(),
        )
    )

    @app.on_event("shutdown")
    def dispose_validation_engine() -> None:
        engine.dispose()

    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(
        create_validation_app(args.database),
        host="127.0.0.1",
        port=args.port,
        log_level="critical",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
