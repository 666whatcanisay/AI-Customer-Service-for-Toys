from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Event, RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .assistant_events import AssistantEventPoller
from .binding import AgentBindingStore, atomic_write_bytes
from .browser import (
    BrowserControlError,
    BrowserSessionState,
    BrowserSessionStatus,
    ChannelAgentBrowserManager,
)
from .client import ChannelEngineClient
from .config import (
    AgentConfigError,
    ChannelAgentConfig,
    load_agent_config,
    save_agent_config,
)
from .contract import AgentRuntimeStatus
from .desktop import DesktopAssistantServer
from .edge_pdd_observe import PDDLocalReferenceTokenizer, PDDWorkspaceObservationMapper
from .edge_spool import DurableEdgeSpool
from .identity import AgentIdentityStatus
from .logger import SafeAgentLogger
from .observation_runtime import (
    NoopAssistantEventRuntime,
    ObserveOnlyRuntimeComponent,
    PersistAckObservationForwarder,
    PersistOnlyObservationForwarder,
)
from .observation_stages import ObservationStage
from .pdd_conversation_capture import DurablePDDConversationCaptureStore
from .pdd_login import (
    PDDLoginObservation,
    PDDLoginObservationAdapter,
    PDDLoginObservationError,
    PDDLoginState,
)
from .pdd_observer import PDDMessageObserver, PDDObserverRunner
from .pdd_page_port import ReplayPDDPageReadPort, load_pdd_replay_fixture
from .pdd_readonly_driver import (
    EvidenceBackedPDDReadOnlyDriver,
    build_replay_observer_evidence,
    load_pdd_observer_evidence,
)
from .retention import TransientBusinessDataPolicy
from .runtime import AgentRuntimeSnapshot, ChannelAgentRuntime, build_runtime
from .security import (
    WindowsDeviceCredentialStore,
    WindowsDPAPITransientPayloadProtector,
)
from .version import AGENT_VERSION

WINDOWS_CLIENT_VERSION = "2.0.0rc5"
WINDOWS_STATE_VERSION = "1.0"
WINDOWS_STATE_READ_ATTEMPTS = 8
WINDOWS_STATE_READ_INITIAL_DELAY_SECONDS = 0.02
WINDOWS_STATE_READ_MAX_DELAY_SECONDS = 0.25
_VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:(?:-?rc\.?)([1-9]\d*))?$"
)


class WindowsClientError(RuntimeError):
    pass


