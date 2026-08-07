from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Event
from typing import Callable, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .binding import AgentBindingStore
from .config import AgentConfigError, load_agent_config
from .contract import AgentRuntimeStatus
from .identity import AgentIdentityStatus
from .runtime import AgentRuntimeSnapshot, ChannelAgentRuntime, build_runtime
from .version import AGENT_VERSION


WINDOWS_CLIENT_VERSION = "1.1.1"
WINDOWS_STATE_VERSION = "1.0"
_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class WindowsClientError(RuntimeError):
    pass


class WindowsStateError(WindowsClientError):
    pass


class WindowsClientProcessStatus(StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class WindowsClientState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = WINDOWS_STATE_VERSION
    client_version: str = WINDOWS_CLIENT_VERSION
    agent_version: str = AGENT_VERSION
    pid: int | None = Field(default=None, ge=1)
    process_status: WindowsClientProcessStatus = WindowsClientProcessStatus.STOPPED
    runtime_status: AgentRuntimeStatus = AgentRuntimeStatus.STOPPED
    identity_status: AgentIdentityStatus = AgentIdentityStatus.UNBOUND
    production_eligible: bool = False
    agent_id: str | None = None
    device_id: str | None = None
    user_id: str | None = None
    store_id: str | None = None
    store_ids: tuple[str, ...] = ()
    binding_revision: int = Field(default=0, ge=0)
    config_status: str = "UNKNOWN"
    config_path: str | None = None
    last_heartbeat: AwareDatetime | None = None
    last_error_code: str | None = None
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class WindowsStateStore:
    """Atomic, credential-free local status file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> WindowsClientState:
        if not self.path.exists():
            return WindowsClientState()
        try:
            raw = self.path.read_bytes()
            if len(raw) > 1024 * 1024:
                raise WindowsStateError("Windows Agent state exceeds one MiB")
            return WindowsClientState.model_validate_json(raw)
        except WindowsStateError:
            raise
        except Exception as exc:
            raise WindowsStateError("Windows Agent state is invalid") from exc

    def save(self, state: WindowsClientState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = state.model_dump_json(indent=2).encode("utf-8") + b"\n"
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise WindowsStateError("Windows Agent state cannot be saved") from exc


class WindowsAgentHost:
    """Runs the existing ChannelAgentRuntime inside a Windows process boundary."""

    def __init__(
        self,
        config_path: str | Path,
        data_root: str | Path,
        *,
        runtime_factory: Callable[..., ChannelAgentRuntime] = build_runtime,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self.config_path = Path(config_path).resolve()
        self.data_root = Path(data_root).resolve()
        self.state_store = WindowsStateStore(
            self.data_root / "runtime" / "channel-agent-state.json"
        )
        self.binding_store = AgentBindingStore(
            self.data_root / "runtime" / "agent-binding.json"
        )
        self.stop_request = self.data_root / "runtime" / "stop.request"
        self._runtime_factory = runtime_factory
        self._clock = clock
        self._poll_interval = max(poll_interval_seconds, 0.02)

    def run(self, stop_event: Event) -> int:
        try:
            config = load_agent_config(self.config_path)
        except AgentConfigError:
            self.state_store.save(
                WindowsClientState(
                    pid=os.getpid(),
                    process_status=WindowsClientProcessStatus.FAILED,
                    config_status="INVALID",
                    config_path=str(self.config_path),
                    last_error_code="AGENT_CONFIG_ERROR",
                    updated_at=self._clock(),
                )
            )
            return 1
        self.stop_request.unlink(missing_ok=True)
        self.data_root.joinpath("logs").mkdir(parents=True, exist_ok=True)
        runtime = self._runtime_factory(
            config,
            log_path=str(self.data_root / "logs" / "channel-agent.jsonl"),
        )
        self._save_snapshot(
            runtime.snapshot(),
            WindowsClientProcessStatus.STARTING,
            config_path=self.config_path,
        )
        try:
            snapshot = runtime.start(background_heartbeat=True)
            self._save_snapshot(snapshot, self._process_status(snapshot))
            while not stop_event.wait(self._poll_interval):
                if self.stop_request.exists():
                    stop_event.set()
                    break
                snapshot = runtime.snapshot()
                self._save_snapshot(snapshot, self._process_status(snapshot))
            final = runtime.stop()
            self._save_snapshot(
                final,
                WindowsClientProcessStatus.STOPPED,
                pid=None,
            )
            return 0
        except Exception as exc:
            current = runtime.snapshot()
            self._save_snapshot(
                current,
                WindowsClientProcessStatus.FAILED,
                error_code=type(exc).__name__.upper(),
            )
            return 4
        finally:
            runtime.close()
            self.stop_request.unlink(missing_ok=True)

    def request_stop(self) -> None:
        self.stop_request.parent.mkdir(parents=True, exist_ok=True)
        self.stop_request.write_text("stop\n", encoding="ascii")

    def _save_snapshot(
        self,
        snapshot: AgentRuntimeSnapshot,
        process_status: WindowsClientProcessStatus,
        *,
        config_path: Path | None = None,
        pid: int | None | object = ...,
        error_code: str | None = None,
    ) -> None:
        actual_pid = os.getpid() if pid is ... else pid
        if snapshot.identity is not None:
            self.binding_store.save_identity(snapshot.identity)
        self.state_store.save(
            WindowsClientState(
                pid=actual_pid,
                process_status=process_status,
                runtime_status=snapshot.status,
                identity_status=snapshot.identity_status,
                production_eligible=snapshot.production_eligible,
                agent_id=snapshot.agent_id,
                device_id=snapshot.device_id,
                user_id=snapshot.user_id,
                store_id=snapshot.store_id,
                store_ids=snapshot.store_ids,
                binding_revision=snapshot.binding_revision,
                config_status="VALID",
                config_path=str(config_path or self.config_path),
                last_heartbeat=snapshot.last_heartbeat,
                last_error_code=error_code or snapshot.last_error_code,
                updated_at=self._clock(),
            )
        )

    @staticmethod
    def _process_status(snapshot: AgentRuntimeSnapshot) -> WindowsClientProcessStatus:
        if snapshot.status is AgentRuntimeStatus.ONLINE:
            return WindowsClientProcessStatus.RUNNING
        if snapshot.status is AgentRuntimeStatus.DEGRADED:
            return WindowsClientProcessStatus.DEGRADED
        if snapshot.status is AgentRuntimeStatus.STOPPED:
            return WindowsClientProcessStatus.STOPPED
        return WindowsClientProcessStatus.STARTING


class WindowsAutoStartManager:
    FILE_NAME = "AI-CS-Channel-Agent.cmd"

    def __init__(self, startup_directory: str | Path) -> None:
        self.startup_directory = Path(startup_directory).resolve()
        self.path = self.startup_directory / self.FILE_NAME

    @property
    def enabled(self) -> bool:
        return self.path.is_file()

    def enable(self, executable: str | Path, data_root: str | Path) -> Path:
        executable_path = Path(executable).resolve()
        data_path = Path(data_root).resolve()
        self.startup_directory.mkdir(parents=True, exist_ok=True)
        content = (
            "@echo off\r\n"
            f'"{executable_path}" start --data-root "{data_path}"\r\n'
        )
        self.path.write_text(content, encoding="utf-8-sig", newline="")
        return self.path

    def disable(self) -> None:
        self.path.unlink(missing_ok=True)


class UpgradeCheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    current_version: str
    available_version: str
    update_available: bool
    package_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def check_upgrade_manifest(path: str | Path) -> UpgradeCheckResult:
    source = Path(path)
    try:
        raw = source.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("manifest exceeds one MiB")
        payload = json.loads(raw.decode("utf-8"))
        version = str(payload["version"])
        sha256 = payload.get("package_sha256")
    except Exception as exc:
        raise WindowsClientError("upgrade manifest is invalid") from exc
    current = _version_tuple(WINDOWS_CLIENT_VERSION)
    available = _version_tuple(version)
    return UpgradeCheckResult(
        current_version=WINDOWS_CLIENT_VERSION,
        available_version=version,
        update_available=available > current,
        package_sha256=sha256,
    )


def default_data_root() -> Path:
    configured = os.getenv("AI_CS_CHANNEL_AGENT_DATA_ROOT")
    if configured:
        return Path(configured).resolve()
    base = os.getenv("PROGRAMDATA") or os.getenv("LOCALAPPDATA")
    if base:
        return Path(base).resolve() / "AI-CS" / "ChannelAgent"
    return Path.cwd() / "channel-agent-data"


def default_startup_directory() -> Path:
    configured = os.getenv("AI_CS_CHANNEL_AGENT_STARTUP_DIR")
    if configured:
        return Path(configured).resolve()
    appdata = os.getenv("APPDATA")
    if appdata:
        return (
            Path(appdata).resolve()
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
        )
    return default_data_root() / "autostart"


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value)
    if match is None:
        raise WindowsClientError("upgrade version must be semantic x.y.z")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


__all__ = [
    "UpgradeCheckResult",
    "WINDOWS_CLIENT_VERSION",
    "WindowsAgentHost",
    "WindowsAutoStartManager",
    "WindowsClientError",
    "WindowsClientProcessStatus",
    "WindowsClientState",
    "WindowsStateError",
    "WindowsStateStore",
    "check_upgrade_manifest",
    "default_data_root",
    "default_startup_directory",
]
