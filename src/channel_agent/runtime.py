from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, RLock
from typing import Protocol

from .client import AgentClientError, AgentRejectedError, ChannelEngineClient
from .config import ChannelAgentConfig
from .contract import AgentHeartbeatAck, AgentRuntimeStatus, ManagedAgentConfig
from .heartbeat import HeartbeatManager
from .identity import AgentIdentity, AgentIdentityStatus
from .logger import SafeAgentLogger
from .version import AGENT_VERSION


class AgentRuntimeError(RuntimeError):
    pass


class AgentLifecycleError(AgentRuntimeError):
    pass


class AgentClientPort(Protocol):
    def register(self, *, hostname: str, status: AgentRuntimeStatus, timestamp: datetime): ...

    def report_status(
        self, *, hostname: str, status: AgentRuntimeStatus, timestamp: datetime
    ): ...

    def fetch_config(self) -> ManagedAgentConfig: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentRuntimeSnapshot:
    agent_id: str
    device_id: str
    user_id: str | None
    store_id: str | None
    store_ids: tuple[str, ...]
    binding_revision: int
    identity: AgentIdentity | None
    identity_status: AgentIdentityStatus
    production_eligible: bool
    version: str
    hostname: str
    status: AgentRuntimeStatus
    registered: bool
    registration_id: str | None
    config_revision: str | None
    last_heartbeat: datetime | None
    consecutive_failures: int
    last_error_code: str | None


