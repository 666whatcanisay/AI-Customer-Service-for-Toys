"""Strict AI-CS Customer Desktop Workflow V1 wire models."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


DESKTOP_WORKFLOW_SCHEMA_VERSION = "ai-cs.customer-desktop-workflow.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReplyPolicyMode(StrEnum):
    MANUAL_CONFIRM = "MANUAL_CONFIRM"
    AUTO_LOW_RISK = "AUTO_LOW_RISK"


class UpstreamReplyPolicy(StrictModel):
    store_id: str = Field(min_length=1, max_length=160)
    mode: ReplyPolicyMode
    revision: int = Field(ge=1)
    updated_by: str = Field(min_length=1, max_length=160)
    updated_at: AwareDatetime


class UpstreamExecutionPreparation(StrictModel):
    preparation_version: Literal["1.0"]
    preparation_id: str = Field(pattern=r"^execution-preparation:[a-f0-9]{64}$")
    decision_id: str = Field(min_length=1, max_length=160)
    trace_id: str = Field(pattern=r"^trace:[a-f0-9]{64}$")
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_revision: int = Field(ge=1)
    policy_mode: ReplyPolicyMode
    policy_revision: int = Field(ge=1)
    authorization_kind: Literal["HUMAN", "AUTO_POLICY"]
    authorized_by: str = Field(min_length=1, max_length=160)
    state: Literal["READY", "INVALIDATED", "EXPIRED", "CONSUMED"]
    prepared_at: AwareDatetime
    expires_at: AwareDatetime
    real_send_enabled: Literal[False]
    external_side_effect: Literal[False]


class AgentIdentityStatus(StrEnum):
    REGISTERED = "REGISTERED"
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


class DesktopBindingActivationRequest(StrictModel):
    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
    device_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
    store_id: int = Field(ge=1)


class DesktopActiveStoreSelectionRequest(StrictModel):
    agent_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
    device_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
    store_id: int = Field(ge=1)
    platform: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    observed_platform_store_id: str = Field(min_length=1, max_length=96)
    human_confirmed: Literal[True]


class DesktopWorkflowAuditProjection(StrictModel):
    audit_event_id: str
    actor_user_id: str
    event_type: str
    agent_id: str | None
    device_id: str | None
    store_id: int | None
    previous_state: str | None
    current_state: str
    reason: str | None = None
    outcome: str
    occurred_at: datetime


class DesktopWorkflowAuditListResponse(StrictModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"] = DESKTOP_WORKFLOW_SCHEMA_VERSION
    items: list[DesktopWorkflowAuditProjection]
    total: int = Field(ge=0)


class AdminDeviceProjection(StrictModel):
    agent_id: str
    device_id: str
    agent_version: str | None = None
    hostname: str | None = None
    identity_status: AgentIdentityStatus
    connectivity_status: AgentConnectivityStatus
    runtime_status: str
    user_reference: str | None = None
    authorized_store_ids: tuple[str, ...] = ()
    active_store_id: str | None = None
    binding_revision: int = Field(ge=0)
    last_heartbeat: AwareDatetime | None = None
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"]


class AdminDeviceListResponse(StrictModel):
    items: tuple[AdminDeviceProjection, ...]
    count: int = Field(ge=0)
    checked_at: AwareDatetime
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"]


class AdminDeviceDisableRequest(StrictModel):
    reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认禁用设备"]


class AdminDeviceRestoreRequest(StrictModel):
    reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认恢复为待绑定"]


class AdminHostPairingCodeRotateRequest(StrictModel):
    reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认重新生成主机连接码"]


class AdminHostPairingCodeRotateResponse(StrictModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"] = DESKTOP_WORKFLOW_SCHEMA_VERSION
    host_id: str = Field(min_length=1, max_length=128)
    pairing_code: str = Field(pattern=r"^[0-9A-HJ-NP-TV-Z]{12}$", repr=False)
    expires_at: AwareDatetime
    display_once: Literal[True] = True


class AdminBindingTargetStore(StrictModel):
    store_id: int = Field(ge=1)
    store_code: str = Field(min_length=1, max_length=96)
    store_name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=64)
    is_default: bool


class AdminBindingTarget(StrictModel):
    user_id: str = Field(min_length=36, max_length=36)
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    stores: tuple[AdminBindingTargetStore, ...]


class AdminBindingTargetListResponse(StrictModel):
    items: tuple[AdminBindingTarget, ...]
    count: int = Field(ge=0)
    checked_at: AwareDatetime


class AdminEnrollmentGrantRequest(StrictModel):
    user_id: str = Field(min_length=36, max_length=36)
    store_ids: tuple[int, ...] = Field(min_length=1)
    reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认生成设备绑定许可"]

    @field_validator("store_ids")
    @classmethod
    def unique_store_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("store_ids must be unique")
        if any(store_id < 1 for store_id in value):
            raise ValueError("store_ids must be positive")
        return value


class AdminEnrollmentGrantResponse(StrictModel):
    schema_version: Literal["ai-cs.customer-desktop-workflow.v1"] = DESKTOP_WORKFLOW_SCHEMA_VERSION
    grant_id: str = Field(min_length=1, max_length=192)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_reference: str = Field(min_length=36, max_length=36)
    store_references: tuple[str, ...] = Field(min_length=1)
    binding_code: str = Field(pattern=r"^[A-F0-9]{32}$", repr=False)
    issued_at: AwareDatetime
    expires_at: AwareDatetime


class UpstreamAgentIdentity(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    agent_id: str
    device_id: str
    user_id: str | None
    store_id: str | None
    store_ids: tuple[str, ...] = ()
    authorized_store_ids: tuple[str, ...] = ()
    active_store_id: str | None = None
    status: AgentIdentityStatus
    binding_revision: int = Field(ge=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("store_ids", "authorized_store_ids")
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
        if (
            self.authorized_store_ids
            and self.store_ids
            and self.authorized_store_ids != self.store_ids
        ):
            raise ValueError("authorized Store references are inconsistent")
        if self.active_store_id is not None and self.active_store_id not in stores:
            raise ValueError("active Store reference is not authorized")
        has_user = self.user_id is not None
        has_store = self.store_id is not None
        if has_user != has_store:
            raise ValueError("user and Store references must be present together")
        if self.status in {AgentIdentityStatus.BOUND, AgentIdentityStatus.ACTIVE} and not has_user:
            raise ValueError("bound identity is incomplete")
        if self.status in {AgentIdentityStatus.UNBOUND, AgentIdentityStatus.DISABLED} and (
            has_user or self.store_ids or self.authorized_store_ids or self.active_store_id
        ):
            raise ValueError("unbound identity retains references")
        if self.updated_at < self.created_at:
            raise ValueError("identity timestamps are inconsistent")
        return self

    @property
    def effective_store_ids(self) -> tuple[str, ...]:
        if self.authorized_store_ids:
            return self.authorized_store_ids
        return self.store_ids or ((self.store_id,) if self.store_id else ())

    @property
    def effective_active_store_id(self) -> str | None:
        if self.active_store_id is not None:
            return self.active_store_id
        if self.authorized_store_ids:
            return None
        return self.store_id


class UpstreamHostPairingCode(StrictModel):
    control_protocol_version: Literal["2.1"] = "2.1"
    host_id: str = Field(min_length=1, max_length=128)
    pairing_code: str = Field(pattern=r"^[0-9A-HJ-NP-TV-Z]{12}$", repr=False)
    expires_at: AwareDatetime
    display_once: Literal[True] = True


class UpstreamAgentView(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    identity: UpstreamAgentIdentity
    identity_status: AgentIdentityStatus
    connectivity_status: AgentConnectivityStatus
    agent_version: str | None = None
    hostname: str | None = None
    runtime_status: str
    last_heartbeat: AwareDatetime | None = None
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"]

    @model_validator(mode="after")
    def status_projection_matches(self) -> "UpstreamAgentView":
        if self.identity_status is not self.identity.status:
            raise ValueError("identity status projection is inconsistent")
        return self


class UpstreamAgentList(StrictModel):
    protocol_version: Literal["1.0"] = "1.0"
    items: tuple[UpstreamAgentView, ...]
    count: int = Field(ge=0)
    server_time: AwareDatetime
    authoritative_source: Literal["CHANNEL_ENGINE_HOST_CONTROL"]

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
