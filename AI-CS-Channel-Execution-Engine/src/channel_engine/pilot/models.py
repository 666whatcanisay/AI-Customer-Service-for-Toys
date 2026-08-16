from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


PDD_PILOT_CONTRACT_VERSION = "1.0"
PDD_PILOT_TARGET_STORE_NAME = "玩趣乐园积木店"


def _contains_sensitive_material(value: object) -> bool:
    forbidden_keys = ("cookie", "token", "password", "secret", "authorization")
    forbidden_values = (
        "cookie=",
        "token=",
        "password=",
        "secret=",
        "bearer ",
        "set-cookie",
    )
    if isinstance(value, dict):
        return any(
            any(marker in str(key).casefold() for marker in forbidden_keys)
            or _contains_sensitive_material(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_sensitive_material(item) for item in value)
    if isinstance(value, str):
        normalized = value.casefold()
        return any(marker in normalized for marker in forbidden_values)
    return False


class PilotModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    pilot_contract_version: Literal["1.0"] = PDD_PILOT_CONTRACT_VERSION


class PilotEnvironment(StrEnum):
    PILOT = "PILOT"


class PilotRuntimeState(StrEnum):
    INIT = "INIT"
    WAITING_FOR_LOGIN = "WAITING_FOR_LOGIN"
    VALIDATING = "VALIDATING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


class PilotBrowserStatus(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    CONNECTED = "CONNECTED"
    EXPIRED = "EXPIRED"
    DEGRADED = "DEGRADED"


class PilotStoreStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"


class PilotComponentStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class PilotSafetyStatus(StrEnum):
    PILOT_MODE = "PILOT_MODE"
    KILL_SWITCH = "KILL_SWITCH"


class PilotEvidenceType(StrEnum):
    STARTUP = "STARTUP"
    BROWSER_SESSION = "BROWSER_SESSION"
    STORE_BINDING = "STORE_BINDING"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    DECISION_CREATED = "DECISION_CREATED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    RECEIPT_RECORDED = "RECEIPT_RECORDED"
    SEND_BLOCKED = "SEND_BLOCKED"
    KILL_SWITCH_CHANGED = "KILL_SWITCH_CHANGED"
    LIVE_PREFLIGHT = "LIVE_PREFLIGHT"
    LIVE_STOPPED = "LIVE_STOPPED"
    LIVE_ACTIVATED = "LIVE_ACTIVATED"


class PilotStoreConfig(PilotModel):
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
    environment: Literal[PilotEnvironment.PILOT] = PilotEnvironment.PILOT
    credential_reference: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    send_limit: int = Field(default=1, ge=1, le=5)
    approval_required: Literal[True] = True
    auto_reply: Literal[False] = False


class PilotBrowserObservation(PilotModel):
    status: PilotBrowserStatus
    session_id: str | None = Field(default=None, max_length=128)
    checked_at: AwareDatetime
    human_login_required: bool
    real_browser_started: bool
    generation: int | None = Field(default=None, ge=1)
    page_revision: str | None = Field(default=None, max_length=128)
    selector_version: str | None = Field(default=None, max_length=128)
    failure_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_login_state(self) -> PilotBrowserObservation:
        if self.status is PilotBrowserStatus.CONNECTED and self.session_id is None:
            raise ValueError("connected Pilot browser requires session_id")
        if self.status is PilotBrowserStatus.CONNECTED and self.generation is None:
            raise ValueError("connected Pilot browser requires generation")
        if self.status in {
            PilotBrowserStatus.LOGIN_REQUIRED,
            PilotBrowserStatus.EXPIRED,
        } and not self.human_login_required:
            raise ValueError("login states require human action")
        return self


class PilotObservedStore(PilotModel):
    platform: Literal["pdd"] = "pdd"
    store_id: str = Field(min_length=1, max_length=128)
    store_name: str = Field(min_length=1, max_length=160)
    observed_at: AwareDatetime
    source: str = Field(min_length=1, max_length=128)


class PilotDashboard(PilotModel):
    node: Literal["ONLINE", "DEGRADED", "BLOCKED", "STOPPED"]
    runtime_state: PilotRuntimeState
    store_id: str
    store_name: str
    store_status: PilotStoreStatus
    browser: PilotBrowserStatus
    message: PilotComponentStatus
    ai: PilotComponentStatus
    channel: PilotComponentStatus
    safety: PilotSafetyStatus
    today_send: int = Field(ge=0)
    send_limit: int = Field(ge=1, le=5)
    approval_required: Literal[True] = True
    auto_reply: Literal[False] = False
    last_heartbeat: AwareDatetime | None = None
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


class PilotDecisionTrace(PilotModel):
    decision_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    context: dict[str, JsonValue] = Field(default_factory=dict)
    answer: str | None = Field(default=None, max_length=8_000)
    citations: tuple[JsonValue, ...] = ()
    risk_level: str | None = Field(default=None, max_length=64)
    action: str = Field(min_length=1, max_length=64)
    gateway_version: str = Field(min_length=1, max_length=128)
    decided_at: AwareDatetime


class PilotIntakeResult(PilotModel):
    conversation_id: str
    message_id: str
    external_message_id: str
    decision_id: str
    answer: str | None = None
    citations: tuple[JsonValue, ...] = ()
    risk_level: str | None = Field(default=None, max_length=64)
    decision_state: Literal["WAITING_APPROVAL"] = "WAITING_APPROVAL"
    requires_approval: Literal[True] = True


class PilotExecutionResult(PilotModel):
    decision_id: str
    approval_id: str
    execution_id: str
    execution_state: str
    receipt_id: str | None = None
    receipt_outcome: str | None = None
    customer_message_sent: bool = False


class PilotExecutionReservation(PilotModel):
    execution_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    send_day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reserved_at: AwareDatetime


class PilotEvidence(PilotModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=255)
    evidence_type: PilotEvidenceType
    store_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    recorded_at: AwareDatetime

    @field_validator("idempotency_key", "store_id", "correlation_id")
    @classmethod
    def reject_sensitive_text(cls, value: str) -> str:
        if _contains_sensitive_material(value):
            raise ValueError("Pilot evidence contains sensitive material")
        return value

    @model_validator(mode="after")
    def reject_sensitive_payload(self) -> PilotEvidence:
        if _contains_sensitive_material(self.payload):
            raise ValueError("Pilot evidence payload contains sensitive material")
        return self


__all__ = [
    "PDD_PILOT_CONTRACT_VERSION",
    "PDD_PILOT_TARGET_STORE_NAME",
    "PilotBrowserObservation",
    "PilotBrowserStatus",
    "PilotComponentStatus",
    "PilotDashboard",
    "PilotDecisionTrace",
    "PilotEnvironment",
    "PilotEvidence",
    "PilotEvidenceType",
    "PilotExecutionReservation",
    "PilotExecutionResult",
    "PilotIntakeResult",
    "PilotModel",
    "PilotObservedStore",
    "PilotRuntimeState",
    "PilotSafetyStatus",
    "PilotStoreConfig",
    "PilotStoreStatus",
]
