from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from channel_engine.models.entities import utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork

from .models import KillSwitchState
from .repository import ControlPlaneRepository


class ExecutionControlBlocked(ValueError):
    error_code = "CONTROL_PLANE_KILL_SWITCH_ENABLED"


class ExecutionControlGate(Protocol):
    def assert_new_execution_allowed(self, uow: SqlAlchemyUnitOfWork) -> None:
        """Reject creation of a new Execution while globally stopped."""

    def pending_claim_allowed(self, uow: SqlAlchemyUnitOfWork) -> bool:
        """Return whether a PENDING Execution may transition to RUNNING."""


class AllowExecutionControlGate:
    """Compatibility default for callers that have not installed a control plane."""

    def assert_new_execution_allowed(self, uow: SqlAlchemyUnitOfWork) -> None:
        del uow

    def pending_claim_allowed(self, uow: SqlAlchemyUnitOfWork) -> bool:
        del uow
        return True


class PersistentExecutionControlGate:
    """Reads the authoritative kill-switch row inside the caller transaction."""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock

    def assert_new_execution_allowed(self, uow: SqlAlchemyUnitOfWork) -> None:
        if not self.pending_claim_allowed(uow):
            raise ExecutionControlBlocked(
                "global kill switch is ENABLED; new Execution is forbidden"
            )

    def pending_claim_allowed(self, uow: SqlAlchemyUnitOfWork) -> bool:
        if uow.session is None:
            raise RuntimeError("control gate requires an active unit of work")
        state = ControlPlaneRepository(uow.session).get_state_for_execution_gate(
            self._clock()
        )
        return state.kill_switch_state is KillSwitchState.DISABLED


__all__ = [
    "AllowExecutionControlGate",
    "ExecutionControlBlocked",
    "ExecutionControlGate",
    "PersistentExecutionControlGate",
]
