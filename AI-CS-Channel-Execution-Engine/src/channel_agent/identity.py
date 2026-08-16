from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .version import AGENT_PROTOCOL_VERSION


_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$"


class AgentIdentityStatus(StrEnum):
    REGISTERED = "REGISTERED"
    # Source compatibility only.  The V2 wire representation is always
    # REGISTERED; UNBOUND is accepted as a legacy input by ``_missing_``.
    UNBOUND = "REGISTERED"
    BOUND = "BOUND"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"

    @classmethod
    def _missing_(cls, value: object) -> "AgentIdentityStatus | None":
        if value == "UNBOUND":
            return cls.REGISTERED
        return None


class AgentConnectivityStatus(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class AgentOnlineStatus(StrEnum):
    """Deprecated V1 display enum; never persisted by Host Control V2."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class AgentIdentityModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION


class AgentIdentity(AgentIdentityModel):
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    store_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    authorized_store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    active_store_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    status: AgentIdentityStatus
    binding_revision: int = Field(default=0, ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("store_ids", "authorized_store_ids")
    @classmethod
    def validate_store_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("store references must be unique")
        return value

    @model_validator(mode="after")
    def validate_binding_shape(self) -> "AgentIdentity":
        has_user = self.user_id is not None
        has_store = self.store_id is not None
        if self.store_ids and self.store_id != self.store_ids[0]:
            raise ValueError("primary store must match the first store reference")
        if (
            self.authorized_store_ids
            and self.store_ids
            and self.authorized_store_ids != self.store_ids
        ):
            raise ValueError("authorized stores must match legacy store references")
        authorized = self.authorized_stores
        if self.active_store_id is not None and self.active_store_id not in authorized:
            raise ValueError("active store must be authorized")
        if has_user != has_store:
            raise ValueError("user and store references must be present together")
        if self.status in {AgentIdentityStatus.BOUND, AgentIdentityStatus.ACTIVE}:
            if not has_user:
                raise ValueError("bound identity requires user and store references")
        elif has_user or self.store_ids:
            raise ValueError("unbound or disabled identity cannot retain references")
        if self.updated_at < self.created_at:
            raise ValueError("identity update time cannot precede creation")
        return self

    @property
    def production_eligible(self) -> bool:
        return self.status is AgentIdentityStatus.ACTIVE

    @property
    def effective_store_ids(self) -> tuple[str, ...]:
        if self.authorized_store_ids:
            return self.authorized_store_ids
        if self.store_ids:
            return self.store_ids
        return (self.store_id,) if self.store_id is not None else ()

    @property
    def authorized_stores(self) -> tuple[str, ...]:
        return self.effective_store_ids

    @property
    def effective_active_store_id(self) -> str | None:
        if self.active_store_id is not None:
            return self.active_store_id
        if self.authorized_store_ids:
            return None
        return self.store_id


class AgentIdentityBindingRequest(AgentIdentityModel):
    user_reference: str = Field(pattern=_REFERENCE_PATTERN)
    store_reference: str = Field(pattern=_REFERENCE_PATTERN)
    reason: str = Field(min_length=1, max_length=512)


class AgentIdentityActivationRequest(AgentIdentityModel):
    reason: str = Field(min_length=1, max_length=512)


class AgentIdentityRestoreRequest(AgentIdentityModel):
    reason: str = Field(min_length=1, max_length=512)
    confirmation_phrase: Literal["确认恢复为待绑定"]


class AgentIdentityAuditAction(StrEnum):
    BIND = "BIND"
    ENROLL = "ENROLL"
    ACTIVATE = "ACTIVATE"
    STORES_UPDATE = "STORES_UPDATE"
    ACTIVE_STORE_SELECT = "ACTIVE_STORE_SELECT"
    UNBIND = "UNBIND"
    DISABLE = "DISABLE"
    RESTORE_TO_REGISTERED = "RESTORE_TO_REGISTERED"


class AgentIdentityAuditState(AgentIdentityModel):
    status: AgentIdentityStatus
    user_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    store_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    authorized_store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    active_store_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    binding_revision: int = Field(default=0, ge=0)


class AgentIdentityAuditEvent(AgentIdentityModel):
    audit_event_id: str = Field(min_length=1, max_length=192)
    agent_id: str = Field(min_length=1, max_length=128)
    operator_id: str = Field(min_length=1, max_length=160)
    action: AgentIdentityAuditAction
    timestamp: AwareDatetime
    reason: str = Field(min_length=1, max_length=512)
    before: AgentIdentityAuditState
    after: AgentIdentityAuditState


class AgentAdminView(AgentIdentityModel):
    identity: AgentIdentity
    identity_status: AgentIdentityStatus
    connectivity_status: AgentConnectivityStatus
    agent_version: str | None = Field(default=None, min_length=1, max_length=64)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    runtime_status: str = Field(min_length=1, max_length=64)
    last_heartbeat: AwareDatetime | None = None
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"] = (
        "CHANNEL_ENGINE_HOST_CONTROL"
    )

    @model_validator(mode="after")
    def validate_status_projection(self) -> "AgentAdminView":
        if self.identity_status is not self.identity.status:
            raise ValueError("identity status projection must match authoritative identity")
        return self

    @property
    def online_status(self) -> AgentOnlineStatus:
        """V1 Python compatibility; deliberately absent from V2 JSON."""

        return AgentOnlineStatus(self.connectivity_status.value)


class AgentAdminListResponse(AgentIdentityModel):
    items: tuple[AgentAdminView, ...]
    count: int = Field(ge=0)
    server_time: AwareDatetime
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"] = (
        "CHANNEL_ENGINE_HOST_CONTROL"
    )


class AgentIdentityAuditListResponse(AgentIdentityModel):
    items: tuple[AgentIdentityAuditEvent, ...]
    count: int = Field(ge=0)
    server_time: AwareDatetime


__all__ = [
    "AgentAdminListResponse",
    "AgentAdminView",
    "AgentIdentity",
    "AgentIdentityActivationRequest",
    "AgentIdentityAuditAction",
    "AgentIdentityAuditEvent",
    "AgentIdentityAuditListResponse",
    "AgentIdentityAuditState",
    "AgentIdentityBindingRequest",
    "AgentIdentityRestoreRequest",
    "AgentIdentityStatus",
    "AgentConnectivityStatus",
    "AgentOnlineStatus",
]
