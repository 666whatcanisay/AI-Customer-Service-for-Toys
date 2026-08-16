from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Literal

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.browser import BrowserPageObserverHeartbeat
from channel_engine.models.entities import utc_now
from channel_engine.session import ChannelSession, MessageCursor

from .message_observation import PDDMessageReaderHealth, PDDMessageReaderState


PDD_RUNTIME_STATUS_VERSION = "1.0"


class PDDRuntimeStatusModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    status_contract_version: Literal["1.0"] = PDD_RUNTIME_STATUS_VERSION


class PDDRuntimeHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    DISABLED = "DISABLED"


class PDDRuntimeComponentStatus(PDDRuntimeStatusModel):
    component: Literal["SESSION", "CURSOR", "BROWSER", "ADAPTER", "RECOVERY"]
    health: PDDRuntimeHealth
    reason_code: str = Field(min_length=3, max_length=128)
    checked_at: AwareDatetime


class PDDRecoveryRuntimeStatus(PDDRuntimeStatusModel):
    health: PDDRuntimeHealth = PDDRuntimeHealth.HEALTHY
    reason_code: str = "PDD_RECOVERY_IDLE"
    attempts: int = Field(default=0, ge=0)
    manual_intervention_required: bool = False


class PDDRuntimeStatus(PDDRuntimeStatusModel):
    overall: PDDRuntimeHealth
    session: PDDRuntimeComponentStatus
    cursor: PDDRuntimeComponentStatus
    browser: PDDRuntimeComponentStatus
    adapter: PDDRuntimeComponentStatus
    recovery: PDDRuntimeComponentStatus
    cursor_last_persisted_sequence: int = Field(ge=0)
    cursor_last_processed_sequence: int = Field(ge=0)
    cursor_backlog: int = Field(ge=0)
    recovery_attempts: int = Field(ge=0)
    manual_intervention_required: bool
    observe_only: Literal[True] = True
    send_enabled: Literal[False] = False
    real_platform_connected: Literal[False] = False
    checked_at: AwareDatetime


