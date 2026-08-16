from __future__ import annotations

import os
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models.entities import utc_now

from .models import AgentEnvironment, AgentNodeStatus, StoreBinding
from .runtime import AgentStoreBindingError, ChannelAgentService


FIRST_LAUNCH_EXPERIENCE_VERSION = "1.0"


class FirstLaunchModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    experience_version: Literal["1.0"] = FIRST_LAUNCH_EXPERIENCE_VERSION


class FirstLaunchState(StrEnum):
    FIRST_START = "FIRST_START"
    CHECKING_ENVIRONMENT = "CHECKING_ENVIRONMENT"
    CONNECTING_SERVER = "CONNECTING_SERVER"
    WAITING_CHANNEL_LOGIN = "WAITING_CHANNEL_LOGIN"
    VERIFYING_STORE = "VERIFYING_STORE"
    READY = "READY"
    FAILED = "FAILED"


class DoctorCheckStatus(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"


class DoctorCategory(StrEnum):
    SYSTEM = "SYSTEM"
    AI_CS = "AI_CS"
    CHANNEL = "CHANNEL"
    SAFETY = "SAFETY"


class FirstLaunchTransportStatus(StrEnum):
    READY = "READY"
    WAITING_LOGIN = "WAITING_LOGIN"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class FirstLaunchChromeStatus(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    FAILED = "FAILED"


class FirstLaunchLoginStatus(StrEnum):
    WAITING = "WAITING"
    AUTHENTICATED = "AUTHENTICATED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class FirstLaunchSessionStatus(StrEnum):
    NONE = "NONE"
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"


class FirstLaunchTimelineKind(StrEnum):
    STARTUP = "STARTUP"
    ENVIRONMENT = "ENVIRONMENT"
    CONNECTION = "CONNECTION"
    BROWSER = "BROWSER"
    LOGIN = "LOGIN"
    STORE = "STORE"
    READY = "READY"
    FAILURE = "FAILURE"
    RESET = "RESET"


class FirstLaunchFailureCode(StrEnum):
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
    CHROME_UNAVAILABLE = "CHROME_UNAVAILABLE"
    LOGIN_FAILED = "LOGIN_FAILED"
    STORE_IDENTITY_UNAVAILABLE = "STORE_IDENTITY_UNAVAILABLE"
    STORE_MISMATCH = "STORE_MISMATCH"
    KILL_SWITCH_ENABLED = "KILL_SWITCH_ENABLED"
    AGENT_NOT_READY = "AGENT_NOT_READY"


class FirstLaunchSetupConfig(FirstLaunchModel):
    platform: Literal["pdd"] = "pdd"
    workspace_id: str = Field(
        default="pdd-single-store-workspace",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    profile_name: str = Field(
        default="pdd-pilot-single-store-001",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    )
    credential_reference: str = Field(
        default="credential-ref://pdd/first-launch/browser-session",
        min_length=1,
        max_length=255,
        pattern=r"^(credential|secret)-ref://[A-Za-z0-9._:/-]+$",
        repr=False,
    )
    automatic_login: Literal[False] = False
    message_read_enabled: Literal[False] = False
    send_enabled: Literal[False] = False
    auto_reply: Literal[False] = False
    approval_required: Literal[True] = True


class EnvironmentProbeSnapshot(FirstLaunchModel):
    windows: bool
    chrome_available: bool
    profile_directory_ready: bool
    network_available: bool
    gateway_healthy: bool
    server_connected: bool
    browser_runtime_ready: bool
    transport_status: FirstLaunchTransportStatus
    pilot_mode: bool
    kill_switch_enabled: bool
    approval_required: bool


class EnvironmentDoctorCheck(FirstLaunchModel):
    check_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    category: DoctorCategory
    label: str = Field(min_length=1, max_length=96)
    status: DoctorCheckStatus
    message: str = Field(min_length=1, max_length=240)
    remediation: str | None = Field(default=None, max_length=240)


class EnvironmentDoctorReport(FirstLaunchModel):
    overall: DoctorCheckStatus
    checked_at: AwareDatetime
    checks: tuple[EnvironmentDoctorCheck, ...]


class FirstLaunchWorkspace(FirstLaunchModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    platform: Literal["pdd"] = "pdd"
    profile_name: str = Field(min_length=1, max_length=128)
    created_at: AwareDatetime


class FirstLaunchBrowserObservation(FirstLaunchModel):
    chrome: FirstLaunchChromeStatus
    login: FirstLaunchLoginStatus
    session: FirstLaunchSessionStatus
    checked_at: AwareDatetime
    automatic_login_performed: Literal[False] = False
    message_read_performed: Literal[False] = False
    send_performed: Literal[False] = False


class DiscoveredStoreIdentity(FirstLaunchModel):
    platform: Literal["pdd"] = "pdd"
    store_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    store_name: str = Field(min_length=1, max_length=160)
    account_identity: str = Field(min_length=1, max_length=160)
    source: Literal["READ_ONLY_PAGE_DISCOVERY"] = "READ_ONLY_PAGE_DISCOVERY"


class FirstLaunchFailure(FirstLaunchModel):
    code: FirstLaunchFailureCode
    title: str = Field(min_length=1, max_length=96)
    message: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=240)


class FirstLaunchTimelineEvent(FirstLaunchModel):
    sequence: int = Field(ge=1)
    kind: FirstLaunchTimelineKind
    occurred_at: AwareDatetime
    title: str = Field(min_length=1, max_length=96)
    detail: str = Field(min_length=1, max_length=240)


class FirstLaunchReadyView(FirstLaunchModel):
    node: str
    store: str
    browser: Literal["CONNECTED"] = "CONNECTED"
    session: Literal["VALID"] = "VALID"
    channel: Literal["READY"] = "READY"
    ai: Literal["READY"] = "READY"
    safety: Literal["PILOT MODE"] = "PILOT MODE"
    approval: Literal["REQUIRED"] = "REQUIRED"


class FirstLaunchStatusView(FirstLaunchModel):
    state: FirstLaunchState
    state_history: tuple[FirstLaunchState, ...]
    progress_percent: int = Field(ge=0, le=100)
    platform: Literal["pdd"] = "pdd"
    workspace: FirstLaunchWorkspace | None
    browser: FirstLaunchBrowserObservation
    store: DiscoveredStoreIdentity | None
    doctor: EnvironmentDoctorReport | None
    ready: FirstLaunchReadyView | None
    failure: FirstLaunchFailure | None
    timeline: tuple[FirstLaunchTimelineEvent, ...]
    can_start: bool
    can_reopen_browser: bool
    can_check_login: bool
    can_reset: bool
    configuration_input_required: Literal[False] = False
    automatic_login: Literal[False] = False
    message_read_enabled: Literal[False] = False
    send_enabled: Literal[False] = False


@runtime_checkable
class FirstLaunchEnvironmentProbe(Protocol):
    def snapshot(self) -> EnvironmentProbeSnapshot:
        """Return non-secret, read-only environment facts."""


@runtime_checkable
class FirstLaunchWorkspacePort(Protocol):
    def create(self, config: FirstLaunchSetupConfig) -> FirstLaunchWorkspace:
        """Create an isolated local workspace without opening a browser."""


@runtime_checkable
class FirstLaunchBrowserPort(Protocol):
    real_pdd_connected: bool

    def open(self, workspace: FirstLaunchWorkspace) -> FirstLaunchBrowserObservation:
        """Open the dedicated browser and wait for human login."""

    def check_login(self) -> FirstLaunchBrowserObservation:
        """Read login state without entering credentials or reading messages."""

    def close(self) -> None:
        """Close resources owned by the port without deleting the profile."""


@runtime_checkable
class FirstLaunchStoreIdentityProbe(Protocol):
    real_pdd_connected: bool

    def discover(self) -> DiscoveredStoreIdentity | None:
        """Discover store identity without accepting operator-supplied identity."""


class FakeFirstLaunchEnvironmentProbe:
    def __init__(
        self,
        *,
        windows: bool = True,
        chrome_available: bool = True,
        profile_directory_ready: bool = True,
        network_available: bool = True,
        gateway_healthy: bool = True,
        server_connected: bool = True,
        browser_runtime_ready: bool = True,
        transport_status: FirstLaunchTransportStatus = (
            FirstLaunchTransportStatus.WAITING_LOGIN
        ),
        pilot_mode: bool = True,
        kill_switch_enabled: bool = False,
        approval_required: bool = True,
    ) -> None:
        self.facts = EnvironmentProbeSnapshot(
            windows=windows,
            chrome_available=chrome_available,
            profile_directory_ready=profile_directory_ready,
            network_available=network_available,
            gateway_healthy=gateway_healthy,
            server_connected=server_connected,
            browser_runtime_ready=browser_runtime_ready,
            transport_status=transport_status,
            pilot_mode=pilot_mode,
            kill_switch_enabled=kill_switch_enabled,
            approval_required=approval_required,
        )

    def snapshot(self) -> EnvironmentProbeSnapshot:
        return self.facts


class AgentFirstLaunchEnvironmentProbe:
    """Resolve local system facts and the authoritative kill switch at check time."""

    def __init__(
        self,
        agent: ChannelAgentService,
        *,
        windows: bool,
        chrome_available: bool,
        profile_directory_ready: bool,
        network_available: bool = True,
        gateway_healthy: bool = True,
        server_connected: bool = True,
        browser_runtime_ready: bool = True,
        transport_status: FirstLaunchTransportStatus = (
            FirstLaunchTransportStatus.WAITING_LOGIN
        ),
    ) -> None:
        self._agent = agent
        self._windows = windows
        self._chrome_available = chrome_available
        self._profile_directory_ready = profile_directory_ready
        self._network_available = network_available
        self._gateway_healthy = gateway_healthy
        self._server_connected = server_connected
        self._browser_runtime_ready = browser_runtime_ready
        self._transport_status = transport_status

    def snapshot(self) -> EnvironmentProbeSnapshot:
        try:
            kill_switch = self._agent.status().kill_switch
        except Exception:
            kill_switch = True
        runtime_mode = self._agent.config.safety.runtime_mode
        return EnvironmentProbeSnapshot(
            windows=self._windows,
            chrome_available=self._chrome_available,
            profile_directory_ready=self._profile_directory_ready,
            network_available=self._network_available,
            gateway_healthy=self._gateway_healthy,
            server_connected=self._server_connected,
            browser_runtime_ready=self._browser_runtime_ready,
            transport_status=self._transport_status,
            pilot_mode=runtime_mode
            in {AgentEnvironment.MOCK, AgentEnvironment.PILOT},
            kill_switch_enabled=kill_switch,
            approval_required=True,
        )


class EnvironmentDoctor:
    def __init__(
        self,
        probe: FirstLaunchEnvironmentProbe,
        *,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(probe, FirstLaunchEnvironmentProbe):
            raise TypeError("probe does not implement FirstLaunchEnvironmentProbe")
        self._probe = probe
        self._clock = clock

    def check(self) -> EnvironmentDoctorReport:
        facts = self._probe.snapshot()
        checks = (
            self._required("WINDOWS", DoctorCategory.SYSTEM, "Windows 系统", facts.windows, "当前节点不是受支持的 Windows 环境。", "请在 Windows 节点上运行 Channel Agent。"),
            self._required("CHROME", DoctorCategory.SYSTEM, "Google Chrome", facts.chrome_available, "未找到可用的 Chrome。", "请安装或修复 Google Chrome 后重试。"),
            self._warning("PROFILE_DIRECTORY", DoctorCategory.SYSTEM, "独立 Profile", facts.profile_directory_ready, "独立 Profile 工作区将在启动时创建。", "请确认本地工作区具有写入权限。"),
            self._required("NETWORK", DoctorCategory.SYSTEM, "本地网络", facts.network_available, "网络检查未通过。", "请检查本机网络和代理设置。"),
            self._required("GATEWAY_HEALTH", DoctorCategory.AI_CS, "AI-CS Gateway", facts.gateway_healthy, "AI-CS Gateway 当前不可用。", "请启动或检查 AI-CS 服务。"),
            self._required("SERVER_CONNECTION", DoctorCategory.AI_CS, "Server Connection", facts.server_connected, "无法连接 AI-CS Server。", "请检查 AI-CS 服务状态后重试。"),
            self._required("BROWSER_RUNTIME", DoctorCategory.CHANNEL, "Browser Runtime", facts.browser_runtime_ready, "浏览器运行环境不可用。", "请检查 Chrome 安装与独立 Profile。"),
            self._transport(facts.transport_status),
            self._required("PILOT_MODE", DoctorCategory.SAFETY, "Pilot Mode", facts.pilot_mode, "当前不是 Pilot Mode。", "请恢复 Pilot 安全配置后重试。"),
            self._warning("KILL_SWITCH", DoctorCategory.SAFETY, "Kill Switch", not facts.kill_switch_enabled, "Kill Switch 已开启，设置可以继续，但节点不能进入 Ready。", "确认安全后再由授权人员关闭 Kill Switch。"),
            self._required("APPROVAL_REQUIRED", DoctorCategory.SAFETY, "Manual Approval", facts.approval_required, "人工审批未启用。", "必须启用 Manual Approval。"),
        )
        overall = (
            DoctorCheckStatus.BLOCKED
            if any(item.status is DoctorCheckStatus.BLOCKED for item in checks)
            else DoctorCheckStatus.WARNING
            if any(item.status is DoctorCheckStatus.WARNING for item in checks)
            else DoctorCheckStatus.PASS
        )
        return EnvironmentDoctorReport(
            overall=overall,
            checked_at=self._clock(),
            checks=checks,
        )

    @staticmethod
    def _required(
        check_id: str,
        category: DoctorCategory,
        label: str,
        passed: bool,
        failure_message: str,
        remediation: str,
    ) -> EnvironmentDoctorCheck:
        return EnvironmentDoctorCheck(
            check_id=check_id,
            category=category,
            label=label,
            status=DoctorCheckStatus.PASS if passed else DoctorCheckStatus.BLOCKED,
            message="检查通过。" if passed else failure_message,
            remediation=None if passed else remediation,
        )

    @staticmethod
    def _warning(
        check_id: str,
        category: DoctorCategory,
        label: str,
        passed: bool,
        warning_message: str,
        remediation: str,
    ) -> EnvironmentDoctorCheck:
        return EnvironmentDoctorCheck(
            check_id=check_id,
            category=category,
            label=label,
            status=DoctorCheckStatus.PASS if passed else DoctorCheckStatus.WARNING,
            message="检查通过。" if passed else warning_message,
            remediation=None if passed else remediation,
        )

    @staticmethod
    def _transport(status: FirstLaunchTransportStatus) -> EnvironmentDoctorCheck:
        ready = status is FirstLaunchTransportStatus.READY
        return EnvironmentDoctorCheck(
            check_id="TRANSPORT_STATUS",
            category=DoctorCategory.CHANNEL,
            label="Channel Transport",
            status=DoctorCheckStatus.PASS if ready else DoctorCheckStatus.WARNING,
            message=(
                "Transport 已就绪。"
                if ready
                else "Transport 将在人工登录并确认店铺后就绪。"
            ),
            remediation=None if ready else "请继续完成浏览器人工登录。",
        )


class DedicatedProfileWorkspacePort:
    def __init__(
        self,
        profile_root: Path,
        *,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        self._root = profile_root.expanduser().resolve()
        self._clock = clock

    def create(self, config: FirstLaunchSetupConfig) -> FirstLaunchWorkspace:
        target = (self._root / config.profile_name).resolve()
        if target == self._root or self._root not in target.parents:
            raise ValueError("first-launch workspace escaped the profile root")
        if target.is_symlink():
            raise ValueError("first-launch workspace cannot be a symbolic link")
        target.mkdir(parents=True, exist_ok=True)
        return FirstLaunchWorkspace(
            workspace_id=config.workspace_id,
            profile_name=config.profile_name,
            created_at=self._clock(),
        )


class FakeFirstLaunchWorkspacePort:
    def __init__(self, *, clock: Callable[[], AwareDatetime] = utc_now) -> None:
        self._clock = clock
        self.create_count = 0

    def create(self, config: FirstLaunchSetupConfig) -> FirstLaunchWorkspace:
        self.create_count += 1
        return FirstLaunchWorkspace(
            workspace_id=config.workspace_id,
            profile_name=config.profile_name,
            created_at=self._clock(),
        )


class FakeFirstLaunchBrowserPort:
    real_pdd_connected = False

    def __init__(self, *, clock: Callable[[], AwareDatetime] = utc_now) -> None:
        self._clock = clock
        self.open_count = 0
        self.check_count = 0
        self.close_count = 0
        self.open_available = True
        self.observation = self._observation(
            FirstLaunchChromeStatus.CLOSED,
            FirstLaunchLoginStatus.UNKNOWN,
            FirstLaunchSessionStatus.NONE,
        )

    def open(self, workspace: FirstLaunchWorkspace) -> FirstLaunchBrowserObservation:
        if not workspace.profile_name:
            raise ValueError("workspace profile is required")
        self.open_count += 1
        if not self.open_available:
            self.observation = self._observation(
                FirstLaunchChromeStatus.FAILED,
                FirstLaunchLoginStatus.FAILED,
                FirstLaunchSessionStatus.INVALID,
            )
            return self.observation
        self.observation = self._observation(
            FirstLaunchChromeStatus.OPEN,
            FirstLaunchLoginStatus.WAITING,
            FirstLaunchSessionStatus.PENDING,
        )
        return self.observation

    def check_login(self) -> FirstLaunchBrowserObservation:
        self.check_count += 1
        return self.observation

    def close(self) -> None:
        self.close_count += 1
        self.observation = self._observation(
            FirstLaunchChromeStatus.CLOSED,
            FirstLaunchLoginStatus.UNKNOWN,
            FirstLaunchSessionStatus.NONE,
        )

    def set_login(self, status: FirstLaunchLoginStatus) -> None:
        session = {
            FirstLaunchLoginStatus.AUTHENTICATED: FirstLaunchSessionStatus.VALID,
            FirstLaunchLoginStatus.FAILED: FirstLaunchSessionStatus.INVALID,
            FirstLaunchLoginStatus.WAITING: FirstLaunchSessionStatus.PENDING,
            FirstLaunchLoginStatus.UNKNOWN: FirstLaunchSessionStatus.PENDING,
        }[status]
        self.observation = self._observation(
            FirstLaunchChromeStatus.OPEN,
            status,
            session,
        )

    def fail_open(self) -> None:
        self.open_available = False
        self.observation = self._observation(
            FirstLaunchChromeStatus.FAILED,
            FirstLaunchLoginStatus.FAILED,
            FirstLaunchSessionStatus.INVALID,
        )

    def _observation(
        self,
        chrome: FirstLaunchChromeStatus,
        login: FirstLaunchLoginStatus,
        session: FirstLaunchSessionStatus,
    ) -> FirstLaunchBrowserObservation:
        return FirstLaunchBrowserObservation(
            chrome=chrome,
            login=login,
            session=session,
            checked_at=self._clock(),
        )


class FakeFirstLaunchStoreIdentityProbe:
    real_pdd_connected = False

    def __init__(self, identity: DiscoveredStoreIdentity | None = None) -> None:
        self.identity = identity
        self.discovery_count = 0
        self.operator_identity_input_count = 0
        self.cookie_access_count = 0
        self.message_read_count = 0

    def discover(self) -> DiscoveredStoreIdentity | None:
        self.discovery_count += 1
        return self.identity


_FAILURE_COPY = {
    FirstLaunchFailureCode.ENVIRONMENT_BLOCKED: (
        "环境检查未通过",
        "存在阻止首次启动的环境问题。",
        "请根据 Environment Doctor 的提示修复后重新检查。",
    ),
    FirstLaunchFailureCode.GATEWAY_UNAVAILABLE: (
        "AI-CS 连接失败",
        "当前无法连接健康的 AI-CS Gateway。",
        "请检查 AI-CS 服务是否正在运行。",
    ),
    FirstLaunchFailureCode.CHROME_UNAVAILABLE: (
        "Chrome 启动失败",
        "无法打开独立的浏览器登录窗口。",
        "请检查 Chrome 安装与 Profile 权限后重试。",
    ),
    FirstLaunchFailureCode.LOGIN_FAILED: (
        "拼多多登录未完成",
        "登录状态无效或已失效。",
        "请重新打开浏览器并人工扫码。",
    ),
    FirstLaunchFailureCode.STORE_IDENTITY_UNAVAILABLE: (
        "无法确认店铺身份",
        "登录页面没有提供可验证的店铺身份。",
        "请确认已进入商家聊天页，然后重新检查。",
    ),
    FirstLaunchFailureCode.STORE_MISMATCH: (
        "店铺不匹配",
        "当前登录店铺与节点已有绑定不一致，运行已停止。",
        "请退出错误店铺，并使用正确店铺重新扫码。",
    ),
    FirstLaunchFailureCode.KILL_SWITCH_ENABLED: (
        "Kill Switch 已开启",
        "安全开关正在阻止 Channel 进入 Ready。",
        "确认安全后由授权人员关闭 Kill Switch，再重新开始。",
    ),
    FirstLaunchFailureCode.AGENT_NOT_READY: (
        "节点尚未就绪",
        "浏览器或 Channel Runtime 未能进入 Ready。",
        "请检查状态面板并重新运行检查。",
    ),
}


class FirstLaunchTransitionError(RuntimeError):
    pass


class ChannelAgentFirstLaunchService:
    _ALLOWED_TRANSITIONS = {
        FirstLaunchState.FIRST_START: {FirstLaunchState.CHECKING_ENVIRONMENT},
        FirstLaunchState.CHECKING_ENVIRONMENT: {
            FirstLaunchState.CONNECTING_SERVER,
            FirstLaunchState.FAILED,
        },
        FirstLaunchState.CONNECTING_SERVER: {
            FirstLaunchState.WAITING_CHANNEL_LOGIN,
            FirstLaunchState.FAILED,
        },
        FirstLaunchState.WAITING_CHANNEL_LOGIN: {
            FirstLaunchState.VERIFYING_STORE,
            FirstLaunchState.FAILED,
        },
        FirstLaunchState.VERIFYING_STORE: {
            FirstLaunchState.READY,
            FirstLaunchState.FAILED,
        },
        FirstLaunchState.READY: {FirstLaunchState.FIRST_START},
        FirstLaunchState.FAILED: {FirstLaunchState.FIRST_START},
    }
    _PROGRESS = {
        FirstLaunchState.FIRST_START: 0,
        FirstLaunchState.CHECKING_ENVIRONMENT: 18,
        FirstLaunchState.CONNECTING_SERVER: 36,
        FirstLaunchState.WAITING_CHANNEL_LOGIN: 58,
        FirstLaunchState.VERIFYING_STORE: 78,
        FirstLaunchState.READY: 100,
        FirstLaunchState.FAILED: 100,
    }

    def __init__(
        self,
        agent: ChannelAgentService,
        setup: FirstLaunchSetupConfig,
        doctor: EnvironmentDoctor,
        workspace: FirstLaunchWorkspacePort,
        browser: FirstLaunchBrowserPort,
        store_identity: FirstLaunchStoreIdentityProbe,
        *,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if browser.real_pdd_connected or store_identity.real_pdd_connected:
            raise ValueError("First Launch Foundation forbids a real PDD connection")
        self._agent = agent
        self._setup = setup
        self._doctor = doctor
        self._workspace_port = workspace
        self._browser_port = browser
        self._store_probe = store_identity
        self._clock = clock
        self._lock = RLock()
        self._state = FirstLaunchState.FIRST_START
        self._state_history = [FirstLaunchState.FIRST_START]
        self._doctor_report: EnvironmentDoctorReport | None = None
        self._workspace: FirstLaunchWorkspace | None = None
        self._browser = FirstLaunchBrowserObservation(
            chrome=FirstLaunchChromeStatus.CLOSED,
            login=FirstLaunchLoginStatus.UNKNOWN,
            session=FirstLaunchSessionStatus.NONE,
            checked_at=clock(),
        )
        self._store: DiscoveredStoreIdentity | None = None
        self._failure: FirstLaunchFailure | None = None
        self._events: list[FirstLaunchTimelineEvent] = []
        self._binding_created_by_wizard = False

    def doctor(self) -> EnvironmentDoctorReport:
        return self._doctor.check()

    def status(self) -> FirstLaunchStatusView:
        with self._lock:
            ready = self._ready_view() if self._state is FirstLaunchState.READY else None
            return FirstLaunchStatusView(
                state=self._state,
                state_history=tuple(self._state_history),
                progress_percent=self._PROGRESS[self._state],
                workspace=self._workspace,
                browser=self._browser,
                store=self._store,
                doctor=self._doctor_report,
                ready=ready,
                failure=self._failure,
                timeline=tuple(self._events[-20:]),
                can_start=self._state is FirstLaunchState.FIRST_START,
                can_reopen_browser=self._state
                is FirstLaunchState.WAITING_CHANNEL_LOGIN,
                can_check_login=self._state
                is FirstLaunchState.WAITING_CHANNEL_LOGIN,
                can_reset=self._state
                in {FirstLaunchState.FAILED, FirstLaunchState.READY},
            )

    def start(self) -> FirstLaunchStatusView:
        with self._lock:
            if self._state is not FirstLaunchState.FIRST_START:
                raise FirstLaunchTransitionError("first launch has already started")
            self._event(
                FirstLaunchTimelineKind.STARTUP,
                "Agent 启动",
                "首次启动向导已开始。",
            )
            self._apply_managed_pilot_configuration()
            self._set_state(FirstLaunchState.CHECKING_ENVIRONMENT)
            self._doctor_report = self._doctor.check()
            if self._doctor_report.overall is DoctorCheckStatus.BLOCKED:
                blocked = {
                    item.check_id for item in self._doctor_report.checks
                    if item.status is DoctorCheckStatus.BLOCKED
                }
                code = (
                    FirstLaunchFailureCode.GATEWAY_UNAVAILABLE
                    if blocked & {"GATEWAY_HEALTH", "SERVER_CONNECTION"}
                    else FirstLaunchFailureCode.CHROME_UNAVAILABLE
                    if blocked & {"CHROME", "BROWSER_RUNTIME"}
                    else FirstLaunchFailureCode.ENVIRONMENT_BLOCKED
                )
                return self._fail(code)
            self._event(
                FirstLaunchTimelineKind.ENVIRONMENT,
                "环境检查通过",
                "系统、AI-CS、Channel 与 Safety 检查已完成。",
            )
            self._set_state(FirstLaunchState.CONNECTING_SERVER)
            self._event(
                FirstLaunchTimelineKind.CONNECTION,
                "AI-CS 连接通过",
                "Gateway Health 与 Server Connection 可用。",
            )
            try:
                self._workspace = self._workspace_port.create(self._setup)
                self._browser = self._browser_port.open(self._workspace)
            except Exception:
                return self._fail(FirstLaunchFailureCode.CHROME_UNAVAILABLE)
            if self._browser.chrome is not FirstLaunchChromeStatus.OPEN:
                return self._fail(FirstLaunchFailureCode.CHROME_UNAVAILABLE)
            self._event(
                FirstLaunchTimelineKind.BROWSER,
                "浏览器已打开",
                f"独立 Profile {self._setup.profile_name} 已准备。",
            )
            self._set_state(FirstLaunchState.WAITING_CHANNEL_LOGIN)
            self._event(
                FirstLaunchTimelineKind.LOGIN,
                "等待拼多多登录",
                "请在独立 Chrome 窗口中人工扫码。",
            )
            return self.status()

    def reopen_browser(self) -> FirstLaunchStatusView:
        with self._lock:
            self._require(FirstLaunchState.WAITING_CHANNEL_LOGIN)
            assert self._workspace is not None
            try:
                self._browser = self._browser_port.open(self._workspace)
            except Exception:
                return self._fail(FirstLaunchFailureCode.CHROME_UNAVAILABLE)
            if self._browser.chrome is not FirstLaunchChromeStatus.OPEN:
                return self._fail(FirstLaunchFailureCode.CHROME_UNAVAILABLE)
            self._event(
                FirstLaunchTimelineKind.BROWSER,
                "浏览器已重新打开",
                "仍需人工完成扫码登录。",
            )
            return self.status()

    def check_login(self) -> FirstLaunchStatusView:
        with self._lock:
            self._require(FirstLaunchState.WAITING_CHANNEL_LOGIN)
            try:
                self._browser = self._browser_port.check_login()
            except Exception:
                return self._fail(FirstLaunchFailureCode.LOGIN_FAILED)
            if self._browser.login in {
                FirstLaunchLoginStatus.WAITING,
                FirstLaunchLoginStatus.UNKNOWN,
            }:
                if not self._events or self._events[-1].title != "仍在等待人工登录":
                    self._event(
                        FirstLaunchTimelineKind.LOGIN,
                        "仍在等待人工登录",
                        "未检测到已验证的登录会话。",
                    )
                return self.status()
            if (
                self._browser.login is not FirstLaunchLoginStatus.AUTHENTICATED
                or self._browser.session is not FirstLaunchSessionStatus.VALID
            ):
                return self._fail(FirstLaunchFailureCode.LOGIN_FAILED)
            self._event(
                FirstLaunchTimelineKind.LOGIN,
                "人工登录成功",
                "已检测到有效会话，未执行自动登录。",
            )
            self._set_state(FirstLaunchState.VERIFYING_STORE)
            return self._verify_store()

    def reset(self) -> FirstLaunchStatusView:
        with self._lock:
            if self._state not in {FirstLaunchState.FAILED, FirstLaunchState.READY}:
                raise FirstLaunchTransitionError("first launch cannot reset now")
            was_ready = self._state is FirstLaunchState.READY
            agent_status = self._agent.status()
            if agent_status.node.status not in {
                AgentNodeStatus.INIT,
                AgentNodeStatus.STOPPED,
            }:
                self._agent.stop()
            if self._binding_created_by_wizard and (was_ready or self._failure is not None):
                try:
                    self._agent.unbind_store()
                except AgentStoreBindingError:
                    pass
            self._browser_port.close()
            self._state = FirstLaunchState.FIRST_START
            self._state_history = [FirstLaunchState.FIRST_START]
            self._doctor_report = None
            self._workspace = None
            self._store = None
            self._failure = None
            self._binding_created_by_wizard = False
            self._browser = FirstLaunchBrowserObservation(
                chrome=FirstLaunchChromeStatus.CLOSED,
                login=FirstLaunchLoginStatus.UNKNOWN,
                session=FirstLaunchSessionStatus.NONE,
                checked_at=self._clock(),
            )
            self._events = []
            self._event(
                FirstLaunchTimelineKind.RESET,
                "首次启动已重置",
                "可以重新执行环境检查与人工登录。",
            )
            return self.status()

    def _verify_store(self) -> FirstLaunchStatusView:
        try:
            identity = self._store_probe.discover()
        except Exception:
            identity = None
        if identity is None:
            return self._fail(FirstLaunchFailureCode.STORE_IDENTITY_UNAVAILABLE)
        existing = self._agent.status()
        if existing.store_id is not None and existing.store_id != identity.store_id:
            if existing.node.status not in {
                AgentNodeStatus.INIT,
                AgentNodeStatus.STOPPED,
            }:
                self._agent.stop()
            return self._fail(FirstLaunchFailureCode.STORE_MISMATCH)
        self._store = identity
        if existing.store_id is None:
            try:
                self._agent.bind_store(
                    StoreBinding(
                        store_id=identity.store_id,
                        store_name=identity.store_name,
                        credential_reference=self._setup.credential_reference,
                    )
                )
                self._binding_created_by_wizard = True
            except AgentStoreBindingError:
                return self._fail(FirstLaunchFailureCode.STORE_MISMATCH)
        self._event(
            FirstLaunchTimelineKind.STORE,
            "店铺绑定成功",
            f"已通过只读身份发现绑定 {identity.store_name}。",
        )
        if self._agent.status().kill_switch:
            return self._fail(FirstLaunchFailureCode.KILL_SWITCH_ENABLED)
        agent_status = self._agent.start()
        if (
            agent_status.node.status is not AgentNodeStatus.ONLINE
            or agent_status.store_id != identity.store_id
        ):
            code = (
                FirstLaunchFailureCode.KILL_SWITCH_ENABLED
                if agent_status.kill_switch
                else FirstLaunchFailureCode.AGENT_NOT_READY
            )
            return self._fail(code)
        self._set_state(FirstLaunchState.READY)
        self._failure = None
        self._event(
            FirstLaunchTimelineKind.READY,
            "Channel Agent 已就绪",
            "AI、Browser、Store、Channel 与 Safety 状态已确认。",
        )
        return self.status()

    def _apply_managed_pilot_configuration(self) -> None:
        config = self._agent.config
        if config.safety.runtime_mode is not AgentEnvironment.MOCK:
            return
        payload = config.model_dump(mode="python")
        payload["safety"]["runtime_mode"] = AgentEnvironment.PILOT
        payload["safety"]["dry_run"] = True
        if payload["channel"].get("credential_reference") is None:
            payload["channel"]["credential_reference"] = (
                self._setup.credential_reference
            )
        self._agent.reload_config(type(config).model_validate(payload))

    def _ready_view(self) -> FirstLaunchReadyView:
        assert self._store is not None
        status = self._agent.status()
        return FirstLaunchReadyView(
            node=status.node.node_name,
            store=self._store.store_name,
        )

    def _fail(self, code: FirstLaunchFailureCode) -> FirstLaunchStatusView:
        title, message, action = _FAILURE_COPY[code]
        self._set_state(FirstLaunchState.FAILED)
        self._failure = FirstLaunchFailure(
            code=code,
            title=title,
            message=message,
            action=action,
        )
        self._event(
            FirstLaunchTimelineKind.FAILURE,
            title,
            message,
        )
        return self.status()

    def _require(self, expected: FirstLaunchState) -> None:
        if self._state is not expected:
            raise FirstLaunchTransitionError(
                f"action requires first-launch state {expected.value}"
            )

    def _set_state(self, state: FirstLaunchState) -> None:
        if state not in self._ALLOWED_TRANSITIONS[self._state]:
            raise FirstLaunchTransitionError(
                f"invalid first-launch transition {self._state.value}->{state.value}"
            )
        self._state = state
        if not self._state_history or self._state_history[-1] is not state:
            self._state_history.append(state)

    def _event(
        self,
        kind: FirstLaunchTimelineKind,
        title: str,
        detail: str,
    ) -> None:
        self._events.append(
            FirstLaunchTimelineEvent(
                sequence=len(self._events) + 1,
                kind=kind,
                occurred_at=self._clock(),
                title=title,
                detail=detail,
            )
        )


def build_default_first_launch_service(
    agent: ChannelAgentService,
) -> ChannelAgentFirstLaunchService:
    config = agent.config
    binding = config.channel.store_binding
    reference = (
        config.channel.credential_reference
        or (binding.credential_reference if binding is not None else None)
        or "credential-ref://pdd/first-launch/browser-session"
    )
    setup = FirstLaunchSetupConfig(credential_reference=reference)
    probe = AgentFirstLaunchEnvironmentProbe(
        agent,
        windows=os.name == "nt",
        chrome_available=config.browser.chrome_path.is_file(),
        profile_directory_ready=config.browser.profile_root.exists(),
    )
    return ChannelAgentFirstLaunchService(
        agent,
        setup,
        EnvironmentDoctor(probe),
        DedicatedProfileWorkspacePort(config.browser.profile_root),
        FakeFirstLaunchBrowserPort(),
        FakeFirstLaunchStoreIdentityProbe(),
    )


__all__ = [
    "FIRST_LAUNCH_EXPERIENCE_VERSION",
    "ChannelAgentFirstLaunchService",
    "AgentFirstLaunchEnvironmentProbe",
    "DedicatedProfileWorkspacePort",
    "DiscoveredStoreIdentity",
    "DoctorCategory",
    "DoctorCheckStatus",
    "EnvironmentDoctor",
    "EnvironmentDoctorCheck",
    "EnvironmentDoctorReport",
    "EnvironmentProbeSnapshot",
    "FakeFirstLaunchBrowserPort",
    "FakeFirstLaunchEnvironmentProbe",
    "FakeFirstLaunchStoreIdentityProbe",
    "FakeFirstLaunchWorkspacePort",
    "FirstLaunchBrowserObservation",
    "FirstLaunchBrowserPort",
    "FirstLaunchChromeStatus",
    "FirstLaunchEnvironmentProbe",
    "FirstLaunchFailure",
    "FirstLaunchFailureCode",
    "FirstLaunchLoginStatus",
    "FirstLaunchReadyView",
    "FirstLaunchSessionStatus",
    "FirstLaunchSetupConfig",
    "FirstLaunchState",
    "FirstLaunchStatusView",
    "FirstLaunchStoreIdentityProbe",
    "FirstLaunchTimelineEvent",
    "FirstLaunchTimelineKind",
    "FirstLaunchTransitionError",
    "FirstLaunchTransportStatus",
    "FirstLaunchWorkspace",
    "FirstLaunchWorkspacePort",
    "build_default_first_launch_service",
]
