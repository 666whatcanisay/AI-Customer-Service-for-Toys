from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Protocol, runtime_checkable

from channel_engine.control.models import KillSwitchState
from channel_engine.models.entities import utc_now

from .config import ChannelAgentConfig
from .models import (
    AgentComponentHealth,
    AgentComponentStatus,
    AgentHealth,
    AgentLifecycleEvent,
    AgentLifecycleStage,
    AgentNode,
    AgentNodeStatus,
    AgentServerConnection,
    AgentStatusView,
    AgentStoreStatus,
    StoreBinding,
    StoreBindingStatus,
)


class ChannelAgentError(RuntimeError):
    pass


class AgentLifecycleError(ChannelAgentError):
    pass


class AgentStoreBindingError(ChannelAgentError):
    pass


@runtime_checkable
class AgentServerConnector(Protocol):
    connector_name: str
    real_server_connection: bool

    def connect(self, server_url: str, token_reference: str) -> bool:
        """Connect using a reference only; never accept a token value."""

    def health_check(self) -> bool:
        """Return current server reachability."""

    def disconnect(self) -> None:
        """Close local connector resources."""


@runtime_checkable
class AgentBrowserController(Protocol):
    controller_name: str
    real_browser_started: bool

    def start(self, chrome_path: str, profile_root: str) -> bool:
        """Start/check the configured dedicated browser runtime."""

    def health_check(self) -> bool:
        """Return browser process/page availability."""

    def stop(self) -> None:
        """Stop owned browser resources without deleting the profile."""


@runtime_checkable
class AgentChannelRuntimeProbe(Protocol):
    probe_name: str
    real_channel_connection: bool

    def health_check(self) -> bool:
        """Return channel runtime readiness without sending."""


class AgentKillSwitchProvider(Protocol):
    def enabled(self) -> bool:
        """Return the authoritative channel kill-switch state."""


class FakeAgentServerConnector:
    connector_name = "fake-agent-server-connector.v1"
    real_server_connection = False

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.connected = False
        self.connect_count = 0
        self.health_count = 0
        self.disconnect_count = 0
        self.secret_value_access_count = 0

    def connect(self, server_url: str, token_reference: str) -> bool:
        if not server_url:
            raise ValueError("server URL is required")
        if not token_reference.startswith(("secret-ref://", "credential-ref://")):
            raise ValueError("Agent connector accepts token references only")
        self.connect_count += 1
        self.connected = self.available
        return self.connected

    def health_check(self) -> bool:
        self.health_count += 1
        if not self.available:
            self.connected = False
        return self.connected and self.available

    def disconnect(self) -> None:
        self.disconnect_count += 1
        self.connected = False

    def set_available(self, available: bool) -> None:
        self.available = available
        if not available:
            self.connected = False


class FakeAgentBrowserController:
    controller_name = "fake-agent-browser-controller.v1"
    real_browser_started = False

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.started = False
        self.start_count = 0
        self.health_count = 0
        self.stop_count = 0

    def start(self, chrome_path: str, profile_root: str) -> bool:
        if not chrome_path or not profile_root:
            raise ValueError("browser paths are required")
        self.start_count += 1
        self.started = self.available
        return self.started

    def health_check(self) -> bool:
        self.health_count += 1
        if not self.available:
            self.started = False
        return self.started and self.available

    def stop(self) -> None:
        self.stop_count += 1
        self.started = False

    def set_available(self, available: bool) -> None:
        self.available = available
        if not available:
            self.started = False


class FakeAgentChannelRuntimeProbe:
    probe_name = "fake-agent-channel-runtime-probe.v1"
    real_channel_connection = False

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.health_count = 0
        self.real_send_count = 0

    def health_check(self) -> bool:
        self.health_count += 1
        return self.available

    def set_available(self, available: bool) -> None:
        self.available = available


class StaticAgentKillSwitch:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled


class PDDProductionKillSwitchProvider:
    def __init__(self, pdd_safety_service) -> None:  # type: ignore[no-untyped-def]
        self._service = pdd_safety_service

    def enabled(self) -> bool:
        return self._service.status().kill_switch is KillSwitchState.ENABLED


