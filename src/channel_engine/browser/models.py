from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


BROWSER_ADAPTER_CONTRACT_VERSION = "1.0"


class BrowserModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    browser_contract_version: Literal["1.0"] = BROWSER_ADAPTER_CONTRACT_VERSION


class ChromeLaunchStrategy(StrEnum):
    SYSTEM_CHROME_PERSISTENT_CONTEXT = "SYSTEM_CHROME_PERSISTENT_CONTEXT"
    PLAYWRIGHT_MANAGED_CHROMIUM = "PLAYWRIGHT_MANAGED_CHROMIUM"
    CDP_ATTACH_EXISTING = "CDP_ATTACH_EXISTING"
    MOCK = "MOCK"


class BrowserSessionState(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    CRASHED = "CRASHED"
    RECOVERING = "RECOVERING"
    EXPIRED = "EXPIRED"
    STOPPED = "STOPPED"


class BrowserLoginState(StrEnum):
    UNKNOWN = "UNKNOWN"
    AUTHENTICATED = "AUTHENTICATED"
    REQUIRED = "REQUIRED"
    EXPIRED = "EXPIRED"


class BrowserHeartbeatState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRASHED = "CRASHED"


class ProfileIsolationMode(StrEnum):
    DEDICATED_PER_ACCOUNT = "DEDICATED_PER_ACCOUNT"


class BrowserProfileReference(BrowserModel):
    profile_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    account_ref: str = Field(min_length=1, max_length=128)
    storage_reference: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^profile-ref://[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$",
    )
    isolation_mode: Literal[ProfileIsolationMode.DEDICATED_PER_ACCOUNT] = (
        ProfileIsolationMode.DEDICATED_PER_ACCOUNT
    )


class BrowserPageContext(BrowserModel):
    page_context_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    generation: int = Field(ge=1)
    platform: Literal["pdd"] = "pdd"
    page: Literal["merchant_chat"] = "merchant_chat"
    selector_contract_version: str = Field(min_length=1, max_length=64)
    page_revision: str | None = Field(default=None, max_length=128)
    created_at: AwareDatetime


class BrowserSession(BrowserModel):
    session_id: str = Field(min_length=1, max_length=128)
    account_ref: str = Field(min_length=1, max_length=128)
    profile: BrowserProfileReference
    launch_strategy: ChromeLaunchStrategy
    state: BrowserSessionState
    login_state: BrowserLoginState
    generation: int = Field(ge=0)
    page_context: BrowserPageContext | None = None
    started_at: AwareDatetime | None = None
    last_heartbeat_at: AwareDatetime | None = None
    stopped_at: AwareDatetime | None = None
    failure_code: str | None = Field(default=None, max_length=128)
    human_takeover_required: bool = False

    @model_validator(mode="after")
    def validate_state(self) -> BrowserSession:
        if self.profile.account_ref != self.account_ref:
            raise ValueError("browser profile account does not match session")
        if self.state is BrowserSessionState.ACTIVE:
            if (
                self.login_state is not BrowserLoginState.AUTHENTICATED
                or self.page_context is None
                or self.started_at is None
            ):
                raise ValueError("ACTIVE browser session requires login and page context")
        if self.state in {
            BrowserSessionState.LOGIN_REQUIRED,
            BrowserSessionState.EXPIRED,
        } and not self.human_takeover_required:
            raise ValueError("login failure states require human takeover")
        if self.state is BrowserSessionState.STOPPED and self.stopped_at is None:
            raise ValueError("STOPPED browser session requires stopped_at")
        return self


class BrowserHeartbeat(BrowserModel):
    session_id: str
    state: BrowserHeartbeatState
    login_state: BrowserLoginState
    page_available: bool
    page_revision: str | None = Field(default=None, max_length=128)
    checked_at: AwareDatetime
    failure_code: str | None = Field(default=None, max_length=128)


__all__ = [
    "BROWSER_ADAPTER_CONTRACT_VERSION",
    "BrowserHeartbeat",
    "BrowserHeartbeatState",
    "BrowserLoginState",
    "BrowserModel",
    "BrowserPageContext",
    "BrowserProfileReference",
    "BrowserSession",
    "BrowserSessionState",
    "ChromeLaunchStrategy",
    "ProfileIsolationMode",
]
