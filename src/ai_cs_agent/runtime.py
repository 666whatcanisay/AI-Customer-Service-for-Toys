from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Protocol

from .browser import BrowserError, WindowsBrowserManager
from .config import AgentConfig, ConfigError, load_config
from .gateway import (
    GatewayAuthenticationFailed,
    GatewayClient,
    GatewayContractViolation,
    GatewayError,
    GatewayUnavailable,
)
from .models import (
    AGENT_VERSION,
    AgentStatus,
    ExitCode,
    FirstLaunchState,
    RuntimeState,
    utc_now_text,
)
from .observability import EventLog
from .security import CredentialProvider, CredentialUnavailable, WindowsCredentialProvider
from .session import SessionManager
from .state import RuntimeStateStore


class GatewayPort(Protocol):
    def health_check(self): ...


class BrowserPort(Protocol):
    def detect_chrome(self) -> Path: ...

    def initialize_profile(self) -> Path: ...

    def snapshot(self): ...


class AgentRuntime:
    """Production-only local lifecycle. It has no channel-send composition."""

    def __init__(
        self,
        home: str | Path,
        config_path: str | Path,
        *,
        credential_provider: CredentialProvider | None = None,
        gateway_factory: Callable[[AgentConfig, CredentialProvider], GatewayPort]
        | None = None,
        browser_factory: Callable[[Path, AgentConfig], BrowserPort] | None = None,
        heartbeat_seconds: float = 5.0,
    ) -> None:
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        self.home = Path(home).resolve()
        self.config_path = Path(config_path).resolve()
        self.heartbeat_seconds = heartbeat_seconds
        self.credential_provider = credential_provider or WindowsCredentialProvider()
        self.gateway_factory = gateway_factory or (
            lambda config, provider: GatewayClient(config.server, provider)
        )
        self.browser_factory = browser_factory or (
            lambda home, config: WindowsBrowserManager(home, config.browser)
        )
        self.state_store = RuntimeStateStore(self.home / "runtime" / "agent-state.json")
        self.events = EventLog(self.home / "logs" / "agent-events.jsonl")
        self.stop_request = self.home / "runtime" / "stop.request"
        self.session_manager = SessionManager()
        self._gateway: GatewayPort | None = None
        self._browser: BrowserPort | None = None

    def preflight(self) -> RuntimeState:
        previous_exists = self.state_store.path.exists()
        previous = self.state_store.load()
        state = previous
        state.agent_version = AGENT_VERSION
        state.agent_status = AgentStatus.STARTING
        state.first_launch_state = FirstLaunchState.CHECKING_ENVIRONMENT
        state.pid = os.getpid()
        state.started_at = state.started_at or utc_now_text()
        state.stopped_at = None
        state.exit_code = int(ExitCode.NORMAL)
        state.config = {"status": "CHECKING"}
        state.gateway = {}
        state.browser = {}
        state.last_error = None
        self._persist(state, "AGENT_STARTING", "PENDING", {})
        try:
            self._check_environment()
            config = load_config(self.config_path)
            state.config = {
                "status": "VALID",
                "schema_version": config.schema_version,
                "runtime_mode": config.runtime_mode,
            }
            state.node_id = f"{config.agent_id}:{config.device_id}"
            if not previous_exists:
                state.safety = {
                    "kill_switch": config.safety.kill_switch,
                    "manual_approval": config.safety.manual_approval,
                    "auto_reply": config.safety.auto_reply,
                }
            else:
                state.safety.update(
                    {
                        "manual_approval": True,
                        "auto_reply": False,
                    }
                )

            state.first_launch_state = FirstLaunchState.CONNECTING_SERVER
            state.gateway = {"status": "CHECKING", "reachable": False}
            self.state_store.save(state)
            self._gateway = self.gateway_factory(config, self.credential_provider)
            gateway_health = self._gateway.health_check()
            state.gateway = {
                "status": gateway_health.status,
                "reachable": gateway_health.reachable,
                "contract_version": gateway_health.contract_version,
                "version": gateway_health.version,
                "checked_at": utc_now_text(),
            }
            self._persist(
                state,
                "GATEWAY_CONNECTED",
                "SUCCESS",
                {"contract_version": gateway_health.contract_version},
            )

            state.first_launch_state = FirstLaunchState.CONFIGURING_IDENTITY
            self.state_store.save(state)
            self._persist(
                state,
                "IDENTITY_CONFIGURED",
                "SUCCESS",
                {"identity_configured": bool(config.customer_service_identity)},
            )

            state.first_launch_state = FirstLaunchState.CHECKING_BROWSER
            self.state_store.save(state)
            self._browser = self.browser_factory(self.home, config)
            self._browser.detect_chrome()

            state.first_launch_state = FirstLaunchState.INITIALIZING_PROFILE
            self.state_store.save(state)
            self._browser.initialize_profile()
            state.browser = self._browser.snapshot().to_dict()
            state.browser["chrome_path"] = None
            state.browser["chrome_path_redacted"] = True
            if previous.session:
                session = self.session_manager.recover(
                    previous.session, config.server.credential_reference
                )
                if session.recovery_reason:
                    state.recovery_count += 1
                    self.events.append(
                        "SESSION_RECOVERED",
                        "SUCCESS",
                        {"reason_code": session.recovery_reason},
                    )
            else:
                session = self.session_manager.initialize(
                    config.server.credential_reference
                )
            state.session = session.to_dict()
            state.first_launch_state = FirstLaunchState.READY
            state.agent_status = AgentStatus.READY
            state.exit_code = int(ExitCode.NORMAL)
            self._persist(
                state,
                "AGENT_READY",
                "SUCCESS",
                {
                    "runtime_mode": config.runtime_mode,
                    "kill_switch_enabled": bool(state.safety.get("kill_switch", True)),
                },
            )
            state.agent_status = AgentStatus.RUNNING
            self.state_store.save(state)
            return state
        except (ConfigError, CredentialUnavailable, GatewayError, BrowserError, OSError) as exc:
            return self._fail(state, exc, "AGENT_START_FAILED")
        except Exception as exc:
            return self._fail(state, exc, "AGENT_START_FAILED")

    def run(self) -> int:
        try:
            self.stop_request.unlink(missing_ok=True)
            state = self.preflight()
            if state.agent_status is AgentStatus.FAILED:
                return state.exit_code
            while not self.stop_request.exists():
                time.sleep(self.heartbeat_seconds)
                state = self._heartbeat(state)
            state.agent_status = AgentStatus.STOPPING
            self._persist(state, "AGENT_STOPPING", "PENDING", {})
            state.agent_status = AgentStatus.STOPPED
            state.stopped_at = utc_now_text()
            state.pid = None
            self._persist(state, "AGENT_STOPPED", "SUCCESS", {})
            self.stop_request.unlink(missing_ok=True)
            state.exit_code = int(ExitCode.NORMAL)
            self.state_store.save(state)
            return int(ExitCode.NORMAL)
        except KeyboardInterrupt:
            state = self.state_store.load()
            state.agent_status = AgentStatus.STOPPED
            state.stopped_at = utc_now_text()
            state.pid = None
            state.exit_code = int(ExitCode.NORMAL)
            self.state_store.save(state)
            return int(ExitCode.NORMAL)
        except Exception as exc:
            state = self.state_store.load()
            self._fail(state, exc, "AGENT_RUNTIME_FAILED")
            return int(ExitCode.RUNTIME_ERROR)

    def status(self) -> RuntimeState:
        return self.state_store.load()

    def request_stop(self) -> None:
        self.stop_request.parent.mkdir(parents=True, exist_ok=True)
        self.stop_request.write_text(utc_now_text() + "\n", encoding="utf-8")

    def prepare_start(self) -> RuntimeState:
        state = self.state_store.load()
        state.agent_version = AGENT_VERSION
        state.agent_status = AgentStatus.STARTING
        state.first_launch_state = FirstLaunchState.CHECKING_ENVIRONMENT
        state.pid = None
        state.started_at = None
        state.stopped_at = None
        state.exit_code = int(ExitCode.NORMAL)
        state.config = {"status": "CHECKING"}
        state.gateway = {}
        state.browser = {}
        state.last_error = None
        self.stop_request.unlink(missing_ok=True)
        self.state_store.save(state)
        return state

    def set_kill_switch(self, enabled: bool, operator: str = "local-operator") -> RuntimeState:
        state = self.state_store.load()
        before = bool(state.safety.get("kill_switch", True))
        state.safety["kill_switch"] = enabled
        state.safety["manual_approval"] = True
        state.safety["auto_reply"] = False
        self.state_store.save(state)
        self.events.append(
            "KILL_SWITCH_CHANGED",
            "SUCCESS",
            {
                "operator": operator,
                "before_enabled": before,
                "after_enabled": enabled,
            },
        )
        return state

    def _heartbeat(self, state: RuntimeState) -> RuntimeState:
        try:
            if self._gateway is None or self._browser is None:
                raise RuntimeError("runtime components were not composed")
            gateway = self._gateway.health_check()
            browser = self._browser.snapshot()
            state.gateway.update(
                {
                    "status": gateway.status,
                    "reachable": gateway.reachable,
                    "checked_at": utc_now_text(),
                }
            )
            state.browser = browser.to_dict()
            state.browser["chrome_path"] = None
            state.browser["chrome_path_redacted"] = True
            if state.agent_status is AgentStatus.DEGRADED:
                self.events.append(
                    "RUNTIME_RECOVERED", "SUCCESS", {"reason_code": "HEARTBEAT_OK"}
                )
            state.agent_status = AgentStatus.RUNNING
            state.exit_code = int(ExitCode.NORMAL)
            state.last_error = None
        except (CredentialUnavailable, GatewayError, BrowserError, RuntimeError) as exc:
            state.agent_status = AgentStatus.DEGRADED
            state.exit_code = int(_exit_code_for_exception(exc))
            self._mark_component_failure(state, exc)
            state.last_error = {
                "code": type(exc).__name__.upper(),
                "message": _operator_message(exc),
            }
            self.events.append(
                "RUNTIME_DEGRADED",
                "FAILED",
                {"reason_code": type(exc).__name__.upper()},
            )
        self.state_store.save(state)
        return state

    def _fail(
        self, state: RuntimeState, exc: Exception, event_type: str
    ) -> RuntimeState:
        state.agent_status = AgentStatus.FAILED
        state.first_launch_state = FirstLaunchState.FAILED
        state.pid = None
        state.exit_code = int(_exit_code_for_exception(exc))
        self._mark_component_failure(state, exc)
        state.last_error = {
            "code": type(exc).__name__.upper(),
            "message": _operator_message(exc),
        }
        self._persist(
            state,
            event_type,
            "FAILED",
            {
                "reason_code": type(exc).__name__.upper(),
                "exit_code": state.exit_code,
            },
        )
        return state

    @staticmethod
    def _mark_component_failure(state: RuntimeState, exc: Exception) -> None:
        if isinstance(exc, ConfigError):
            state.config = {"status": "INVALID"}
        elif isinstance(exc, (CredentialUnavailable, GatewayAuthenticationFailed)):
            state.gateway = {"status": "AUTHENTICATION_FAILED", "reachable": True}
        elif isinstance(exc, GatewayUnavailable):
            state.gateway = {"status": "GATEWAY_UNAVAILABLE", "reachable": False}
        elif isinstance(exc, GatewayContractViolation):
            state.gateway = {"status": "CONTRACT_ERROR", "reachable": True}
        elif isinstance(exc, GatewayError):
            state.gateway = {"status": "ERROR", "reachable": True}
        elif isinstance(exc, BrowserError):
            state.browser = {"chrome_status": "UNAVAILABLE"}

    def _check_environment(self) -> None:
        if os.name != "nt":
            raise OSError("Windows is required")
        for relative in ("config", "runtime", "logs"):
            path = self.home / relative
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-check"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()

    def _persist(
        self,
        state: RuntimeState,
        event_type: str,
        status: str,
        metadata: dict[str, str | bool | int],
    ) -> None:
        self.state_store.save(state)
        self.events.append(event_type, status, metadata)