class SingleStoreBindingRegistry:
    """One-node/one-store registry. A second store requires explicit unbind."""

    def __init__(self, initial: StoreBinding | None = None) -> None:
        self._binding = initial

    def bind(self, binding: StoreBinding) -> StoreBinding:
        if self._binding is not None and self._binding.store_id != binding.store_id:
            raise AgentStoreBindingError(
                "Channel Agent V1 supports one store; unbind before replacing it"
            )
        self._binding = binding
        return binding

    def unbind(self) -> StoreBinding | None:
        previous = self._binding
        self._binding = None
        return previous

    def snapshot(self) -> StoreBinding | None:
        return self._binding

    def status(self) -> AgentStoreStatus:
        if self._binding is None:
            return AgentStoreStatus.UNBOUND
        if self._binding.status is StoreBindingStatus.SUSPENDED:
            return AgentStoreStatus.SUSPENDED
        return AgentStoreStatus.BOUND


class ChannelAgentService:
    """Local-only node orchestrator; it owns no message-send operation."""

    _ALLOWED_TRANSITIONS = {
        AgentNodeStatus.INIT: {AgentNodeStatus.CONNECTING, AgentNodeStatus.STOPPED},
        AgentNodeStatus.OFFLINE: {
            AgentNodeStatus.CONNECTING,
            AgentNodeStatus.STOPPED,
        },
        AgentNodeStatus.CONNECTING: {
            AgentNodeStatus.ONLINE,
            AgentNodeStatus.DEGRADED,
            AgentNodeStatus.OFFLINE,
            AgentNodeStatus.STOPPED,
        },
        AgentNodeStatus.ONLINE: {
            AgentNodeStatus.DEGRADED,
            AgentNodeStatus.OFFLINE,
            AgentNodeStatus.STOPPED,
        },
        AgentNodeStatus.DEGRADED: {
            AgentNodeStatus.CONNECTING,
            AgentNodeStatus.ONLINE,
            AgentNodeStatus.OFFLINE,
            AgentNodeStatus.STOPPED,
        },
        AgentNodeStatus.STOPPED: {AgentNodeStatus.CONNECTING},
    }

    def __init__(
        self,
        config: ChannelAgentConfig,
        server: AgentServerConnector,
        browser: AgentBrowserController,
        channel: AgentChannelRuntimeProbe,
        *,
        kill_switch_provider: AgentKillSwitchProvider | None = None,
        clock: Callable = utc_now,  # type: ignore[type-arg]
    ) -> None:
        if not isinstance(server, AgentServerConnector):
            raise TypeError("server does not implement AgentServerConnector")
        if not isinstance(browser, AgentBrowserController):
            raise TypeError("browser does not implement AgentBrowserController")
        if not isinstance(channel, AgentChannelRuntimeProbe):
            raise TypeError("channel does not implement AgentChannelRuntimeProbe")
        if server.real_server_connection:
            raise ValueError("Agent Foundation V1 forbids a real server connector")
        if browser.real_browser_started:
            raise ValueError("Agent Foundation V1 forbids starting a real browser")
        if channel.real_channel_connection:
            raise ValueError("Agent Foundation V1 forbids a real channel probe")
        self._config = config
        self._server = server
        self._browser = browser
        self._channel = channel
        self._kill_switch_provider = kill_switch_provider or StaticAgentKillSwitch()
        self._clock = clock
        self._lock = RLock()
        self._stores = SingleStoreBindingRegistry(config.channel.store_binding)
        self._events: list[AgentLifecycleEvent] = []
        now = clock()
        self._node = AgentNode(
            node_id=config.node_id,
            node_name=config.node_name,
            status=AgentNodeStatus.INIT,
            version=config.agent_version,
            server_connection=AgentServerConnection.DISCONNECTED,
            environment=config.safety.runtime_mode,
        )
        self._server_health = self._component(
            "server", AgentComponentStatus.UNKNOWN, "AGENT_NOT_STARTED", now
        )
        self._browser_health = self._component(
            "browser", AgentComponentStatus.UNKNOWN, "AGENT_NOT_STARTED", now
        )
        self._channel_health = self._component(
            "channel", AgentComponentStatus.UNKNOWN, "AGENT_NOT_STARTED", now
        )

    @property
    def config(self) -> ChannelAgentConfig:
        return self._config

    def lifecycle_events(self) -> tuple[AgentLifecycleEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def start(self) -> AgentStatusView:
        with self._lock:
            if self._node.status in {AgentNodeStatus.ONLINE, AgentNodeStatus.CONNECTING}:
                return self.status()
            previous_status = self._node.status
            self._transition(AgentNodeStatus.CONNECTING)
            now = self._clock()
            self._record(
                AgentLifecycleStage.ENVIRONMENT_CHECK,
                True,
                "AGENT_ENVIRONMENT_VALID",
                now,
            )
            self._node = self._node.model_copy(
                update={"server_connection": AgentServerConnection.CONNECTING}
            )
            try:
                connected = self._server.connect(
                    self._config.server.server_url,
                    self._config.server.agent_token_reference,
                )
            except Exception:
                connected = False
            self._record(
                AgentLifecycleStage.SERVER_CONNECT,
                connected,
                "AGENT_SERVER_CONNECTED" if connected else "AGENT_SERVER_UNAVAILABLE",
                self._clock(),
            )
            if not connected:
                self._server_health = self._component(
                    "server",
                    AgentComponentStatus.UNAVAILABLE,
                    "AGENT_SERVER_UNAVAILABLE",
                )
                self._browser_health = self._component(
                    "browser", AgentComponentStatus.STOPPED, "AGENT_SERVER_REQUIRED"
                )
                self._channel_health = self._component(
                    "channel", AgentComponentStatus.BLOCKED, "AGENT_SERVER_REQUIRED"
                )
                self._node = self._node.model_copy(
                    update={"server_connection": AgentServerConnection.DISCONNECTED}
                )
                self._transition(AgentNodeStatus.OFFLINE)
                return self.status()
            self._node = self._node.model_copy(
                update={"server_connection": AgentServerConnection.CONNECTED}
            )
            self._server_health = self._component(
                "server", AgentComponentStatus.HEALTHY, "AGENT_SERVER_CONNECTED"
            )
            self._record(
                AgentLifecycleStage.CONFIG_LOAD,
                True,
                "AGENT_CONFIG_LOADED",
                self._clock(),
            )
            browser_ok = False
            if previous_status in {
                AgentNodeStatus.OFFLINE,
                AgentNodeStatus.DEGRADED,
            }:
                try:
                    browser_ok = self._browser.health_check()
                except Exception:
                    browser_ok = False
            if not browser_ok:
                try:
                    browser_ok = self._browser.start(
                        str(self._config.browser.chrome_path),
                        str(self._config.browser.profile_root),
                    )
                except Exception:
                    browser_ok = False
            self._browser_health = self._component(
                "browser",
                (
                    AgentComponentStatus.HEALTHY
                    if browser_ok
                    else AgentComponentStatus.UNAVAILABLE
                ),
                "AGENT_BROWSER_READY" if browser_ok else "AGENT_BROWSER_UNAVAILABLE",
            )
            self._record(
                AgentLifecycleStage.BROWSER_CHECK,
                browser_ok,
                "AGENT_BROWSER_READY" if browser_ok else "AGENT_BROWSER_UNAVAILABLE",
                self._clock(),
            )
            channel_ok = self._evaluate_channel(browser_ok)
            self._record(
                AgentLifecycleStage.CHANNEL_CHECK,
                channel_ok,
                self._channel_health.reason_code,
                self._clock(),
            )
            self._resolve_ready(channel_ok)
            return self.status()

    def stop(self) -> AgentStatusView:
        with self._lock:
            if self._node.status is AgentNodeStatus.STOPPED:
                return self.status()
            self._browser.stop()
            self._server.disconnect()
            self._server_health = self._component(
                "server", AgentComponentStatus.STOPPED, "AGENT_STOPPED"
            )
            self._browser_health = self._component(
                "browser", AgentComponentStatus.STOPPED, "AGENT_STOPPED"
            )
            self._channel_health = self._component(
                "channel", AgentComponentStatus.STOPPED, "AGENT_STOPPED"
            )
            self._node = self._node.model_copy(
                update={"server_connection": AgentServerConnection.DISCONNECTED}
            )
            self._record(
                AgentLifecycleStage.STOP,
                True,
                "AGENT_STOPPED",
                self._clock(),
            )
            self._transition(AgentNodeStatus.STOPPED)
            return self.status()

    def check(self) -> AgentStatusView:
        with self._lock:
            if self._node.status in {AgentNodeStatus.INIT, AgentNodeStatus.STOPPED}:
                return self.status()
            if self._node.status is AgentNodeStatus.OFFLINE:
                return self.start()
            try:
                server_ok = self._server.health_check()
            except Exception:
                server_ok = False
            self._server_health = self._component(
                "server",
                (
                    AgentComponentStatus.HEALTHY
                    if server_ok
                    else AgentComponentStatus.UNAVAILABLE
                ),
                "AGENT_SERVER_CONNECTED" if server_ok else "AGENT_SERVER_DISCONNECTED",
            )
            if not server_ok:
                self._node = self._node.model_copy(
                    update={"server_connection": AgentServerConnection.DISCONNECTED}
                )
                self._channel_health = self._component(
                    "channel",
                    AgentComponentStatus.DEGRADED,
                    "AGENT_SERVER_DISCONNECTED",
                )
                self._transition(AgentNodeStatus.OFFLINE)
                return self.status()
            try:
                browser_ok = self._browser.health_check()
            except Exception:
                browser_ok = False
            if not browser_ok:
                try:
                    browser_ok = self._browser.start(
                        str(self._config.browser.chrome_path),
                        str(self._config.browser.profile_root),
                    )
                except Exception:
                    browser_ok = False
            self._browser_health = self._component(
                "browser",
                (
                    AgentComponentStatus.HEALTHY
                    if browser_ok
                    else AgentComponentStatus.UNAVAILABLE
                ),
                "AGENT_BROWSER_READY" if browser_ok else "AGENT_BROWSER_UNAVAILABLE",
            )
            channel_ok = self._evaluate_channel(browser_ok)
            target = AgentNodeStatus.ONLINE if channel_ok else AgentNodeStatus.DEGRADED
            if target is not self._node.status:
                self._transition(target)
            else:
                self._heartbeat()
            return self.status()

    def bind_store(self, binding: StoreBinding) -> AgentStatusView:
        with self._lock:
            if self._node.status not in {
                AgentNodeStatus.INIT,
                AgentNodeStatus.STOPPED,
            }:
                raise AgentStoreBindingError("stop Agent before changing store binding")
            self._stores.bind(binding)
            self._replace_config_binding(binding)
            return self.status()

    def unbind_store(self) -> AgentStatusView:
        with self._lock:
            if self._node.status not in {
                AgentNodeStatus.INIT,
                AgentNodeStatus.STOPPED,
            }:
                raise AgentStoreBindingError("stop Agent before unbinding store")
            self._stores.unbind()
            self._replace_config_binding(None)
            return self.status()

    def reload_config(self, config: ChannelAgentConfig) -> AgentStatusView:
        with self._lock:
            if self._node.status not in {
                AgentNodeStatus.INIT,
                AgentNodeStatus.STOPPED,
            }:
                raise AgentLifecycleError("stop Agent before loading a new config")
            self._config = config
            self._stores = SingleStoreBindingRegistry(config.channel.store_binding)
            self._node = self._node.model_copy(
                update={
                    "node_id": config.node_id,
                    "node_name": config.node_name,
                    "version": config.agent_version,
                    "environment": config.safety.runtime_mode,
                }
            )
            return self.status()

    def status(self) -> AgentStatusView:
        with self._lock:
            binding = self._stores.snapshot()
            store_status = self._stores.status()
            return AgentStatusView(
                node=self._node,
                server_status=self._server_health,
                browser_status=self._browser_health,
                channel_status=self._channel_health,
                store_status=store_status,
                store_id=binding.store_id if binding is not None else None,
                store_name=binding.store_name if binding is not None else None,
                dry_run=self._config.safety.dry_run,
                kill_switch=self._kill_switch_enabled(),
                config_fingerprint=self._config.fingerprint(),
            )

    def health(self) -> AgentHealth:
        status = self.status()
        mapping = {
            AgentNodeStatus.ONLINE: ("healthy", True, "AGENT_READY"),
            AgentNodeStatus.DEGRADED: ("degraded", False, "AGENT_DEGRADED"),
            AgentNodeStatus.OFFLINE: ("offline", False, "AGENT_OFFLINE"),
            AgentNodeStatus.STOPPED: ("stopped", False, "AGENT_STOPPED"),
            AgentNodeStatus.INIT: ("stopped", False, "AGENT_NOT_STARTED"),
            AgentNodeStatus.CONNECTING: ("degraded", False, "AGENT_CONNECTING"),
        }
        label, ready, reason = mapping[status.node.status]
        return AgentHealth(
            status=label,  # type: ignore[arg-type]
            ready=ready,
            node_status=status.node.status,
            checked_at=self._clock(),
            reason_code=reason,
        )

    def _evaluate_channel(self, browser_ok: bool) -> bool:
        if self._kill_switch_enabled():
            self._channel_health = self._component(
                "channel", AgentComponentStatus.BLOCKED, "AGENT_KILL_SWITCH_ENABLED"
            )
            return False
        store_status = self._stores.status()
        if store_status is AgentStoreStatus.UNBOUND:
            self._channel_health = self._component(
                "channel", AgentComponentStatus.BLOCKED, "AGENT_STORE_UNBOUND"
            )
            return False
        if store_status is AgentStoreStatus.SUSPENDED:
            self._channel_health = self._component(
                "channel", AgentComponentStatus.BLOCKED, "AGENT_STORE_SUSPENDED"
            )
            return False
        if not browser_ok:
            self._channel_health = self._component(
                "channel", AgentComponentStatus.BLOCKED, "AGENT_BROWSER_UNAVAILABLE"
            )
            return False
        try:
            channel_ok = self._channel.health_check()
        except Exception:
            channel_ok = False
        self._channel_health = self._component(
            "channel",
            (
                AgentComponentStatus.HEALTHY
                if channel_ok
                else AgentComponentStatus.UNAVAILABLE
            ),
            "AGENT_CHANNEL_READY" if channel_ok else "AGENT_CHANNEL_UNAVAILABLE",
        )
        return channel_ok

    def _resolve_ready(self, channel_ok: bool) -> None:
        target = AgentNodeStatus.ONLINE if channel_ok else AgentNodeStatus.DEGRADED
        self._transition(target)
        self._record(
            AgentLifecycleStage.READY,
            channel_ok,
            "AGENT_READY" if channel_ok else "AGENT_DEGRADED",
            self._clock(),
        )

    def _transition(self, target: AgentNodeStatus) -> None:
        current = self._node.status
        if target is current:
            self._heartbeat()
            return
        if target not in self._ALLOWED_TRANSITIONS[current]:
            raise AgentLifecycleError(
                f"invalid Agent transition {current.value} -> {target.value}"
            )
        self._node = self._node.model_copy(
            update={"status": target, "last_heartbeat": self._clock()}
        )

    def _heartbeat(self) -> None:
        self._node = self._node.model_copy(
            update={"last_heartbeat": self._clock()}
        )

    def _kill_switch_enabled(self) -> bool:
        return self._config.safety.kill_switch or self._kill_switch_provider.enabled()

    def _replace_config_binding(self, binding: StoreBinding | None) -> None:
        payload = self._config.model_dump(mode="python")
        payload["channel"]["store_binding"] = (
            binding.model_dump(mode="python") if binding is not None else None
        )
        self._config = ChannelAgentConfig.model_validate(payload)

    def _record(
        self,
        stage: AgentLifecycleStage,
        successful: bool,
        reason_code: str,
        occurred_at,
    ) -> None:  # type: ignore[no-untyped-def]
        self._events.append(
            AgentLifecycleEvent(
                sequence=len(self._events) + 1,
                stage=stage,
                occurred_at=occurred_at,
                successful=successful,
                reason_code=reason_code,
            )
        )

    def _component(
        self,
        component: str,
        status: AgentComponentStatus,
        reason_code: str,
        checked_at=None,  # type: ignore[no-untyped-def]
    ) -> AgentComponentHealth:
        return AgentComponentHealth(
            component=component,  # type: ignore[arg-type]
            status=status,
            checked_at=checked_at or self._clock(),
            reason_code=reason_code,
        )


__all__ = [
    "AgentBrowserController",
    "AgentChannelRuntimeProbe",
    "AgentKillSwitchProvider",
    "AgentLifecycleError",
    "AgentServerConnector",
    "AgentStoreBindingError",
    "ChannelAgentError",
    "ChannelAgentService",
    "FakeAgentBrowserController",
    "FakeAgentChannelRuntimeProbe",
    "FakeAgentServerConnector",
    "PDDProductionKillSwitchProvider",
    "SingleStoreBindingRegistry",
    "StaticAgentKillSwitch",
]
