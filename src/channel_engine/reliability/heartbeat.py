from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from threading import Lock
from time import perf_counter
from typing import Protocol

from sqlalchemy import text as sql_text

from channel_engine.models.entities import new_id, utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork

from .browser import BrowserManager
from .models import (
    ComponentHealth,
    ComponentHeartbeat,
    HeartbeatReport,
    ProbeReading,
    RuntimeComponent,
)
from .persistence import RuntimeReliabilityStore


class HealthProbe(Protocol):
    def __call__(self) -> ProbeReading: ...


class StaticHealthProbe:
    def __init__(
        self,
        health: ComponentHealth = ComponentHealth.HEALTHY,
        reason_code: str = "FAKE_COMPONENT_HEALTHY",
    ) -> None:
        self.health = health
        self.reason_code = reason_code

    def __call__(self) -> ProbeReading:
        return ProbeReading(
            health=self.health,
            available=self.health is not ComponentHealth.UNHEALTHY,
            reason_code=self.reason_code,
        )

    def set(
        self, health: ComponentHealth, reason_code: str
    ) -> None:
        self.health = health
        self.reason_code = reason_code

    def recover(self) -> bool:
        self.health = ComponentHealth.HEALTHY
        self.reason_code = "FAKE_COMPONENT_RECOVERED"
        return True


class BrowserHealthProbe:
    def __init__(self, browser: BrowserManager) -> None:
        self._browser = browser

    def __call__(self) -> ProbeReading:
        status = self._browser.health_check()
        return ProbeReading(
            health=status.health,
            available=status.process_running and status.page_available,
            process_running=status.process_running,
            page_available=status.page_available,
            reason_code=status.reason_code,
        )


class StorageHealthProbe:
    def __init__(
        self, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    ) -> None:
        self._uow_factory = uow_factory

    def __call__(self) -> ProbeReading:
        with self._uow_factory() as uow:
            assert uow.session is not None
            value = uow.session.scalar(sql_text("SELECT 1"))
        if value != 1:
            return ProbeReading(
                health=ComponentHealth.UNHEALTHY,
                available=False,
                reason_code="SQLITE_HEALTH_CHECK_FAILED",
            )
        return ProbeReading(
            health=ComponentHealth.HEALTHY,
            available=True,
            reason_code="SQLITE_HEALTHY",
        )


class HeartbeatManager:
    REQUIRED_COMPONENTS = frozenset(RuntimeComponent)

    def __init__(
        self,
        runtime_id: str,
        store: RuntimeReliabilityStore,
        probes: Mapping[RuntimeComponent, HealthProbe],
        *,
        clock: Callable = utc_now,
    ) -> None:
        if set(probes) != self.REQUIRED_COMPONENTS:
            missing = sorted(
                item.value for item in self.REQUIRED_COMPONENTS.difference(probes)
            )
            extra = sorted(
                item.value for item in set(probes).difference(self.REQUIRED_COMPONENTS)
            )
            raise ValueError(
                f"heartbeat probes must cover exactly all components; "
                f"missing={missing}, extra={extra}"
            )
        self.runtime_id = runtime_id
        self._store = store
        self._probes = dict(probes)
        self._clock = clock
        self._clock_lock = Lock()
        self._last_checked_at: datetime | None = None

    def run_once(self) -> HeartbeatReport:
        cycle_id = new_id("heartbeat-cycle")
        components: list[ComponentHeartbeat] = []
        for component in RuntimeComponent:
            started = perf_counter()
            try:
                reading = self._probes[component]()
            except Exception as exc:
                reading = ProbeReading(
                    health=ComponentHealth.UNHEALTHY,
                    available=False,
                    reason_code=f"{component.value}_{type(exc).__name__.upper()}",
                )
            latency_ms = max(0.0, (perf_counter() - started) * 1000)
            components.append(
                ComponentHeartbeat(
                    heartbeat_id=new_id("heartbeat"),
                    runtime_id=self.runtime_id,
                    cycle_id=cycle_id,
                    component=component,
                    health=reading.health,
                    available=reading.available,
                    process_running=reading.process_running,
                    page_available=reading.page_available,
                    reason_code=reading.reason_code,
                    latency_ms=latency_ms,
                    checked_at=self._next_checked_at(),
                )
            )
        values = tuple(item.health for item in components)
        overall = (
            ComponentHealth.UNHEALTHY
            if ComponentHealth.UNHEALTHY in values
            else (
                ComponentHealth.DEGRADED
                if ComponentHealth.DEGRADED in values
                else ComponentHealth.HEALTHY
            )
        )
        report = HeartbeatReport(
            runtime_id=self.runtime_id,
            cycle_id=cycle_id,
            overall=overall,
            components=tuple(components),
            checked_at=max(item.checked_at for item in components),
        )
        self._store.append_heartbeat(report)
        return report

    def _next_checked_at(self) -> datetime:
        """Keep persisted heartbeat ordering monotonic on coarse Windows clocks."""
        with self._clock_lock:
            checked_at = self._clock()
            if (
                self._last_checked_at is not None
                and checked_at <= self._last_checked_at
            ):
                checked_at = self._last_checked_at + timedelta(microseconds=1)
            self._last_checked_at = checked_at
            return checked_at


__all__ = [
    "BrowserHealthProbe",
    "HealthProbe",
    "HeartbeatManager",
    "StaticHealthProbe",
    "StorageHealthProbe",
]
