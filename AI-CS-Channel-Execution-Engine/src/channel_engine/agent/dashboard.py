from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field

from channel_engine.models.entities import utc_now

from .models import (
    AgentComponentStatus,
    AgentEnvironment,
    AgentLifecycleEvent,
    AgentLifecycleStage,
    AgentModel,
    AgentNodeStatus,
    AgentServerConnection,
    AgentStoreStatus,
)
from .runtime import ChannelAgentService


CHANNEL_AGENT_DASHBOARD_VERSION = "1.0"


class DashboardStoreState(StrEnum):
    CONNECTED = "CONNECTED"
    WAITING_LOGIN = "WAITING_LOGIN"
    DISCONNECTED = "DISCONNECTED"


class DashboardBrowserSessionState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


class DashboardLoginState(StrEnum):
    UNKNOWN = "UNKNOWN"
    WAITING_LOGIN = "WAITING_LOGIN"
    AUTHENTICATED = "AUTHENTICATED"
    DISCONNECTED = "DISCONNECTED"


class DashboardTimelineKind(StrEnum):
    STARTUP = "STARTUP"
    CONNECTION = "CONNECTION"
    LOGIN = "LOGIN"
    STATUS = "STATUS"
    ERROR = "ERROR"
    STOP = "STOP"


class DashboardAgentSummary(AgentModel):
    status: Literal["HEALTHY", "DEGRADED", "OFFLINE", "STOPPED"]
    ready: bool
    version: str
    environment: AgentEnvironment


class DashboardNodeSummary(AgentModel):
    node_id: str
    node_name: str
    status: AgentNodeStatus
    last_heartbeat: AwareDatetime | None


class DashboardAICSView(AgentModel):
    status: AgentComponentStatus
    connection: AgentServerConnection
    endpoint: str = Field(min_length=1, max_length=512)
    reason_code: str


class DashboardBrowserView(AgentModel):
    chrome_status: AgentComponentStatus
    profile: str = Field(min_length=1, max_length=1024)
    session: DashboardBrowserSessionState
    login: DashboardLoginState
    reason_code: str


class DashboardChannelView(AgentModel):
    platform: Literal["pdd"] = "pdd"
    status: AgentComponentStatus
    reason_code: str


class DashboardStoreView(AgentModel):
    platform: Literal["pdd"] = "pdd"
    store_id: str | None = None
    store_name: str | None = None
    state: DashboardStoreState


class DashboardSafetyView(AgentModel):
    runtime_mode: AgentEnvironment
    pilot_mode: bool
    manual_approval: Literal[True] = True
    kill_switch: bool
    dry_run: bool
    send_control_available: Literal[False] = False


class DashboardTimelineItem(AgentModel):
    sequence: int = Field(ge=1)
    kind: DashboardTimelineKind
    title: str = Field(min_length=1, max_length=96)
    occurred_at: AwareDatetime
    successful: bool
    reason_code: str


class ChannelAgentDashboard(AgentModel):
    dashboard_version: Literal["1.0"] = CHANNEL_AGENT_DASHBOARD_VERSION
    generated_at: AwareDatetime
    agent: DashboardAgentSummary
    node: DashboardNodeSummary
    ai_cs: DashboardAICSView
    browser: DashboardBrowserView
    channel: DashboardChannelView
    store: DashboardStoreView
    safety: DashboardSafetyView
    timeline: tuple[DashboardTimelineItem, ...]
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


_EVENT_PRESENTATION = {
    AgentLifecycleStage.ENVIRONMENT_CHECK: (
        DashboardTimelineKind.STARTUP,
        "运行环境检查",
    ),
    AgentLifecycleStage.SERVER_CONNECT: (
        DashboardTimelineKind.CONNECTION,
        "连接 AI-CS",
    ),
    AgentLifecycleStage.CONFIG_LOAD: (
        DashboardTimelineKind.STARTUP,
        "加载节点配置",
    ),
    AgentLifecycleStage.BROWSER_CHECK: (
        DashboardTimelineKind.LOGIN,
        "检查浏览器与登录状态",
    ),
    AgentLifecycleStage.CHANNEL_CHECK: (
        DashboardTimelineKind.CONNECTION,
        "检查渠道运行时",
    ),
    AgentLifecycleStage.READY: (
        DashboardTimelineKind.STATUS,
        "节点就绪状态更新",
    ),
    AgentLifecycleStage.STOP: (
        DashboardTimelineKind.STOP,
        "停止节点",
    ),
}


