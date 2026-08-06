from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from channel_engine.models.entities import utc_now

from .models import (
    BrowserHealth,
    BrowserRuntimeState,
    ComponentHealth,
)


@runtime_checkable
class BrowserManager(Protocol):
    """Platform-neutral browser lifecycle boundary; V1 has no real driver."""

    def start(self) -> BrowserHealth: ...

    def stop(self) -> BrowserHealth: ...

    def health_check(self) -> BrowserHealth: ...

    def recover(self) -> bool: ...


class FakeBrowserAdapter:
    def __init__(
        self,
        *,
        fail_start: bool = False,
        failed_recovery_attempts: int = 0,
        clock: Callable = utc_now,
    ) -> None:
        if failed_recovery_attempts < 0:
            raise ValueError("failed_recovery_attempts cannot be negative")
        self.fail_start = fail_start
        self.failed_recovery_attempts = failed_recovery_attempts
        self._clock = clock
        self._state = BrowserRuntimeState.STOPPED
        self._health = ComponentHealth.UNHEALTHY
        self._reason_code = "BROWSER_STOPPED"
        self.start_count = 0
        self.stop_count = 0
        self.recovery_count = 0

    def start(self) -> BrowserHealth:
        self.start_count += 1
        self._state = BrowserRuntimeState.STARTING
        if self.fail_start:
            self._state = BrowserRuntimeState.FAILED
            self._health = ComponentHealth.UNHEALTHY
            self._reason_code = "FAKE_BROWSER_START_FAILED"
            raise RuntimeError(self._reason_code)
        self._state = BrowserRuntimeState.RUNNING
        self._health = ComponentHealth.HEALTHY
        self._reason_code = "FAKE_BROWSER_READY"
        return self.health_check()

    def stop(self) -> BrowserHealth:
        self.stop_count += 1
        self._state = BrowserRuntimeState.STOPPED
        self._health = ComponentHealth.UNHEALTHY
        self._reason_code = "BROWSER_STOPPED"
        return self.health_check()

    def health_check(self) -> BrowserHealth:
        process_running = self._state in {
            BrowserRuntimeState.RUNNING,
            BrowserRuntimeState.DEGRADED,
        }
        return BrowserHealth(
            state=self._state,
            health=self._health,
            process_running=process_running,
            page_available=(
                process_running and self._health is ComponentHealth.HEALTHY
            ),
            real_browser_connected=False,
            reason_code=self._reason_code,
            checked_at=self._clock(),
        )

    def simulate_failure(self, reason_code: str = "FAKE_PAGE_UNAVAILABLE") -> None:
        self._state = BrowserRuntimeState.DEGRADED
        self._health = ComponentHealth.UNHEALTHY
        self._reason_code = reason_code

    def recover(self) -> bool:
        self.recovery_count += 1
        if self.recovery_count <= self.failed_recovery_attempts:
            self._state = BrowserRuntimeState.DEGRADED
            self._health = ComponentHealth.UNHEALTHY
            self._reason_code = "FAKE_BROWSER_RECOVERY_FAILED"
            return False
        self._state = BrowserRuntimeState.RUNNING
        self._health = ComponentHealth.HEALTHY
        self._reason_code = "FAKE_BROWSER_RECOVERED"
        return True


__all__ = ["BrowserManager", "FakeBrowserAdapter"]