def _exit_code_for_exception(exc: Exception) -> ExitCode:
    if isinstance(exc, ConfigError):
        return ExitCode.CONFIG_ERROR
    if isinstance(exc, (CredentialUnavailable, GatewayAuthenticationFailed)):
        return ExitCode.AUTHENTICATION_FAILED
    if isinstance(exc, GatewayUnavailable):
        return ExitCode.GATEWAY_UNREACHABLE
    if isinstance(exc, BrowserError):
        return ExitCode.BROWSER_ERROR
    return ExitCode.RUNTIME_ERROR


def _operator_message(exc: Exception) -> str:
    if isinstance(exc, ConfigError):
        return "Agent 配置无效，请检查配置页面或示例文件。"
    if isinstance(exc, (CredentialUnavailable, GatewayAuthenticationFailed)):
        return "AI-CS 凭据引用不可用，请检查 Windows 凭据管理器。"
    if isinstance(exc, GatewayUnavailable):
        return "无法连接 AI-CS Gateway，请检查服务地址和服务状态。"
    if isinstance(exc, GatewayContractViolation):
        return "AI-CS Gateway 协议校验失败，请检查服务版本与响应。"
    if isinstance(exc, GatewayError):
        return "AI-CS Gateway 返回异常，请联系系统管理员。"
    if isinstance(exc, BrowserError):
        return "Chrome 或独立浏览器 Profile 不可用。"
    return "Windows Agent 运行异常，请查看本地事件日志或联系系统管理员。"
