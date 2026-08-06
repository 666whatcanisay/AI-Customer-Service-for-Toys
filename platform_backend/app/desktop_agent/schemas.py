"""Strict AI-CS Customer Desktop Workflow V1 wire models."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


DESKTOP_WORKFLOW_SCHEMA_VERSION = "ai-cs.customer-desktop-workflow.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentIdentityStatus(StrEnum):
    UNBOUND = "UNBOUND"
    BOUND = "BOUND"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class AgentOnlineStatus(StrEnum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class DesktopAssociationState(StrEnum):
    READY = "READY"
    BINDING_REQUIRED = "BINDING_REQUIRED"
    ACTIVATION_REQUIRED = "ACTIVATION_REQUIRED"
    STORE_MISMATCH = "STORE_MISMATCH"
    MULTIPLE_MATCHES = "MULTIPLE_MATCHES"
    DISABLED = "DISABLED"


class DesktopAgentProjection(StrictModel):
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    device_name: str | None = Field(default=None, max_length=255)
    agent_version: str | None = Field(default=None, max_length=64)
    identity_status: AgentIdentityStatus
    online_status: AgentOnlineStatus
    runtime_status: str = Field(min_length=1, max_length=64)
    production_eligible: bool
    binding_revision: int = Field(ge=0)
    last_heartbeat: datetime | None


class DesktopAgentStatusResponse(StrictModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"] = DESKTOP_WORKFLOW_SCHEMA_VERSION
    user_id: str = Field(min_length=36, max_length=36)
    store_id: int = Field(ge=1)
    store_code: str = Field(min_length=1, max_length=96)
    association_state: DesktopAssociationState
    agent: DesktopAgentProjection | None
    checked_at: datetime


class DesktopBindingGrantRequest(StrictModel):
    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
    device_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
    store_id: int = Field(ge=1)


class DesktopBindingGrantResponse(StrictModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"] = DESKTOP_WORKFLOW_SCHEMA_VERSION
    grant_id: str = Field(min_length=1, max_length=192)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    binding_code: str = Field(pattern=r"^[A-F0-9]{32}$", repr=False)
    expires_at: datetime


class DesktopWorkflowAuditProjection(StrictModel):
    audit_event_id: str
    actor_user_id: str
    event_type: str
    agent_id: str | None
    device_id: str | None
    store_id: int | None
    previous_state: str | None
    current_state: str
    outcome: str
    occurred_at: datetime


class DesktopWorkflowAuditListResponse(StrictModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"] = DESKTOP_WORKFLOW_SCHEMA_VERSION
    items: list[DesktopWorkflowAuditProjection]
    total: int = Field(ge=0)


class UpstreamAgentIdentity(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    agent_id: str
    device_id: str
    user_id: str | None
    store_id: str | None
    store_ids: tuple[str, ...] = ()
    status: AgentIdentityStatus
    binding_revision: int = Field(ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("store_ids")
    @classmethod
    def unique_store_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("store references must be unique")
        return value

    @model_validator(mode="after")
    def valid_binding_shape(self) -> "UpstreamAgentIdentity":
        stores = self.effective_store_ids
        if self.store_ids and self.store_id != self.store_ids[0]:
            raise ValueError("primary Store reference is inconsistent")
        has_binding = self.user_id is not None and bool(stores)
        if (self.user_id is None) != (not stores):
            raise ValueError("user and Store references must be present together")
        if self.status in {AgentIdentityStatus.BOUND, AgentIdentityStatus.ACTIVE} and not has_binding:
            raise ValueError("bound identity is incomplete")
        if self.status in {AgentIdentityStatus.UNBOUND, AgentIdentityStatus.DISABLED} and has_binding:
            raise ValueError("unbound identity retains references")
        if self.updated_at < self.created_at:
            raise ValueError("identity timestamps are inconsistent")
        return self

    @property
    def effective_store_ids(self) -> tuple[str, ...]:
        return self.store_ids or ((self.store_id,) if self.store_id else ())


class UpstreamAgentView(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    identity: UpstreamAgentIdentity
    online_status: AgentOnlineStatus
    agent_version: str | None = None
    hostname: str | None = None
    runtime_status: str
    last_heartbeat: AwareDatetime | None = None


class UpstreamAgentList(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    items: tuple[UpstreamAgentView, ...]
    count: int = Field(ge=0)
    server_time: AwareDatetime

    @model_validator(mode="after")
    def count_matches_items(self) -> "UpstreamAgentList":
        if self.count != len(self.items):
            raise ValueError("Agent count does not match items")
        return self


class UpstreamEnrollmentGrant(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    grant_id: str
    agent_id: str
    device_id: str
    user_reference: str
    store_references: tuple[str, ...]
    binding_code: str = Field(pattern=r"^[A-F0-9]{32}$", repr=False)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