class ChannelAgentDashboardProjector:
    """Read-only product projection over the existing Agent runtime."""

    def __init__(
        self,
        service: ChannelAgentService,
        *,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        self._service = service
        self._clock = clock

    def snapshot(self, *, timeline_limit: int = 12) -> ChannelAgentDashboard:
        if not 1 <= timeline_limit <= 50:
            raise ValueError("dashboard timeline limit must be between 1 and 50")
        status = self._service.status()
        health = self._service.health()
        config = self._service.config
        browser_session, login = self._browser_state(
            status.node.status,
            status.browser_status.status,
            status.channel_status.status,
            status.store_status,
        )
        store_state = self._store_state(
            status.node.status,
            status.store_status,
            status.browser_status.status,
            status.channel_status.status,
        )
        agent_label = {
            "healthy": "HEALTHY",
            "degraded": "DEGRADED",
            "offline": "OFFLINE",
            "stopped": "STOPPED",
        }[health.status]
        return ChannelAgentDashboard(
            generated_at=self._clock(),
            agent=DashboardAgentSummary(
                status=agent_label,  # type: ignore[arg-type]
                ready=health.ready,
                version=status.node.version,
                environment=status.node.environment,
            ),
            node=DashboardNodeSummary(
                node_id=status.node.node_id,
                node_name=status.node.node_name,
                status=status.node.status,
                last_heartbeat=status.node.last_heartbeat,
            ),
            ai_cs=DashboardAICSView(
                status=status.server_status.status,
                connection=status.node.server_connection,
                endpoint=config.server.server_url,
                reason_code=status.server_status.reason_code,
            ),
            browser=DashboardBrowserView(
                chrome_status=status.browser_status.status,
                profile=str(config.browser.profile_root),
                session=browser_session,
                login=login,
                reason_code=status.browser_status.reason_code,
            ),
            channel=DashboardChannelView(
                status=status.channel_status.status,
                reason_code=status.channel_status.reason_code,
            ),
            store=DashboardStoreView(
                store_id=status.store_id,
                store_name=status.store_name,
                state=store_state,
            ),
            safety=DashboardSafetyView(
                runtime_mode=status.node.environment,
                pilot_mode=status.node.environment is AgentEnvironment.PILOT,
                kill_switch=status.kill_switch,
                dry_run=status.dry_run,
            ),
            timeline=self.timeline(limit=timeline_limit),
            config_fingerprint=status.config_fingerprint,
        )

    def timeline(self, *, limit: int = 12) -> tuple[DashboardTimelineItem, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("dashboard timeline limit must be between 1 and 50")
        events = self._service.lifecycle_events()[-limit:]
        return tuple(self._timeline_item(event) for event in reversed(events))

    @staticmethod
    def _browser_state(
        node: AgentNodeStatus,
        browser: AgentComponentStatus,
        channel: AgentComponentStatus,
        store: AgentStoreStatus,
    ) -> tuple[DashboardBrowserSessionState, DashboardLoginState]:
        if node is AgentNodeStatus.INIT:
            return (
                DashboardBrowserSessionState.NOT_STARTED,
                DashboardLoginState.DISCONNECTED,
            )
        if node is AgentNodeStatus.STOPPED or browser is AgentComponentStatus.STOPPED:
            return (
                DashboardBrowserSessionState.STOPPED,
                DashboardLoginState.DISCONNECTED,
            )
        if browser is AgentComponentStatus.HEALTHY:
            return (
                DashboardBrowserSessionState.ACTIVE,
                (
                    DashboardLoginState.AUTHENTICATED
                    if channel is AgentComponentStatus.HEALTHY
                    and store is AgentStoreStatus.BOUND
                    else DashboardLoginState.UNKNOWN
                ),
            )
        if browser in {
            AgentComponentStatus.UNAVAILABLE,
            AgentComponentStatus.BLOCKED,
        }:
            return (
                DashboardBrowserSessionState.DEGRADED,
                DashboardLoginState.WAITING_LOGIN,
            )
        return DashboardBrowserSessionState.DEGRADED, DashboardLoginState.UNKNOWN

    @staticmethod
    def _store_state(
        node: AgentNodeStatus,
        store: AgentStoreStatus,
        browser: AgentComponentStatus,
        channel: AgentComponentStatus,
    ) -> DashboardStoreState:
        if (
            store is not AgentStoreStatus.BOUND
            or node is AgentNodeStatus.STOPPED
        ):
            return DashboardStoreState.DISCONNECTED
        if (
            browser is AgentComponentStatus.HEALTHY
            and channel is AgentComponentStatus.HEALTHY
        ):
            return DashboardStoreState.CONNECTED
        return DashboardStoreState.WAITING_LOGIN

    @staticmethod
    def _timeline_item(event: AgentLifecycleEvent) -> DashboardTimelineItem:
        kind, title = _EVENT_PRESENTATION[event.stage]
        if not event.successful:
            kind = DashboardTimelineKind.ERROR
            title = f"{title}异常"
        return DashboardTimelineItem(
            sequence=event.sequence,
            kind=kind,
            title=title,
            occurred_at=event.occurred_at,
            successful=event.successful,
            reason_code=event.reason_code,
        )


__all__ = [
    "CHANNEL_AGENT_DASHBOARD_VERSION",
    "ChannelAgentDashboard",
    "ChannelAgentDashboardProjector",
    "DashboardAICSView",
    "DashboardAgentSummary",
    "DashboardBrowserSessionState",
    "DashboardBrowserView",
    "DashboardChannelView",
    "DashboardLoginState",
    "DashboardNodeSummary",
    "DashboardSafetyView",
    "DashboardStoreState",
    "DashboardStoreView",
    "DashboardTimelineItem",
    "DashboardTimelineKind",
]
