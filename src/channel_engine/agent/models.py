from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


CHANNEL_AGENT_CONTRACT_VERSION = "1.0"


class AgentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_contract_version: Literal["1.0"] = CHANNEL_AGENT_CONTRACT_VERSION


class AgentNodeStatus(StrEnum):
    INIT = "INIT"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


class AgentServerConnection(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"


class AgentEnvironment(StrEnum):
    MOCK = "MOCK"
    STAGING = "STAGING"
    PILOT = "PILOT"
    PRODUCTION = "PRODUCTION"


class AgentComponentStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


class StoreBindingStatus(StrEnum):
    BOUND = "BOUND"
    SUSPENDED = "SUSPENDED"


class AgentStoreStatus(StrEnum):
    BOUND = "BOUND"
    UNBOUND = "UNBOUND"
    SUSPENDED = "SUSPENDED"


class StoreBinding(AgentModel):
    platform: Literal["pdd"] = "pdd"
    store_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    store_name: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    credential_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    status: StoreBindingStatus = StoreBindingStatus.BOUND


class AgentComponentHealth(AgentModel):
    component: Literal["server", "browser", "channel"]
    status: AgentComponentStatus
    checked_at: AwareDatetime
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


class AgentNode(AgentModel):
    node_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    node_name: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    status: AgentNodeStatus
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$",
    )
    last_heartbeat: AwareDatetime | None = None
    server_connection: AgentServerConnection
    environment: AgentEnvironment


class AgentStatusView(AgentModel):
    node: AgentNode
    server_status: AgentComponentHealth
    browser_status: AgentComponentHealth
    channel_status: AgentComponentHealth
    store_status: AgentStoreStatus
    store_id: str | None = Field(default=None, max_length=128)
    store_name: str | None = Field(default=None, max_length=160)
    dry_run: bool
    kill_switch: bool
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_store_view(self) -> AgentStatusView:
        if self.store_status is AgentStoreStatus.UNBOUND:
            if self.store_id is not None or self.store_name is not None:
                raise ValueError("unbound store status cannot expose store identity")
        elif self.store_id is None or self.store_name is None:
            raise ValueError("bound store status requires store identity")
        return self


class AgentHealth(AgentModel):
    status: Literal["healthy", "degraded", "offline", "stopped"]
    ready: bool
    node_status: AgentNodeStatus
    checked_at: AwareDatetime
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


class AgentLifecycleStage(StrEnum):
    ENVIRONMENT_CHECK = "ENVIRONMENT_CHECK"
    SERVER_CONNECT = "SERVER_CONNECT"
    CONFIG_LOAD = "CONFIG_LOAD"
    BROWSER_CHECK = "BROWSER_CHECK"
    CHANNEL_CHECK = "CHANNEL_CHECK"
    READY = "READY"
    STOP = "STOP"


class AgentLifecycleEvent(AgentModel):
    sequence: int = Field(ge=1)
    stage: AgentLifecycleStage
    occurred_at: AwareDatetime
    successful: bool
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


__all__ = [
    "CHANNEL_AGENT_CONTRACT_VERSION",
    "AgentComponentHealth",
    "AgentComponentStatus",
    "AgentEnvironment",
    "AgentHealth",
    "AgentLifecycleEvent",
    "AgentLifecycleStage",
    "AgentModel",
    "AgentNode",
    "AgentNodeStatus",
    "AgentServerConnection",
    "AgentStatusView",
    "AgentStoreStatus",
    "StoreBinding",
    "StoreBindingStatus",
]