class ChannelAgentRuntime:
    """Standalone node lifecycle with heartbeat-based connection recovery."""

    _ALLOWED = {
        AgentRuntimeStatus.STOPPED: {AgentRuntimeStatus.STARTING},
        AgentRuntimeStatus.STARTING: {
            AgentRuntimeStatus.ONLINE,
            AgentRuntimeStatus.DEGRADED,
            AgentRuntimeStatus.STOPPED,
        },
        AgentRuntimeStatus.ONLINE: {
            AgentRuntimeStatus.DEGRADED,
            AgentRuntimeStatus.STOPPED,
        },
        AgentRuntimeStatus.DEGRADED: {
            AgentRuntimeStatus.ONLINE,
            AgentRuntimeStatus.STOPPED,
        },
    }

    def __init__(
        self,
        config: ChannelAgentConfig,
        client: AgentClientPort,
        logger: SafeAgentLogger,
        *,
        hostname: str | None = None,
        clock=lambda: datetime.now(UTC),  # type: ignore[no-untyped-def]
    ) -> None:
        self._config = config
        self._client = client
        self._logger = logger
        self._hostname = (hostname or socket.gethostname()).strip() or "unknown-host"
        self._clock = clock
        self._lock = RLock()
        self._status = AgentRuntimeStatus.STOPPED
        self._registered = False
        self._registration_id: str | None = None
        self._identity_status = AgentIdentityStatus.UNBOUND
        self._identity: AgentIdentity | None = None
        self._binding_revision = 0
        self._user_id = config.user_reference
        self._store_ids = config.store_references or (
            (config.store_reference,) if config.store_reference is not None else ()
        )
        self._active_store_id = config.store_reference
        self._production_eligible = False
        self._remote_config: ManagedAgentConfig | None = None
        self._last_heartbeat: datetime | None = None
        self._consecutive_failures = 0
        self._last_error_code: str | None = None
        self._heartbeat = HeartbeatManager(
            self.heartbeat_once,
            config.heartbeat_interval_seconds,
            on_error=self._handle_unexpected_heartbeat_error,
        )

    @property
    def heartbeat(self) -> HeartbeatManager:
        return self._heartbeat

    @property
    def remote_config(self) -> ManagedAgentConfig | None:
        with self._lock:
            return self._remote_config

    def start(self, *, background_heartbeat: bool = True) -> AgentRuntimeSnapshot:
        with self._lock:
            if self._status in {AgentRuntimeStatus.ONLINE, AgentRuntimeStatus.STARTING}:
                return self.snapshot()
            if self._status is AgentRuntimeStatus.DEGRADED:
                if background_heartbeat:
                    self._heartbeat.start()
                return self.snapshot()
            self._transition(AgentRuntimeStatus.STARTING)
            self._logger.event(
                "AGENT_STARTING",
                "PENDING",
                {"agent_id": self._config.agent_id, "version": AGENT_VERSION},
            )
        try:
            self._register()
            with self._lock:
                self._transition(AgentRuntimeStatus.ONLINE)
                self._consecutive_failures = 0
                self._last_error_code = None
            self._logger.event(
                "CHANNEL_ENGINE_CONNECTED",
                "SUCCESS",
                {
                    "agent_id": self._config.agent_id,
                    "control_protocol_version": self._config.control_protocol_version,
                },
            )
        except AgentClientError as exc:
            self._degrade(exc, "AGENT_START_CONNECTION_FAILED")
        if background_heartbeat:
            self._heartbeat.start()
        return self.snapshot()

    def heartbeat_once(self) -> AgentRuntimeSnapshot:
        with self._lock:
            if self._status is AgentRuntimeStatus.STOPPED:
                return self.snapshot()
            was_degraded = self._status is AgentRuntimeStatus.DEGRADED
        try:
            if not self._registered:
                self._register()
            now = self._clock()
            ack = self._report_status_with_registration_recovery(now)
            with self._lock:
                self._identity_status = ack.identity_status
                self._production_eligible = ack.production_eligible
                if ack.identity is not None:
                    self._apply_identity_locked(ack.identity)
                current_revision = (
                    self._remote_config.revision if self._remote_config is not None else None
                )
            if ack.config_revision != current_revision:
                self._apply_remote_config(self._client.fetch_config())
            with self._lock:
                if self._status is AgentRuntimeStatus.DEGRADED:
                    self._transition(AgentRuntimeStatus.ONLINE)
                self._last_heartbeat = now
                self._consecutive_failures = 0
                self._last_error_code = None
            if was_degraded:
                self._logger.event(
                    "CHANNEL_ENGINE_CONNECTION_RECOVERED",
                    "SUCCESS",
                    {"agent_id": self._config.agent_id},
                )
        except AgentClientError as exc:
            self._degrade(exc, "AGENT_HEARTBEAT_FAILED")
        return self.snapshot()

    def stop(self) -> AgentRuntimeSnapshot:
        self._heartbeat.stop()
        with self._lock:
            if self._status is AgentRuntimeStatus.STOPPED:
                return self.snapshot()
        try:
            if self._registered:
                self._client.report_status(
                    hostname=self._hostname,
                    status=AgentRuntimeStatus.STOPPED,
                    timestamp=self._clock(),
                )
        except AgentClientError as exc:
            self._logger.error("AGENT_STOP_REPORT_FAILED", exc)
        with self._lock:
            self._transition(AgentRuntimeStatus.STOPPED)
            self._logger.event(
                "AGENT_STOPPED",
                "SUCCESS",
                {"agent_id": self._config.agent_id},
            )
            return self.snapshot()

    def close(self) -> None:
        self.stop()
        self._client.close()
        self._logger.close()

    def run_forever(self, stop_event: Event) -> int:
        self.start(background_heartbeat=True)
        try:
            while not stop_event.wait(0.25):
                pass
        finally:
            self.close()
        return 0

    def snapshot(self) -> AgentRuntimeSnapshot:
        with self._lock:
            return AgentRuntimeSnapshot(
                agent_id=self._config.agent_id,
                device_id=self._config.device_id,
                user_id=self._user_id,
                store_id=self._active_store_id,
                store_ids=self._store_ids,
                binding_revision=self._binding_revision,
                identity=self._identity,
                identity_status=self._identity_status,
                production_eligible=self._production_eligible,
                version=AGENT_VERSION,
                hostname=self._hostname,
                status=self._status,
                registered=self._registered,
                registration_id=self._registration_id,
                config_revision=(
                    self._remote_config.revision if self._remote_config is not None else None
                ),
                last_heartbeat=self._last_heartbeat,
                consecutive_failures=self._consecutive_failures,
                last_error_code=self._last_error_code,
            )

    def _register(self) -> None:
        response = self._client.register(
            hostname=self._hostname,
            status=AgentRuntimeStatus.STARTING,
            timestamp=self._clock(),
        )
        with self._lock:
            self._registered = True
            self._registration_id = response.registration_id
            self._apply_identity_locked(response.identity)
        self._apply_remote_config(response.config)

    def _report_status_with_registration_recovery(
        self,
        now: datetime,
    ) -> AgentHeartbeatAck:
        try:
            return self._client.report_status(
                hostname=self._hostname,
                status=AgentRuntimeStatus.ONLINE,
                timestamp=now,
            )
        except AgentRejectedError as exc:
            if not (
                exc.status_code == 404
                and exc.error_code == "AGENT_NOT_REGISTERED"
            ):
                raise
            with self._lock:
                self._registered = False
                self._registration_id = None
            self._logger.event(
                "AGENT_REGISTRATION_RECOVERY_STARTED",
                "PENDING",
                {"agent_id": self._config.agent_id},
            )
            self._register()
            ack = self._client.report_status(
                hostname=self._hostname,
                status=AgentRuntimeStatus.ONLINE,
                timestamp=now,
            )
            self._logger.event(
                "AGENT_REGISTRATION_RECOVERY_COMPLETED",
                "SUCCESS",
                {"agent_id": self._config.agent_id},
            )
            return ack

    def _apply_remote_config(self, config: ManagedAgentConfig) -> None:
        if config.message_read_enabled or config.send_enabled or config.browser_automation_enabled:
            raise AgentLifecycleError("Foundation config attempted to enable forbidden capability")
        with self._lock:
            self._remote_config = config
        self._heartbeat.set_interval(config.heartbeat_interval_seconds)

    def _apply_identity_locked(self, identity: AgentIdentity) -> None:
        self._identity_status = identity.status
        self._identity = identity
        self._binding_revision = identity.binding_revision
        self._production_eligible = identity.production_eligible
        self._user_id = identity.user_id
        self._store_ids = identity.effective_store_ids
        self._active_store_id = identity.effective_active_store_id

    def _degrade(self, error: Exception, event: str) -> None:
        with self._lock:
            if self._status is AgentRuntimeStatus.STARTING:
                self._transition(AgentRuntimeStatus.DEGRADED)
            elif self._status is AgentRuntimeStatus.ONLINE:
                self._transition(AgentRuntimeStatus.DEGRADED)
            self._consecutive_failures += 1
            self._last_error_code = type(error).__name__.upper()
        self._logger.error(event, error)

    def _handle_unexpected_heartbeat_error(self, error: Exception) -> None:
        self._degrade(error, "AGENT_HEARTBEAT_RUNTIME_ERROR")

    def _transition(self, target: AgentRuntimeStatus) -> None:
        if target is self._status:
            return
        if target not in self._ALLOWED[self._status]:
            raise AgentLifecycleError(
                f"invalid Agent transition {self._status.value} -> {target.value}"
            )
        self._status = target


def build_runtime(
    config: ChannelAgentConfig,
    *,
    log_path: str,
) -> ChannelAgentRuntime:
    logger = SafeAgentLogger(log_path)
    client = ChannelEngineClient(config)
    return ChannelAgentRuntime(config, client, logger)


__all__ = [
    "AgentLifecycleError",
    "AgentRuntimeError",
    "AgentRuntimeSnapshot",
    "ChannelAgentRuntime",
    "build_runtime",
]
