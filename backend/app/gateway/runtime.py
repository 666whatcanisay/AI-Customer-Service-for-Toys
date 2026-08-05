from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.gateway.contract import CONTRACT_VERSION, GATEWAY_VERSION


SERVER_RUNTIME_SCHEMA_VERSION = "ai-cs.server-runtime-console.v1"
SERVER_RUNTIME_VERSION = "ai-cs-server-runtime.rc1"


class _RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServerRuntimeState(StrEnum):
    READY = "READY"
    STARTING = "STARTING"
    UNHEALTHY = "UNHEALTHY"


class GatewayRuntimeState(StrEnum):
    DISABLED = "DISABLED"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"


class ServerRuntimeSummary(_RuntimeModel):
    status: ServerRuntimeState
    version: Literal[SERVER_RUNTIME_VERSION]
    runtime_mode: str


class GatewayRuntimeSummary(_RuntimeModel):
    enabled: bool
    status: GatewayRuntimeState
    version: Literal[GATEWAY_VERSION]
    contract_version: Literal[CONTRACT_VERSION]
    configuration_state: Literal["CONFIGURED", "DISABLED", "INVALID"]


class ServerRuntimeConsoleSnapshot(_RuntimeModel):
    schema_version: Literal[SERVER_RUNTIME_SCHEMA_VERSION]
    server: ServerRuntimeSummary
    gateway: GatewayRuntimeSummary


def server_runtime_console_schema() -> dict[str, Any]:
    generated = ServerRuntimeConsoleSnapshot.model_json_schema(
        ref_template="#/$defs/{model}"
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:ai-cs:server-runtime-console:v1",
        **generated,
    }


def server_runtime_console_snapshot(application: Any) -> ServerRuntimeConsoleSnapshot:
    """Return operator-safe process state without credentials or local paths."""
    settings = application.state.settings
    ready = bool(getattr(application.state, "ready", False))
    initialization_error = getattr(application.state, "initialization_error", None)
    server_status = (
        ServerRuntimeState.READY
        if ready
        else ServerRuntimeState.UNHEALTHY
        if initialization_error
        else ServerRuntimeState.STARTING
    )

    gateway_enabled = bool(settings.gateway_enabled)
    gateway_server = getattr(application.state, "gateway_server", None)
    gateway_error = getattr(application.state, "gateway_initialization_error", None)
    if not gateway_enabled:
        gateway_status = GatewayRuntimeState.DISABLED
        configuration_state = "DISABLED"
    elif gateway_server is None or gateway_error:
        gateway_status = GatewayRuntimeState.UNHEALTHY
        configuration_state = "INVALID"
    else:
        gateway_status = GatewayRuntimeState(gateway_server.health().status.value)
        configuration_state = "CONFIGURED"

    return ServerRuntimeConsoleSnapshot(
        schema_version=SERVER_RUNTIME_SCHEMA_VERSION,
        server=ServerRuntimeSummary(
            status=server_status,
            version=SERVER_RUNTIME_VERSION,
            runtime_mode=settings.server_runtime_mode,
        ),
        gateway=GatewayRuntimeSummary(
            enabled=gateway_enabled,
            status=gateway_status,
            version=GATEWAY_VERSION,
            contract_version=CONTRACT_VERSION,
            configuration_state=configuration_state,
        ),
    )
