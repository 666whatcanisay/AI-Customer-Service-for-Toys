from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


AGENT_VERSION = "1.0.0-rc.2"


class ExitCode(IntEnum):
    NORMAL = 0
    CONFIG_ERROR = 1
    GATEWAY_UNREACHABLE = 2
    AUTHENTICATION_FAILED = 3
    RUNTIME_ERROR = 4
    BROWSER_ERROR = 5


class AgentStatus(StrEnum):
    INIT = "INIT"
    STARTING = "STARTING"
    READY = "READY"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class FirstLaunchState(StrEnum):
    FIRST_START = "FIRST_START"
    CHECKING_ENVIRONMENT = "CHECKING_ENVIRONMENT"
    CONNECTING_SERVER = "CONNECTING_SERVER"
    CONFIGURING_IDENTITY = "CONFIGURING_IDENTITY"
    CHECKING_BROWSER = "CHECKING_BROWSER"
    INITIALIZING_PROFILE = "INITIALIZING_PROFILE"
    READY = "READY"
    FAILED = "FAILED"


class ComponentStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    EXPIRED = "EXPIRED"
    RECOVERING = "RECOVERING"
    DISCONNECTED = "DISCONNECTED"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    status: ComponentStatus
    reason_code: str
    checked_at: str = field(default_factory=utc_now_text)
    details: dict[str, str | int | bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeState:
    schema_version: str = "1.0"
    agent_version: str = AGENT_VERSION
    agent_status: AgentStatus = AgentStatus.INIT
    first_launch_state: FirstLaunchState = FirstLaunchState.FIRST_START
    pid: int | None = None
    started_at: str | None = None
    updated_at: str = field(default_factory=utc_now_text)
    stopped_at: str | None = None
    node_id: str | None = None
    exit_code: int = int(ExitCode.NORMAL)
    config: dict[str, Any] = field(default_factory=dict)
    gateway: dict[str, Any] = field(default_factory=dict)
    browser: dict[str, Any] = field(default_factory=dict)
    session: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(
        default_factory=lambda: {
            "kill_switch": True,
            "manual_approval": True,
            "auto_reply": False,
        }
    )
    last_error: dict[str, str] | None = None
    recovery_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["agent_status"] = self.agent_status.value
        value["first_launch_state"] = self.first_launch_state.value
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RuntimeState":
        return cls(
            schema_version=str(value.get("schema_version", "1.0")),
            agent_version=str(value.get("agent_version", AGENT_VERSION)),
            agent_status=AgentStatus(value.get("agent_status", "INIT")),
            first_launch_state=FirstLaunchState(
                value.get("first_launch_state", "FIRST_START")
            ),
            pid=value.get("pid"),
            started_at=value.get("started_at"),
            updated_at=str(value.get("updated_at", utc_now_text())),
            stopped_at=value.get("stopped_at"),
            node_id=value.get("node_id"),
            exit_code=_read_exit_code(value.get("exit_code", ExitCode.NORMAL)),
            config=dict(value.get("config") or {}),
            gateway=dict(value.get("gateway") or {}),
            browser=dict(value.get("browser") or {}),
            session=dict(value.get("session") or {}),
            safety=dict(value.get("safety") or {}),
            last_error=value.get("last_error"),
            recovery_count=int(value.get("recovery_count", 0)),
        )


def _read_exit_code(value: object) -> int:
    try:
        return int(ExitCode(int(value)))
    except (TypeError, ValueError):
        return int(ExitCode.RUNTIME_ERROR)