class PDDRuntimeStatusMonitor:
    """Aggregates PDD session, cursor, browser, adapter and recovery health."""

    def __init__(
        self,
        *,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        self._clock = clock
        self._lock = RLock()
        self._latest = self._disabled_snapshot()

    def update(
        self,
        *,
        session: ChannelSession | None,
        cursor: MessageCursor | None,
        browser: BrowserPageObserverHeartbeat | None,
        adapter: PDDMessageReaderHealth | None,
        recovery: PDDRecoveryRuntimeStatus | None = None,
    ) -> PDDRuntimeStatus:
        with self._lock:
            now = self._clock()
            session_component = self._session_component(session, now)
            cursor_component = self._cursor_component(cursor, now)
            browser_component = self._browser_component(browser, now)
            adapter_component = self._adapter_component(adapter, now)
            recovery_state = recovery or PDDRecoveryRuntimeStatus()
            recovery_component = PDDRuntimeComponentStatus(
                component="RECOVERY",
                health=recovery_state.health,
                reason_code=recovery_state.reason_code,
                checked_at=now,
            )
            components = (
                session_component,
                cursor_component,
                browser_component,
                adapter_component,
                recovery_component,
            )
            overall = self._overall(component.health for component in components)
            last_sequence = cursor.last_sequence if cursor is not None else 0
            last_acked = cursor.last_acked_sequence if cursor is not None else 0
            self._latest = PDDRuntimeStatus(
                overall=overall,
                session=session_component,
                cursor=cursor_component,
                browser=browser_component,
                adapter=adapter_component,
                recovery=recovery_component,
                cursor_last_persisted_sequence=last_sequence,
                cursor_last_processed_sequence=last_acked,
                cursor_backlog=max(last_sequence - last_acked, 0),
                recovery_attempts=recovery_state.attempts,
                manual_intervention_required=(
                    recovery_state.manual_intervention_required
                ),
                checked_at=now,
            )
            return self._latest

    def snapshot(self) -> PDDRuntimeStatus:
        with self._lock:
            return self._latest

    def _disabled_snapshot(self) -> PDDRuntimeStatus:
        now = self._clock()
        components = {
            name: PDDRuntimeComponentStatus(
                component=name,
                health=PDDRuntimeHealth.DISABLED,
                reason_code=f"PDD_{name}_DISABLED",
                checked_at=now,
            )
            for name in ("SESSION", "CURSOR", "BROWSER", "ADAPTER", "RECOVERY")
        }
        return PDDRuntimeStatus(
            overall=PDDRuntimeHealth.DISABLED,
            session=components["SESSION"],
            cursor=components["CURSOR"],
            browser=components["BROWSER"],
            adapter=components["ADAPTER"],
            recovery=components["RECOVERY"],
            cursor_last_persisted_sequence=0,
            cursor_last_processed_sequence=0,
            cursor_backlog=0,
            recovery_attempts=0,
            manual_intervention_required=False,
            checked_at=now,
        )

    @staticmethod
    def _session_component(
        session: ChannelSession | None,
        now: AwareDatetime,
    ) -> PDDRuntimeComponentStatus:
        if session is None:
            return PDDRuntimeComponentStatus(
                component="SESSION",
                health=PDDRuntimeHealth.BLOCKED,
                reason_code="PDD_SESSION_UNAVAILABLE",
                checked_at=now,
            )
        connected = session.status.value == "CONNECTED"
        return PDDRuntimeComponentStatus(
            component="SESSION",
            health=(PDDRuntimeHealth.HEALTHY if connected else PDDRuntimeHealth.DEGRADED),
            reason_code=f"PDD_SESSION_{session.status.value}",
            checked_at=now,
        )

    @staticmethod
    def _cursor_component(
        cursor: MessageCursor | None,
        now: AwareDatetime,
    ) -> PDDRuntimeComponentStatus:
        if cursor is None:
            return PDDRuntimeComponentStatus(
                component="CURSOR",
                health=PDDRuntimeHealth.BLOCKED,
                reason_code="PDD_CURSOR_UNAVAILABLE",
                checked_at=now,
            )
        backlog = cursor.last_sequence - cursor.last_acked_sequence
        return PDDRuntimeComponentStatus(
            component="CURSOR",
            health=(PDDRuntimeHealth.HEALTHY if backlog == 0 else PDDRuntimeHealth.DEGRADED),
            reason_code=("PDD_CURSOR_IN_SYNC" if backlog == 0 else "PDD_CURSOR_BACKLOG"),
            checked_at=now,
        )

    @staticmethod
    def _browser_component(
        browser: BrowserPageObserverHeartbeat | None,
        now: AwareDatetime,
    ) -> PDDRuntimeComponentStatus:
        healthy = browser is not None and browser.healthy
        return PDDRuntimeComponentStatus(
            component="BROWSER",
            health=(PDDRuntimeHealth.HEALTHY if healthy else PDDRuntimeHealth.DEGRADED),
            reason_code=(
                "PDD_BROWSER_HEALTHY"
                if healthy
                else (
                    browser.failure_code
                    if browser is not None and browser.failure_code is not None
                    else "PDD_BROWSER_UNAVAILABLE"
                )
            ),
            checked_at=now,
        )

    @staticmethod
    def _adapter_component(
        adapter: PDDMessageReaderHealth | None,
        now: AwareDatetime,
    ) -> PDDRuntimeComponentStatus:
        connected = adapter is not None and adapter.state is PDDMessageReaderState.CONNECTED
        return PDDRuntimeComponentStatus(
            component="ADAPTER",
            health=(PDDRuntimeHealth.HEALTHY if connected else PDDRuntimeHealth.DEGRADED),
            reason_code=(
                "PDD_ADAPTER_CONNECTED"
                if connected
                else (
                    f"PDD_ADAPTER_{adapter.state.value}"
                    if adapter is not None
                    else "PDD_ADAPTER_UNAVAILABLE"
                )
            ),
            checked_at=now,
        )

    @staticmethod
    def _overall(healths) -> PDDRuntimeHealth:
        values = tuple(healths)
        for state in (
            PDDRuntimeHealth.BLOCKED,
            PDDRuntimeHealth.DEGRADED,
            PDDRuntimeHealth.DISABLED,
        ):
            if state in values:
                return state
        return PDDRuntimeHealth.HEALTHY


def create_pdd_runtime_status_router(
    status_provider: Callable[[], PDDRuntimeStatus],
) -> APIRouter:
    router = APIRouter(prefix="/ops/pdd", tags=["pdd-runtime"])

    @router.get("/runtime/status", response_model=PDDRuntimeStatus)
    def runtime_status() -> PDDRuntimeStatus:
        return status_provider()

    return router


__all__ = [
    "PDD_RUNTIME_STATUS_VERSION",
    "PDDRecoveryRuntimeStatus",
    "PDDRuntimeComponentStatus",
    "PDDRuntimeHealth",
    "PDDRuntimeStatus",
    "PDDRuntimeStatusMonitor",
    "create_pdd_runtime_status_router",
]
