from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from threading import Lock
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.models.entities import new_id, utc_now


class LifecycleModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ChannelConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"


class ChannelAuthenticationScheme(StrEnum):
    API_TOKEN = "API_TOKEN"
    OAUTH2 = "OAUTH2"
    SIGNED_REQUEST = "SIGNED_REQUEST"
    MANAGED_SESSION = "MANAGED_SESSION"


class HeartbeatStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class ChannelCredentialReference(LifecycleModel):
    """Non-secret locator resolved by an external credential broker."""

    credential_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$",
    )
    provider: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
    )
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )
    account_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[^\r\n]+$",
    )
    auth_scheme: ChannelAuthenticationScheme


class ChannelAuthentication(LifecycleModel):
    """Sanitized authentication result; it never contains token/cookie/secret."""

    principal_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[^\r\n]+$",
    )
    account_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[^\r\n]+$",
    )
    credential_id: str = Field(min_length=1, max_length=128)
    credential_version: str = Field(min_length=1, max_length=64)
    auth_scheme: ChannelAuthenticationScheme
    authenticated_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self) -> ChannelAuthentication:
        if self.expires_at <= self.authenticated_at:
            raise ValueError("channel authentication expiry must follow authentication")
        return self


class ChannelSession(LifecycleModel):
    """Opaque, log-safe session metadata exposed to the engine."""

    session_id: str = Field(min_length=1, max_length=128)
    connection_id: str = Field(min_length=1, max_length=128)
    channel: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$",
    )
    account_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[^\r\n]+$",
    )
    principal_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[^\r\n]+$",
    )
    credential_id: str = Field(min_length=1, max_length=128)
    credential_version: str = Field(min_length=1, max_length=64)
    established_at: AwareDatetime
    expires_at: AwareDatetime
    last_heartbeat_at: AwareDatetime | None = None
    authenticated: bool = True

    @model_validator(mode="after")
    def validate_window(self) -> ChannelSession:
        if self.expires_at <= self.established_at:
            raise ValueError("channel session expiry must follow establishment")
        return self


class ChannelConnection(LifecycleModel):
    connection_id: str = Field(min_length=1, max_length=128)
    channel: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$",
    )
    account_ref: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[^\r\n]+$",
    )
    state: ChannelConnectionState
    connected_at: AwareDatetime | None = None
    last_heartbeat_at: AwareDatetime | None = None
    failure_code: str | None = Field(default=None, max_length=128)
    real_platform_connected: bool


class ChannelHeartbeat(LifecycleModel):
    connection_id: str
    session_id: str
    status: HeartbeatStatus
    checked_at: AwareDatetime
    next_check_after_seconds: int = Field(ge=1, le=300)
    failure_code: str | None = Field(default=None, max_length=128)
    real_platform_contacted: bool


class ChannelLifecycleError(RuntimeError):
    pass


class ChannelAuthenticationFailed(ChannelLifecycleError):
    pass


class ChannelSessionUnavailable(ChannelLifecycleError):
    pass


@runtime_checkable
class ChannelAuthenticationBroker(Protocol):
    def authenticate(
        self,
        channel: str,
        credential: ChannelCredentialReference,
    ) -> ChannelAuthentication:
        """Authenticate through a secret broker without returning secret material."""


@runtime_checkable
class ChannelHeartbeatProbe(Protocol):
    def probe(self, session: ChannelSession) -> bool:
        """Return whether the sanitized session remains usable."""


