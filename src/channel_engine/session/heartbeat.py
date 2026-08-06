from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import Event, Lock, Thread

from channel_engine.channel import AdapterHealthStatus
from channel_engine.models.entities import new_id, utc_now
from channel_engine.reliability import ComponentHealth, ProbeReading

from .manager import ChannelInstanceManager
from .models import (
    ChannelInstanceStatus,
    ChannelSessionStatus,
    SessionHeartbeat,
    SessionHeartbeatReport,
)
from .persistence import ChannelSessionStore


class SessionHeartbeatScheduler:
    def __init__(
        self,
        manager: ChannelInstanceManager,
        store: ChannelSessionStore,
        browser_probe: Callable[[], ProbeReading],
        gateway_probe: Callable[[], ProbeReading],
        *,
        interval_seconds: float = 30.0,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if interval_seconds < 0.01 or interval_seconds > 300:
            raise ValueError("heartbeat interval must be between 0.01 and 300 seconds")
        self._manager = manager
        self._store = store
        self._browser_probe = browser_probe
        self._gateway_probe = gateway_probe
        self.interval_seconds = interval_seconds
        self._clock = clock
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self.run_count = 0
        self.last_report: SessionHeartbeatReport | None = None

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def run_once(self) -> SessionHeartbeatReport:
        cycle_id = new_id("session-heartbeat-cycle")
        browser = self._safe_probe(self._browser_probe, "BROWSER_PROBE_FAILED")
        gateway = self._safe_probe(self._gateway_probe, "GATEWAY_PROBE_FAILED")
        views = self._manager.heartbeat_all()
        records: list[SessionHeartbeat] = []
        for view in views:
            session = view.session
            adapter_health = view.adapter_health
            session_healthy = (
                session is not None
                and session.status is ChannelSessionStatus.CONNECTED
            )
            adapter_component = {
                AdapterHealthStatus.HEALTHY: ComponentHealth.HEALTHY,
                AdapterHealthStatus.DEGRADED: ComponentHealth.DEGRADED,
                AdapterHealthStatus.UNHEALTHY: ComponentHealth.UNHEALTHY,
            }[adapter_health]
            values = (
                adapter_component,
                browser.health,
                gateway.health,
                (
                    ComponentHealth.HEALTHY
                    if session_healthy
                    else ComponentHealth.UNHEALTHY
                ),
            )
            overall = (
                ComponentHealth.UNHEALTHY
                if ComponentHealth.UNHEALTHY in values
                else (
                    ComponentHealth.DEGRADED
                    if ComponentHealth.DEGRADED in values
                    else ComponentHealth.HEALTHY
                )
            )
            reason_code = self._reason(
                session_healthy,
                adapter_component,
                browser,
                gateway,
            )
            if (
                overall is not ComponentHealth.HEALTHY
                and view.instance.status is ChannelInstanceStatus.CONNECTED
            ):
                self._manager.mark_degraded(
                    view.instance.instance_id,
                    reason_code,
                )
            records.append(
                SessionHeartbeat(
                    heartbeat_id=new_id("session-heartbeat"),
                    cycle_id=cycle_id,
                    instance_id=view.instance.instance_id,
                    session_id=session.session_id if session is not None else None,
                    session_status=session.status if session is not None else None,
                    adapter_health=adapter_health,
                    browser_health=browser.health,
                    gateway_health=gateway.health,
                    overall=overall,
                    reason_code=reason_code,
                    checked_at=self._clock(),
                )
            )
        overall = (
            ComponentHealth.UNHEALTHY
            if not records
            or any(item.overall is ComponentHealth.UNHEALTHY for item in records)
            else (
                ComponentHealth.DEGRADED
                if any(item.overall is ComponentHealth.DEGRADED for item in records)
                else ComponentHealth.HEALTHY
            )
        )
        report = SessionHeartbeatReport(
            cycle_id=cycle_id,
            instances=tuple(records),
            overall=overall,
            checked_at=(
                max(item.checked_at for item in records)
                if records
                else self._clock()
            ),
        )
        self._store.append_heartbeats(report.instances)
        with self._lock:
            self.run_count += 1
            self.last_report = report
        return report

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self._stop_event.clear()
            self._thread = Thread(
                target=self._loop,
                name="channel-session-heartbeat",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return False
            self._stop_event.set()
        thread.join(timeout=min(5.0, self.interval_seconds * 2 + 0.1))
        with self._lock:
            self._thread = None
        return True

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                pass
            self._stop_event.wait(self.interval_seconds)

    @staticmethod
    def _safe_probe(
        probe: Callable[[], ProbeReading], reason_code: str
    ) -> ProbeReading:
        try:
            return probe()
        except Exception:
            return ProbeReading(
                health=ComponentHealth.UNHEALTHY,
                available=False,
                reason_code=reason_code,
            )

    @staticmethod
    def _reason(
        session_healthy: bool,
        adapter: ComponentHealth,
        browser: ProbeReading,
        gateway: ProbeReading,
    ) -> str:
        if not session_healthy:
            return "SESSION_NOT_CONNECTED"
        if adapter is not ComponentHealth.HEALTHY:
            return "ADAPTER_HEALTH_DEGRADED"
        if browser.health is not ComponentHealth.HEALTHY:
            return "BROWSER_HEALTH_DEGRADED"
        if gateway.health is not ComponentHealth.HEALTHY:
            return "GATEWAY_HEALTH_DEGRADED"
        return "SESSION_RUNTIME_HEALTHY"


class ChannelSessionRuntimeHealthProbe:
    def __init__(self, scheduler: SessionHeartbeatScheduler) -> None:
        self._scheduler = scheduler

    def __call__(self) -> ProbeReading:
        report = self._scheduler.run_once()
        return ProbeReading(
            health=report.overall,
            available=(
                bool(report.instances)
                and all(
                    item.overall is ComponentHealth.HEALTHY
                    for item in report.instances
                )
            ),
            reason_code=(
                "CHANNEL_SESSIONS_HEALTHY"
                if report.overall is ComponentHealth.HEALTHY
                else "CHANNEL_SESSIONS_DEGRADED"
            ),
        )


__all__ = [
    "ChannelSessionRuntimeHealthProbe",
    "SessionHeartbeatScheduler",
]
