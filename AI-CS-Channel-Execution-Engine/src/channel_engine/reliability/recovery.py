from __future__ import annotations

from collections.abc import Callable, Mapping

from channel_engine.models.entities import new_id, utc_now

from .models import (
    RecoveryEvent,
    RecoveryResult,
    RecoveryState,
    RuntimeComponent,
)
from .persistence import RuntimeReliabilityStore


class RuntimeRecoveryCoordinator:
    """Bounded, operator-triggered recovery. It never loops indefinitely."""

    def __init__(
        self,
        runtime_id: str,
        store: RuntimeReliabilityStore,
        recovery_actions: Mapping[RuntimeComponent, Callable[[], bool]],
        *,
        max_attempts: int = 2,
        event_observer: Callable[[RecoveryEvent], object] | None = None,
        clock: Callable = utc_now,
    ) -> None:
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        self.runtime_id = runtime_id
        self._store = store
        self._actions = dict(recovery_actions)
        self.max_attempts = max_attempts
        self._event_observer = event_observer
        self._clock = clock

    def recover(self, component: RuntimeComponent) -> RecoveryResult:
        recovery_id = new_id("recovery")
        events: list[RecoveryEvent] = []
        action = self._actions.get(component)
        for attempt in range(1, self.max_attempts + 1):
            events.append(
                self._record(
                    recovery_id,
                    component,
                    attempt,
                    RecoveryState.RECOVERING,
                    "RECOVERY_ATTEMPT_STARTED",
                )
            )
            recovered = False
            if action is not None:
                try:
                    recovered = action() is True
                except Exception:
                    recovered = False
            if recovered:
                events.append(
                    self._record(
                        recovery_id,
                        component,
                        attempt,
                        RecoveryState.RECOVERED,
                        "COMPONENT_RECOVERED",
                    )
                )
                return RecoveryResult(
                    recovery_id=recovery_id,
                    component=component,
                    state=RecoveryState.RECOVERED,
                    attempts=attempt,
                    events=tuple(events),
                )
        events.append(
            self._record(
                recovery_id,
                component,
                self.max_attempts,
                RecoveryState.MANUAL_INTERVENTION,
                "RECOVERY_BUDGET_EXHAUSTED",
            )
        )
        return RecoveryResult(
            recovery_id=recovery_id,
            component=component,
            state=RecoveryState.MANUAL_INTERVENTION,
            attempts=self.max_attempts,
            events=tuple(events),
        )

    def _record(
        self,
        recovery_id: str,
        component: RuntimeComponent,
        attempt: int,
        state: RecoveryState,
        reason_code: str,
    ) -> RecoveryEvent:
        event = RecoveryEvent(
            recovery_event_id=new_id("recovery-event"),
            recovery_id=recovery_id,
            runtime_id=self.runtime_id,
            component=component,
            attempt=attempt,
            state=state,
            reason_code=reason_code,
            occurred_at=self._clock(),
        )
        self._store.append_recovery_event(event)
        if self._event_observer is not None:
            self._event_observer(event)
        return event


__all__ = ["RuntimeRecoveryCoordinator"]