class ChannelLifecycleManager:
    """Thread-safe lifecycle state machine shared by future real adapters."""

    def __init__(
        self,
        channel: str,
        credential: ChannelCredentialReference,
        authentication_broker: ChannelAuthenticationBroker,
        heartbeat_probe: ChannelHeartbeatProbe,
        *,
        clock: Callable[[], datetime] = utc_now,
        real_platform_connection: bool = False,
    ) -> None:
        if credential.account_ref.strip() != credential.account_ref:
            raise ValueError("account_ref cannot contain surrounding whitespace")
        self.channel = channel
        self.credential = credential
        self._authentication_broker = authentication_broker
        self._heartbeat_probe = heartbeat_probe
        self._clock = clock
        self._real_platform_connection = real_platform_connection
        self._lock = Lock()
        self._session: ChannelSession | None = None
        self._connection = ChannelConnection(
            connection_id=new_id("channel-connection"),
            channel=channel,
            account_ref=credential.account_ref,
            state=ChannelConnectionState.DISCONNECTED,
            real_platform_connected=False,
        )
        self._transition_history = [ChannelConnectionState.DISCONNECTED]

    @property
    def connection(self) -> ChannelConnection:
        with self._lock:
            return self._connection

    @property
    def transition_history(self) -> tuple[ChannelConnectionState, ...]:
        with self._lock:
            return tuple(self._transition_history)

    def connect(self) -> ChannelSession:
        with self._lock:
            if self._session is not None and self._connection.state in {
                ChannelConnectionState.CONNECTED,
                ChannelConnectionState.DEGRADED,
            }:
                return self._session
            self._transition(ChannelConnectionState.CONNECTING)
            self._transition(ChannelConnectionState.AUTHENTICATING)
            try:
                authentication = self._authentication_broker.authenticate(
                    self.channel,
                    self.credential,
                )
            except Exception as exc:
                self._transition(
                    ChannelConnectionState.AUTHENTICATION_FAILED,
                    failure_code="CHANNEL_AUTHENTICATION_FAILED",
                )
                raise ChannelAuthenticationFailed(
                    "channel credential broker rejected authentication"
                ) from exc
            if (
                authentication.account_ref != self.credential.account_ref
                or authentication.credential_id != self.credential.credential_id
                or authentication.credential_version != self.credential.version
                or authentication.auth_scheme is not self.credential.auth_scheme
            ):
                self._transition(
                    ChannelConnectionState.AUTHENTICATION_FAILED,
                    failure_code="CHANNEL_AUTHENTICATION_IDENTITY_MISMATCH",
                )
                raise ChannelAuthenticationFailed(
                    "channel authentication identity did not match credential reference"
                )
            now = self._clock()
            if authentication.expires_at <= now:
                self._transition(
                    ChannelConnectionState.AUTHENTICATION_FAILED,
                    failure_code="CHANNEL_AUTHENTICATION_EXPIRED",
                )
                raise ChannelAuthenticationFailed(
                    "channel authentication was already expired"
                )
            session = ChannelSession(
                session_id=new_id("channel-session"),
                connection_id=self._connection.connection_id,
                channel=self.channel,
                account_ref=authentication.account_ref,
                principal_ref=authentication.principal_ref,
                credential_id=authentication.credential_id,
                credential_version=authentication.credential_version,
                established_at=now,
                expires_at=authentication.expires_at,
                authenticated=True,
            )
            self._session = session
            self._transition(
                ChannelConnectionState.CONNECTED,
                connected_at=now,
                real_platform_connected=self._real_platform_connection,
            )
            return session

    def heartbeat(self, *, next_check_after_seconds: int = 30) -> ChannelHeartbeat:
        with self._lock:
            session = self._session
            if session is None or self._connection.state not in {
                ChannelConnectionState.CONNECTED,
                ChannelConnectionState.DEGRADED,
            }:
                raise ChannelSessionUnavailable("channel session is not connected")
            now = self._clock()
            if session.expires_at <= now:
                self._transition(
                    ChannelConnectionState.DEGRADED,
                    last_heartbeat_at=now,
                    failure_code="CHANNEL_SESSION_EXPIRED",
                    real_platform_connected=False,
                )
                return ChannelHeartbeat(
                    connection_id=session.connection_id,
                    session_id=session.session_id,
                    status=HeartbeatStatus.SESSION_EXPIRED,
                    checked_at=now,
                    next_check_after_seconds=next_check_after_seconds,
                    failure_code="CHANNEL_SESSION_EXPIRED",
                    real_platform_contacted=False,
                )
            healthy = self._heartbeat_probe.probe(session)
            session = session.model_copy(update={"last_heartbeat_at": now})
            self._session = session
            self._transition(
                (
                    ChannelConnectionState.CONNECTED
                    if healthy
                    else ChannelConnectionState.DEGRADED
                ),
                connected_at=self._connection.connected_at,
                last_heartbeat_at=now,
                failure_code=None if healthy else "CHANNEL_HEARTBEAT_FAILED",
                real_platform_connected=(
                    self._real_platform_connection if healthy else False
                ),
            )
            return ChannelHeartbeat(
                connection_id=session.connection_id,
                session_id=session.session_id,
                status=HeartbeatStatus.OK if healthy else HeartbeatStatus.FAILED,
                checked_at=now,
                next_check_after_seconds=next_check_after_seconds,
                failure_code=None if healthy else "CHANNEL_HEARTBEAT_FAILED",
                real_platform_contacted=(
                    self._real_platform_connection if healthy else False
                ),
            )

    def get_session(self) -> ChannelSession | None:
        with self._lock:
            return self._session

    def disconnect(self) -> None:
        with self._lock:
            self._session = None
            self._connection = ChannelConnection(
                connection_id=self._connection.connection_id,
                channel=self.channel,
                account_ref=self.credential.account_ref,
                state=ChannelConnectionState.DISCONNECTED,
                real_platform_connected=False,
            )
            self._transition_history.append(ChannelConnectionState.DISCONNECTED)

    def _transition(
        self,
        state: ChannelConnectionState,
        *,
        connected_at: datetime | None = None,
        last_heartbeat_at: datetime | None = None,
        failure_code: str | None = None,
        real_platform_connected: bool | None = None,
    ) -> None:
        self._connection = self._connection.model_copy(
            update={
                "state": state,
                "connected_at": connected_at,
                "last_heartbeat_at": last_heartbeat_at,
                "failure_code": failure_code,
                "real_platform_connected": (
                    self._connection.real_platform_connected
                    if real_platform_connected is None
                    else real_platform_connected
                ),
            }
        )
        self._transition_history.append(state)


__all__ = [
    "ChannelAuthentication",
    "ChannelAuthenticationBroker",
    "ChannelAuthenticationFailed",
    "ChannelAuthenticationScheme",
    "ChannelConnection",
    "ChannelConnectionState",
    "ChannelCredentialReference",
    "ChannelHeartbeat",
    "ChannelHeartbeatProbe",
    "ChannelLifecycleError",
    "ChannelLifecycleManager",
    "ChannelSession",
    "ChannelSessionUnavailable",
    "HeartbeatStatus",
]