class WindowsStateError(WindowsClientError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class WindowsClientProcessStatus(StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class AgentExperienceStatus(StrEnum):
    INSTALLED = "INSTALLED"
    CONNECTED = "CONNECTED"
    BOUND = "BOUND"
    STORE_SELECTED = "STORE_SELECTED"
    PDD_READY = "PDD_READY"
    ASSISTANT_READY = "ASSISTANT_READY"
    DEGRADED = "DEGRADED"


class WindowsClientState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = WINDOWS_STATE_VERSION
    client_version: str = WINDOWS_CLIENT_VERSION
    agent_version: str = AGENT_VERSION
    pid: int | None = Field(default=None, ge=1)
    process_status: WindowsClientProcessStatus = WindowsClientProcessStatus.STOPPED
    experience_status: AgentExperienceStatus = AgentExperienceStatus.INSTALLED
    runtime_status: AgentRuntimeStatus = AgentRuntimeStatus.STOPPED
    identity_status: AgentIdentityStatus = AgentIdentityStatus.UNBOUND
    production_eligible: bool = False
    agent_id: str | None = None
    device_id: str | None = None
    user_id: str | None = None
    store_id: str | None = None
    store_ids: tuple[str, ...] = ()
    authorized_store_ids: tuple[str, ...] = ()
    active_store_id: str | None = None
    binding_revision: int = Field(default=0, ge=0)
    config_status: str = "UNKNOWN"
    config_path: str | None = None
    browser_enabled: bool = False
    browser_id: str | None = None
    browser_status: BrowserSessionStatus = BrowserSessionStatus.STOPPED
    browser_pid: int | None = Field(default=None, ge=1)
    browser_profile_reference: str | None = None
    browser_generation: int = Field(default=0, ge=0)
    browser_last_seen: AwareDatetime | None = None
    browser_error_code: str | None = None
    pdd_login_observation_enabled: bool = False
    pdd_login_state: PDDLoginState | None = None
    pdd_store_reference: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    pdd_store_id: str | None = None
    pdd_login_observed_at: AwareDatetime | None = None
    pdd_login_reason_code: str | None = None
    message_observation_enabled: bool = False
    observer_mode: str = "OBSERVE_ONLY"
    observer_status: str = "DISABLED"
    observer_last_error_code: str | None = None
    desktop_ui_enabled: bool = True
    desktop_ui_status: str = "STOPPED"
    desktop_ui_url: str | None = None
    last_heartbeat: AwareDatetime | None = None
    last_error_code: str | None = None
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class WindowsStateStore:
    """Atomic, credential-free local status file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()

    def load(self) -> WindowsClientState:
        with self._lock:
            if not self.path.exists():
                return WindowsClientState()
            last_transient: PermissionError | FileNotFoundError | None = None
            for attempt in range(WINDOWS_STATE_READ_ATTEMPTS):
                try:
                    raw = self.path.read_bytes()
                    break
                except (PermissionError, FileNotFoundError) as exc:
                    last_transient = exc
                    if attempt + 1 < WINDOWS_STATE_READ_ATTEMPTS:
                        time.sleep(
                            min(
                                WINDOWS_STATE_READ_INITIAL_DELAY_SECONDS * (2**attempt),
                                WINDOWS_STATE_READ_MAX_DELAY_SECONDS,
                            )
                        )
            else:
                raise WindowsStateError(
                    "Windows Agent state is temporarily unavailable",
                    error_code="LOCAL_STATE_TEMPORARILY_LOCKED",
                ) from last_transient
            try:
                if len(raw) > 1024 * 1024:
                    raise WindowsStateError(
                        "Windows Agent state exceeds one MiB",
                        error_code="LOCAL_STATE_TOO_LARGE",
                    )
                return WindowsClientState.model_validate_json(raw)
            except WindowsStateError:
                raise
            except Exception as exc:
                raise WindowsStateError(
                    "Windows Agent state is invalid",
                    error_code="LOCAL_STATE_INVALID",
                ) from exc

    def save(self, state: WindowsClientState) -> None:
        with self._lock:
            payload = state.model_dump_json(indent=2).encode("utf-8") + b"\n"
            try:
                atomic_write_bytes(self.path, payload)
            except OSError as exc:
                raise WindowsStateError(
                    "Windows Agent state cannot be saved",
                    error_code="LOCAL_STATE_WRITE_FAILED",
                ) from exc


class WindowsAgentHost:
    """Runs the existing ChannelAgentRuntime inside a Windows process boundary."""

    def __init__(
        self,
        config_path: str | Path,
        data_root: str | Path,
        *,
        runtime_factory: Callable[..., ChannelAgentRuntime] = build_runtime,
        browser_factory: Callable[
            [ChannelAgentConfig, Path], ChannelAgentBrowserManager
        ]
        | None = None,
        pdd_login_factory: Callable[
            [ChannelAgentConfig, Path, ChannelAgentBrowserManager],
            PDDLoginObservationAdapter,
        ]
        | None = None,
        desktop_factory: Callable[
            [ChannelAgentConfig, Path], DesktopAssistantServer
        ]
        | None = None,
        observation_factory: Callable[
            [
                ChannelAgentConfig,
                Path,
                BrowserSessionState,
                str,
                str,
                DesktopAssistantServer,
                Callable[[str], None],
            ],
            ObserveOnlyRuntimeComponent,
        ]
        | None = None,
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
        self.reload_request = self.data_root / "runtime" / "reload.request"
        self.observer_restart_request = (
            self.data_root / "runtime" / "pdd-observer-restart.request"
        )
        self._runtime_factory = runtime_factory
        self._browser_factory = browser_factory or self._build_browser_manager
        self._pdd_login_factory = pdd_login_factory or self._build_pdd_login_adapter
        self._desktop_factory = desktop_factory or self._build_desktop_assistant
        self._observation_factory = (
            observation_factory or self._build_observation_component
        )
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
            return self._run_recovery_ui(stop_event)
        self.stop_request.unlink(missing_ok=True)
        self.observer_restart_request.unlink(missing_ok=True)
        self.data_root.joinpath("logs").mkdir(parents=True, exist_ok=True)
        runtime = self._runtime_factory(
            config,
            log_path=str(self.data_root / "logs" / "channel-agent.jsonl"),
        )
        desktop = (
            self._desktop_factory(config, self.data_root)
            if config.desktop_ui_enabled
            else None
        )
        desktop_url: str | None = None
        browser = self._browser_factory(config, self.data_root)
        browser_state = browser.browser_status()
        pdd_login = (
            self._pdd_login_factory(config, self.data_root, browser)
            if config.pdd_login_observation_enabled
            else None
        )
        pdd_observation: PDDLoginObservation | None = None
        observer: ObserveOnlyRuntimeComponent | None = None
        observer_init_failed = False
        observer_error: dict[str, str | None] = {"code": None}
        pdd_poll_error: dict[str, str | None] = {"code": None}

        def record_observer_error(code: str) -> None:
            observer_error["code"] = code[:120]

        def reported_observer_error() -> str | None:
            return observer_error["code"] or pdd_poll_error["code"]
        self._save_snapshot(
            runtime.snapshot(),
            WindowsClientProcessStatus.STARTING,
            config_path=self.config_path,
            browser_enabled=config.browser_enabled,
            browser_state=browser_state,
            pdd_login_enabled=config.pdd_login_observation_enabled,
            desktop_ui_enabled=config.desktop_ui_enabled,
            desktop_ui_url=desktop_url,
            runtime_mode=config.runtime_mode,
            message_observation_enabled=config.message_observation_enabled,
            observer_mode=config.observer_mode,
            observer_status=self._observer_status(config, None, pdd_observation),
        )
        reload_requested = False
        preserve_browser_on_reload = False
        try:
            snapshot = runtime.start(background_heartbeat=True)
            if desktop is not None:
                desktop_url = desktop.start()
            self._commit_pending_configuration(config)
            if config.browser_enabled:
                try:
                    browser_state = browser.open_browser()
                except BrowserControlError:
                    browser_state = browser.browser_status()
            if pdd_login is not None:
                try:
                    pdd_observation = pdd_login.launch()
                    pdd_poll_error["code"] = None
                except (PDDLoginObservationError, BrowserControlError) as exc:
                    # A transient CDP/session-file read must not terminate the
                    # desktop Agent and close the operator's authenticated Edge.
                    # Keep the browser alive and retry from the normal poll loop.
                    pdd_poll_error["code"] = (
                        "PDD_LOGIN_POLL_" + type(exc).__name__.upper()
                    )[:120]
                    browser_state = browser.browser_status()
                else:
                    browser_state = browser.browser_status()
            if config.message_observation_enabled:
                observer, observer_init_failed = self._start_observer_if_ready(
                    config=config,
                    browser_state=browser_state,
                    pdd_observation=pdd_observation,
                    snapshot=snapshot,
                    desktop=desktop,
                    existing=observer,
                    initialization_failed=observer_init_failed,
                    error_sink=record_observer_error,
                )
            self._save_snapshot(
                snapshot,
                self._process_status(snapshot, config.browser_enabled, browser_state),
                browser_enabled=config.browser_enabled,
                browser_state=browser_state,
                pdd_login_enabled=config.pdd_login_observation_enabled,
                pdd_observation=pdd_observation,
                desktop_ui_enabled=config.desktop_ui_enabled,
                desktop_ui_url=desktop_url,
                runtime_mode=config.runtime_mode,
                message_observation_enabled=config.message_observation_enabled,
                observer_mode=config.observer_mode,
                observer_status=self._observer_status(
                    config, observer, pdd_observation,
                    initialization_failed=observer_init_failed,
                ),
                observer_error_code=reported_observer_error(),
            )
            next_pdd_observation = 0.0
            while not stop_event.wait(self._poll_interval):
                if self.stop_request.exists():
                    stop_event.set()
                    break
                if self.reload_request.exists():
                    reload_payload = self._read_reload_request()
                    reload_requested = True
                    preserve_browser_on_reload = bool(
                        reload_payload.get("preserve_browser", True)
                    )
                    stop_event.set()
                    break
                if self.observer_restart_request.exists():
                    identity = snapshot.identity
                    restart_ready = bool(
                        observer is not None
                        and pdd_observation is not None
                        and pdd_observation.login_state
                        is PDDLoginState.CUSTOMER_SERVICE_READY
                        and pdd_observation.page_ready
                        and identity is not None
                        and identity.status is AgentIdentityStatus.ACTIVE
                        and identity.effective_active_store_id is not None
                    )
                    try:
                        if observer is None:
                            raise WindowsClientError(
                                "PDD observer runtime is not available"
                            )
                        observer.restart_observer(page_ready=restart_ready)
                        observer_error["code"] = None
                    except Exception as exc:
                        record_observer_error(
                            ("OBSERVER_RESTART_" + type(exc).__name__.upper())[:120]
                        )
                    finally:
                        self.observer_restart_request.unlink(missing_ok=True)
                snapshot = runtime.snapshot()
                browser_state = browser.browser_status()
                if (
                    config.browser_enabled
                    and browser_state.status
                    in {BrowserSessionStatus.DEGRADED, BrowserSessionStatus.FAILED}
                    and not browser_state.automatic_recovery_attempted
                ):
                    try:
                        browser_state = browser.recover()
                    except BrowserControlError:
                        browser_state = browser.browser_status()
                if pdd_login is not None and time.monotonic() >= next_pdd_observation:
                    try:
                        pdd_observation = pdd_login.observe()
                        pdd_poll_error["code"] = None
                    except (PDDLoginObservationError, BrowserControlError) as exc:
                        # Preserve the last known-good observation and browser.
                        # The next two-second poll is allowed to recover naturally.
                        pdd_poll_error["code"] = (
                            "PDD_LOGIN_POLL_" + type(exc).__name__.upper()
                        )[:120]
                    browser_state = browser.browser_status()
                    next_pdd_observation = time.monotonic() + 2.0
                if config.message_observation_enabled:
                    observer, observer_init_failed = self._start_observer_if_ready(
                        config=config,
                        browser_state=browser_state,
                        pdd_observation=pdd_observation,
                        snapshot=snapshot,
                        desktop=desktop,
                        existing=observer,
                        initialization_failed=observer_init_failed,
                        error_sink=record_observer_error,
                    )
                self._save_snapshot(
                    snapshot,
                    self._process_status(snapshot, config.browser_enabled, browser_state),
                    browser_enabled=config.browser_enabled,
                    browser_state=browser_state,
                    pdd_login_enabled=config.pdd_login_observation_enabled,
                    pdd_observation=pdd_observation,
                    desktop_ui_enabled=config.desktop_ui_enabled,
                    desktop_ui_url=desktop_url,
                    runtime_mode=config.runtime_mode,
                    message_observation_enabled=config.message_observation_enabled,
                    observer_mode=config.observer_mode,
                    observer_status=self._observer_status(
                        config, observer, pdd_observation,
                        initialization_failed=observer_init_failed,
                    ),
                    observer_error_code=reported_observer_error(),
                )
            if observer is not None:
                observer.close()
                observer = None
            browser_stop_failed = False
            if not (reload_requested and preserve_browser_on_reload):
                try:
                    browser_state = browser.close_browser()
                except BrowserControlError:
                    browser_stop_failed = True
                    browser_state = browser.browser_status()
            else:
                browser_state = browser.browser_status()
            if reload_requested and preserve_browser_on_reload and desktop is not None:
                desktop.prepare_reload_handoff()
            final = runtime.stop()
            self._save_snapshot(
                final,
                (
                    WindowsClientProcessStatus.FAILED
                    if browser_stop_failed
                    else WindowsClientProcessStatus.STOPPED
                ),
                pid=None,
                browser_enabled=config.browser_enabled,
                browser_state=browser_state,
                pdd_login_enabled=config.pdd_login_observation_enabled,
                pdd_observation=pdd_observation,
                desktop_ui_enabled=config.desktop_ui_enabled,
                desktop_ui_url=None,
                runtime_mode=config.runtime_mode,
                message_observation_enabled=config.message_observation_enabled,
                observer_mode=config.observer_mode,
                observer_status="STOPPED",
                observer_error_code=reported_observer_error(),
            )
            return 4 if browser_stop_failed else 0
        except Exception as exc:
            current = runtime.snapshot()
            rolled_back = self._rollback_pending_configuration()
            if rolled_back:
                reload_requested = True
                preserve_browser_on_reload = True
            if not preserve_browser_on_reload:
                try:
                    browser_state = browser.close_browser()
                except BrowserControlError:
                    browser_state = browser.browser_status()
            self._save_snapshot(
                current,
                WindowsClientProcessStatus.FAILED,
                error_code=type(exc).__name__.upper(),
                browser_enabled=config.browser_enabled,
                browser_state=browser_state,
                pdd_login_enabled=config.pdd_login_observation_enabled,
                pdd_observation=pdd_observation,
                desktop_ui_enabled=config.desktop_ui_enabled,
                desktop_ui_url=desktop_url,
                runtime_mode=config.runtime_mode,
                message_observation_enabled=config.message_observation_enabled,
                observer_mode=config.observer_mode,
                observer_status="FAILED",
                observer_error_code=(reported_observer_error() or type(exc).__name__.upper()),
            )
            return 4
        finally:
            if observer is not None:
                observer.close()
            runtime.close()
            browser.close_resources()
            if pdd_login is not None:
                pdd_login.close_resources()
            if desktop is not None:
                desktop.stop()
            if config.runtime_mode != "SIMULATOR" and not reload_requested:
                TransientBusinessDataPolicy().purge_on_safe_stop(self.data_root)
            self.stop_request.unlink(missing_ok=True)
            self.reload_request.unlink(missing_ok=True)
            self.observer_restart_request.unlink(missing_ok=True)

    def request_stop(self) -> None:
        self.stop_request.parent.mkdir(parents=True, exist_ok=True)
        self.stop_request.write_text("stop\n", encoding="ascii")

    def _run_recovery_ui(self, stop_event: Event) -> int:
        """Keep the local diagnosis UI available even with a broken config."""

        desktop = DesktopAssistantServer(
            data_root=self.data_root,
            config_path=self.config_path,
            static_root=self._desktop_static_root(),
        )
        try:
            desktop.start()
            while not stop_event.wait(self._poll_interval):
                if self.stop_request.exists() or self.reload_request.exists():
                    break
        finally:
            desktop.stop()
            self.stop_request.unlink(missing_ok=True)
            self.reload_request.unlink(missing_ok=True)
        return 1

    def _read_reload_request(self) -> dict[str, object]:
        try:
            value = json.loads(self.reload_request.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    def _commit_pending_configuration(self, config: ChannelAgentConfig) -> None:
        pending = self.data_root / "runtime" / "config-reload-pending.json"
        if not pending.is_file():
            return
        target = self.data_root / "runtime" / "config-backups" / "agent.last-known-good.json"
        save_agent_config(target, config)
        pending.unlink(missing_ok=True)

    def _rollback_pending_configuration(self) -> bool:
        pending = self.data_root / "runtime" / "config-reload-pending.json"
        backup = self.data_root / "runtime" / "config-backups" / "agent.previous.json"
        if not pending.is_file() or not backup.is_file():
            return False
        try:
            previous = load_agent_config(backup)
            save_agent_config(self.config_path, previous)
            pending.unlink(missing_ok=True)
            restart = self.data_root / "runtime" / "restart-agent.request"
            restart.parent.mkdir(parents=True, exist_ok=True)
            restart.write_text("rollback-preserve-assistant\n", encoding="ascii")
            return True
        except AgentConfigError:
            return False

    def _save_snapshot(
        self,
        snapshot: AgentRuntimeSnapshot,
        process_status: WindowsClientProcessStatus,
        *,
        config_path: Path | None = None,
        pid: int | None | object = ...,
        error_code: str | None = None,
        browser_enabled: bool = False,
        browser_state: BrowserSessionState | None = None,
        pdd_login_enabled: bool = False,
        pdd_observation: PDDLoginObservation | None = None,
        desktop_ui_enabled: bool = True,
        desktop_ui_url: str | None = None,
        runtime_mode: str = "MOCK",
        message_observation_enabled: bool = False,
        observer_mode: str = "OBSERVE_ONLY",
        observer_status: str = "DISABLED",
        observer_error_code: str | None = None,
    ) -> None:
        actual_pid = os.getpid() if pid is ... else pid
        if snapshot.identity is not None:
            self.binding_store.save_identity(snapshot.identity)
        self.state_store.save(
            WindowsClientState(
                pid=actual_pid,
                process_status=process_status,
                experience_status=self._experience_status(
                    snapshot,
                    process_status,
                    pdd_observation,
                    desktop_ui_url,
                    runtime_mode,
                ),
                runtime_status=snapshot.status,
                identity_status=snapshot.identity_status,
                production_eligible=snapshot.production_eligible,
                agent_id=snapshot.agent_id,
                device_id=snapshot.device_id,
                user_id=snapshot.user_id,
                store_id=snapshot.store_id,
                store_ids=snapshot.store_ids,
                authorized_store_ids=(
                    snapshot.identity.authorized_stores
                    if snapshot.identity is not None
                    else snapshot.store_ids
                ),
                active_store_id=(
                    snapshot.identity.effective_active_store_id
                    if snapshot.identity is not None
                    else snapshot.store_id
                ),
                binding_revision=snapshot.binding_revision,
                config_status="VALID",
                config_path=str(config_path or self.config_path),
                browser_enabled=browser_enabled,
                browser_id=(browser_state.browser_id if browser_state else None),
                browser_status=(
                    browser_state.status
                    if browser_state is not None
                    else BrowserSessionStatus.STOPPED
                ),
                browser_pid=(browser_state.pid if browser_state else None),
                browser_profile_reference=(
                    browser_state.public_view(self.data_root)["profile_reference"]
                    if browser_state is not None
                    else None
                ),
                browser_generation=(browser_state.generation if browser_state else 0),
                browser_last_seen=(browser_state.last_seen if browser_state else None),
                browser_error_code=(
                    browser_state.last_error_code if browser_state else None
                ),
                pdd_login_observation_enabled=pdd_login_enabled,
                pdd_login_state=(
                    pdd_observation.login_state if pdd_observation else None
                ),
                pdd_store_reference=(
                    pdd_observation.store_reference if pdd_observation else None
                ),
                pdd_store_id=(
                    pdd_observation.store_identity.store_id
                    if pdd_observation is not None
                    and pdd_observation.store_identity is not None
                    else None
                ),
                pdd_login_observed_at=(
                    pdd_observation.observed_at if pdd_observation else None
                ),
                pdd_login_reason_code=(
                    pdd_observation.reason_code if pdd_observation else None
                ),
                message_observation_enabled=message_observation_enabled,
                observer_mode=observer_mode,
                observer_status=observer_status,
                observer_last_error_code=observer_error_code,
                desktop_ui_enabled=desktop_ui_enabled,
                desktop_ui_status=("RUNNING" if desktop_ui_url else "STOPPED"),
                desktop_ui_url=desktop_ui_url,
                last_heartbeat=snapshot.last_heartbeat,
                last_error_code=(
                    error_code
                    or observer_error_code
                    or (browser_state.last_error_code if browser_state else None)
                    or snapshot.last_error_code
                ),
                updated_at=self._clock(),
            )
        )

    @staticmethod
    def _experience_status(
        snapshot: AgentRuntimeSnapshot,
        process_status: WindowsClientProcessStatus,
        pdd_observation: PDDLoginObservation | None,
        desktop_ui_url: str | None,
        runtime_mode: str,
    ) -> AgentExperienceStatus:
        if process_status in {
            WindowsClientProcessStatus.DEGRADED,
            WindowsClientProcessStatus.FAILED,
        }:
            return AgentExperienceStatus.DEGRADED
        if snapshot.status is not AgentRuntimeStatus.ONLINE:
            return AgentExperienceStatus.INSTALLED
        identity = snapshot.identity
        if identity is None or identity.status is AgentIdentityStatus.UNBOUND:
            return AgentExperienceStatus.CONNECTED
        active_store = identity.effective_active_store_id
        if active_store is None:
            return AgentExperienceStatus.BOUND
        if runtime_mode == "SIMULATOR" and desktop_ui_url:
            return AgentExperienceStatus.ASSISTANT_READY
        if pdd_observation is None:
            return AgentExperienceStatus.STORE_SELECTED
        if pdd_observation.login_state is not PDDLoginState.CUSTOMER_SERVICE_READY:
            return AgentExperienceStatus.STORE_SELECTED
        # The observed PDD identifier is a platform_store_id while active_store is
        # AI-CS's internal store_code.  Their relationship is verified through the
        # server-owned store_platform_binding; comparing the two strings here would
        # incorrectly degrade every correctly mapped store.
        if desktop_ui_url:
            return AgentExperienceStatus.ASSISTANT_READY
        return AgentExperienceStatus.PDD_READY

    @staticmethod
    def _process_status(
        snapshot: AgentRuntimeSnapshot,
        browser_enabled: bool = False,
        browser_state: BrowserSessionState | None = None,
    ) -> WindowsClientProcessStatus:
        if browser_enabled and browser_state is not None and browser_state.status in {
            BrowserSessionStatus.DEGRADED,
            BrowserSessionStatus.FAILED,
        }:
            return WindowsClientProcessStatus.DEGRADED
        if snapshot.status is AgentRuntimeStatus.ONLINE:
            return WindowsClientProcessStatus.RUNNING
        if snapshot.status is AgentRuntimeStatus.DEGRADED:
            return WindowsClientProcessStatus.DEGRADED
        if snapshot.status is AgentRuntimeStatus.STOPPED:
            return WindowsClientProcessStatus.STOPPED
        return WindowsClientProcessStatus.STARTING

    def _start_observer_if_ready(
        self,
        *,
        config: ChannelAgentConfig,
        browser_state: BrowserSessionState,
        pdd_observation: PDDLoginObservation | None,
        snapshot: AgentRuntimeSnapshot,
        desktop: DesktopAssistantServer | None,
        existing: ObserveOnlyRuntimeComponent | None,
        initialization_failed: bool,
        error_sink: Callable[[str], None],
    ) -> tuple[ObserveOnlyRuntimeComponent | None, bool]:
        offline_replay = config.development_profile == "OFFLINE_REPLAY"
        page_ready = offline_replay or bool(
            pdd_observation is not None
            and pdd_observation.login_state is PDDLoginState.CUSTOMER_SERVICE_READY
            and pdd_observation.page_ready
            and pdd_observation.store_identity is not None
        )
        identity = snapshot.identity
        active_store = (
            identity.effective_active_store_id if identity is not None else None
        )
        identity_ready = bool(
            identity is not None
            and identity.status is AgentIdentityStatus.ACTIVE
            and active_store is not None
        )
        if existing is not None:
            existing.set_page_ready(page_ready and identity_ready)
            return existing, initialization_failed
        if initialization_failed or not page_ready or not identity_ready or desktop is None:
            return None, initialization_failed
        assert active_store is not None
        if offline_replay:
            assert config.pdd_replay_platform_store_id is not None
            platform_store_id = config.pdd_replay_platform_store_id
        else:
            assert pdd_observation is not None
            assert pdd_observation.store_identity is not None
            platform_store_id = pdd_observation.store_identity.store_id
        try:
            component = self._observation_factory(
                config,
                self.data_root,
                browser_state,
                active_store,
                platform_store_id,
                desktop,
                error_sink,
            )
            component.start(page_ready=True)
            return component, False
        except Exception as exc:
            error_sink(("OBSERVER_INIT_" + type(exc).__name__.upper())[:120])
            return None, True

    @staticmethod
    def _observer_status(
        config: ChannelAgentConfig,
        observer: ObserveOnlyRuntimeComponent | None,
        pdd_observation: PDDLoginObservation | None,
        *,
        initialization_failed: bool = False,
    ) -> str:
        if not config.message_observation_enabled:
            return "DISABLED"
        if initialization_failed:
            return "FAILED"
        if observer is not None and observer.observing:
            return "OBSERVING"
        if (
            observer is not None
            and observer.observer.stop_reason
            == "PDD_OBSERVER_SESSION_LIMIT_REACHED"
        ):
            return "SESSION_LIMIT_REACHED"
        if config.development_profile == "OFFLINE_REPLAY":
            return "WAITING_IDENTITY"
        if (
            pdd_observation is None
            or pdd_observation.login_state is not PDDLoginState.CUSTOMER_SERVICE_READY
        ):
            return "WAITING_PAGE"
        return "WAITING_IDENTITY"

    def _build_observation_component(
        self,
        config: ChannelAgentConfig,
        data_root: Path,
        browser_state: BrowserSessionState,
        store_id: str,
        platform_store_id: str,
        desktop: DesktopAssistantServer,
        error_sink: Callable[[str], None],
    ) -> ObserveOnlyRuntimeComponent:
        if config.observer_mode != "OBSERVE_ONLY":
            raise WindowsClientError("only OBSERVE_ONLY is available in ChannelAgent rc4")
        if config.development_profile == "OFFLINE_REPLAY":
            fixture_path = config.pdd_replay_fixture_path
            if fixture_path is None:
                raise WindowsClientError("PDD replay fixture is not configured")
            if not fixture_path.is_absolute():
                fixture_path = (self.config_path.parent / fixture_path).resolve()
            fixture = load_pdd_replay_fixture(fixture_path)
            evidence = build_replay_observer_evidence(fixture)
            driver = EvidenceBackedPDDReadOnlyDriver(
                store_id=store_id,
                platform_store_id=platform_store_id,
                evidence=evidence,
                page_port=ReplayPDDPageReadPort(fixture),
            )
        else:
            evidence_path = config.pdd_observation_evidence_path
            if evidence_path is None:
                raise WindowsClientError("PDD selector evidence is not configured")
            if not evidence_path.is_absolute():
                evidence_path = (self.config_path.parent / evidence_path).resolve()
            evidence = load_pdd_observer_evidence(evidence_path)
            driver = EvidenceBackedPDDReadOnlyDriver(
                profile_path=browser_state.profile_path,
                store_id=store_id,
                platform_store_id=platform_store_id,
                evidence=evidence,
                allow_navigation=config.pdd_conversation_navigation_enabled,
            )
        reference_tokenizer = None
        if config.development_profile != "OFFLINE_REPLAY":
            if config.device_credential_reference is None:
                raise WindowsClientError(
                    "REAL_PDD privacy tokenization requires the bound device credential"
                )
            device_key = WindowsDeviceCredentialStore().acquire(
                config.device_credential_reference
            ).for_signing()
            reference_tokenizer = PDDLocalReferenceTokenizer(
                hmac.new(
                    device_key,
                    b"AI-CS PDD local business reference token v1",
                    hashlib.sha256,
                ).digest()
            )
        spool_path = data_root / "runtime" / "observe-only-spool.sqlite3"
        spool = DurableEdgeSpool(
            spool_path,
            WindowsDPAPITransientPayloadProtector(),
        )
        capture_store = (
            DurablePDDConversationCaptureStore(spool_path)
            if driver.navigation_enabled
            else None
        )
        client = None
        if config.observation_stage.allows(ObservationStage.HOST_INGEST):
            client = ChannelEngineClient(config)
            forwarder = PersistAckObservationForwarder(client, spool)
        else:
            forwarder = PersistOnlyObservationForwarder(spool)
        mapper = PDDWorkspaceObservationMapper(
            agent_id=config.agent_id,
            device_id=config.device_id,
            provider_id=(
                "recorded-replay"
                if config.development_profile == "OFFLINE_REPLAY"
                else "real-pdd-readonly"
            ),
            reference_tokenizer=reference_tokenizer,
        )
        observer = PDDMessageObserver(
            driver=driver,
            mapper=mapper,
            spool=spool,
            forward=forwarder,
            diagnostic=lambda code, _summary, _details: error_sink(code),
            capture_store=capture_store,
            stage=config.observation_stage,
        )
        runner = PDDObserverRunner(
            observer,
            error_sink=error_sink,
            session_event_sink=error_sink,
            maximum_session_seconds=30 * 60,
            warning_seconds=25 * 60,
        )
        assistant_events = (
            AssistantEventPoller(
                client,
                desktop.event_journal,
                error_sink=error_sink,
            )
            if client is not None
            else NoopAssistantEventRuntime()
        )
        return ObserveOnlyRuntimeComponent(
            forwarder=forwarder,
            observer=runner,
            assistant_events=assistant_events,
            stage=config.observation_stage,
            error_sink=error_sink,
            close_resources=(client.close if client is not None else lambda: None),
        )

    @staticmethod
    def _build_browser_manager(
        config: ChannelAgentConfig, data_root: Path
    ) -> ChannelAgentBrowserManager:
        return ChannelAgentBrowserManager(
            agent_id=config.agent_id,
            data_root=data_root,
            enabled=config.browser_enabled,
            logger=SafeAgentLogger(data_root / "logs" / "browser-runtime.jsonl"),
        )

    @staticmethod
    def _build_pdd_login_adapter(
        config: ChannelAgentConfig,
        data_root: Path,
        browser: ChannelAgentBrowserManager,
    ) -> PDDLoginObservationAdapter:
        if (
            config.pdd_login_url is None
            or config.pdd_customer_service_url is None
        ):
            raise WindowsClientError("PDD observation URLs are not configured")
        return PDDLoginObservationAdapter(
            agent_id=config.agent_id,
            data_root=data_root,
            login_url=config.pdd_login_url,
            customer_service_url=config.pdd_customer_service_url,
            browser=browser,
            logger=SafeAgentLogger(data_root / "logs" / "pdd-login-observer.jsonl"),
        )

    @staticmethod
    def _build_desktop_assistant(
        config: ChannelAgentConfig, data_root: Path
    ) -> DesktopAssistantServer:
        packaged_root = WindowsAgentHost._desktop_static_root()
        static_root = packaged_root
        manual_pdd_browser = ChannelAgentBrowserManager(
            agent_id=config.agent_id,
            data_root=data_root,
            enabled=True,
            logger=SafeAgentLogger(
                data_root / "logs" / "pdd-manual-window-browser.jsonl"
            ),
        )
        manual_pdd_login = PDDLoginObservationAdapter(
            agent_id=config.agent_id,
            data_root=data_root,
            login_url="https://mms.pinduoduo.com/login/",
            customer_service_url=(
                "https://mms.pinduoduo.com/chat-merchant/index.html#/"
            ),
            browser=manual_pdd_browser,
            logger=SafeAgentLogger(
                data_root / "logs" / "pdd-manual-window-login.jsonl"
            ),
        )

        def project_pdd_window(
            observation: PDDLoginObservation,
        ) -> dict[str, object]:
            browser_state = manual_pdd_browser.browser_status()
            return {
                "status": (
                    "READY"
                    if observation.login_state
                    is PDDLoginState.CUSTOMER_SERVICE_READY
                    else "OPENING"
                ),
                "browser_status": browser_state.status.value,
                "pdd_login_state": observation.login_state.value,
            }

        def launch_pdd_window() -> dict[str, object]:
            return project_pdd_window(manual_pdd_login.launch())

        def refresh_pdd_window() -> dict[str, object]:
            return project_pdd_window(manual_pdd_login.observe())

        def close_pdd_window_resources() -> None:
            manual_pdd_login.close_resources()
            manual_pdd_browser.close_resources()

        def select_active_store(store_reference: str, reason: str) -> dict[str, object]:
            state = WindowsStateStore(
                data_root / "runtime" / "channel-agent-state.json"
            ).load()
            observed_store = state.pdd_store_id
            if config.runtime_mode == "SIMULATOR":
                observed_store = store_reference
            if observed_store is None:
                raise WindowsClientError("PDD store identity is not available")
            client = ChannelEngineClient(config)
            try:
                client.fetch_config()
                identity = client.select_active_store(
                    store_reference,
                    observed_store,
                    reason=reason,
                )
            finally:
                client.close()
            return {
                "status": "STORE_SELECTED",
                "authorized_store_ids": list(identity.authorized_stores),
                "active_store_id": identity.effective_active_store_id,
                "binding_revision": identity.binding_revision,
            }

        return DesktopAssistantServer(
            data_root=data_root,
            config_path=data_root / "config" / "agent.json",
            static_root=static_root,
            port=config.desktop_ui_port,
            platform_origin=config.ai_cs_platform_url,
            active_store_handler=select_active_store,
            pdd_workspace_launch_handler=launch_pdd_window,
            pdd_workspace_status_handler=refresh_pdd_window,
            pdd_workspace_close_handler=close_pdd_window_resources,
            platform_proxy_mode=config.ai_cs_platform_proxy_mode,
            platform_ca_certificate=config.ai_cs_ca_certificate_path,
        )

    @staticmethod
    def _desktop_static_root() -> Path | None:
        packaged_root = Path(sys.argv[0]).resolve().parent.parent / "ui"
        return packaged_root if packaged_root.is_dir() else None


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
            f'set "AI_CS_CHANNEL_AGENT_DATA_ROOT={data_path}"\r\n'
            f'start "" "{executable_path}" --background\r\n'
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


def _version_tuple(value: str) -> tuple[int, int, int, int, int]:
    match = _VERSION.fullmatch(value)
    if match is None:
        raise WindowsClientError("upgrade version must be semantic x.y.z or x.y.zrcN")
    major, minor, patch, release_candidate = match.groups()
    return (
        int(major),
        int(minor),
        int(patch),
        1 if release_candidate is None else 0,
        int(release_candidate or 0),
    )


__all__ = [
    "WINDOWS_CLIENT_VERSION",
    "UpgradeCheckResult",
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
