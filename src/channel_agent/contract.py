from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field

from .identity import AgentIdentity, AgentIdentityStatus
from .version import AGENT_PROTOCOL_VERSION


class AgentRuntimeStatus(StrEnum):
    STARTING = "STARTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


class AgentContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ManagedAgentConfig(AgentContractModel):
    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION
    revision: str = Field(min_length=1, max_length=128)
    heartbeat_interval_seconds: float = Field(default=30.0, ge=0.05, le=300.0)
    message_read_enabled: Literal[False] = False
    send_enabled: Literal[False] = False
    browser_automation_enabled: Literal[False] = False


class AgentRegistrationRequest(AgentContractModel):
    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    agent_version: str = Field(
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("agent_version", "version"),
    )
    user_reference: str | None = Field(default=None, min_length=1, max_length=160)
    store_reference: str | None = Field(default=None, min_length=1, max_length=160)
    store_references: tuple[str, ...] = Field(default=(), max_length=32)
    hostname: str = Field(min_length=1, max_length=255)
    status: AgentRuntimeStatus
    timestamp: AwareDatetime


class AgentRegistrationResponse(AgentContractModel):
    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION
    accepted: Literal[True] = True
    registration_id: str = Field(min_length=1, max_length=160)
    identity: AgentIdentity
    production_eligible: bool
    config: ManagedAgentConfig
    server_time: AwareDatetime


class AgentHeartbeatRequest(AgentContractModel):
    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_id: str | None = Field(default=None, min_length=1, max_length=160)
    store_id: str | None = Field(default=None, min_length=1, max_length=160)
    store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    binding_revision: int = Field(default=0, ge=0)
    version: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    status: AgentRuntimeStatus
    timestamp: AwareDatetime


class AgentHeartbeatAck(AgentContractModel):
    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION
    accepted: Literal[True] = True
    identity_status: AgentIdentityStatus
    production_eligible: bool
    config_revision: str = Field(min_length=1, max_length=128)
    identity: AgentIdentity | None = None
    server_time: AwareDatetime


class AgentConfigResponse(AgentContractModel):
    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    identity_status: AgentIdentityStatus
    production_eligible: bool
    identity: AgentIdentity | None = None
    config: ManagedAgentConfig
    server_time: AwareDatetime


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


__all__ = [
    "AgentConfigResponse",
    "AgentHeartbeatAck",
    "AgentHeartbeatRequest",
    "AgentRegistrationRequest",
    "AgentRegistrationResponse",
    "AgentRuntimeStatus",
    "ManagedAgentConfig",
    "utc_now",
]
