from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from channel_engine.control.gate import (
    ExecutionControlGate,
    PersistentExecutionControlGate,
)
from channel_engine.models import Event, EventType, Execution
from channel_engine.models.entities import utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork


class ExecutionLease(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution: Execution
    worker_id: str
    lease_token: str
    lease_expires_at: datetime


class LeaseLost(RuntimeError):
    pass


class ExecutionQueue:
    """Database-backed queue with atomic PENDING-to-RUNNING claims."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        worker_id: str,
        *,
        lease_duration: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = utc_now,
        control_gate: ExecutionControlGate | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_duration <= timedelta(0):
            raise ValueError("lease_duration must be positive")
        self._uow_factory = uow_factory
        self.worker_id = worker_id.strip()
        self.lease_duration = lease_duration
        self._clock = clock
        self._control_gate = control_gate or PersistentExecutionControlGate(
            clock=clock
        )

    def claim(self) -> ExecutionLease | None:
        return self._claim(None)

    def claim_exact(self, execution_id: str) -> ExecutionLease | None:
        if not execution_id.strip():
            raise ValueError("execution_id is required")
        return self._claim(execution_id.strip())

    def _claim(self, execution_id: str | None) -> ExecutionLease | None:
        now = self._clock()
        lease_expires_at = now + self.lease_duration
        with self._uow_factory() as uow:
            if not self._control_gate.pending_claim_allowed(uow):
                return None
            repo = uow.require_repository()
            execution = (
                repo.claim_pending_execution(
                    self.worker_id, now, lease_expires_at
                )
                if execution_id is None
                else repo.claim_pending_execution_by_id(
                    execution_id,
                    self.worker_id,
                    now,
                    lease_expires_at,
                )
            )
            if execution is None:
                return None
            assert execution.lease_token is not None
            decision = repo.get_decision(execution.decision_id)
            repo.append_event(
                Event(
                    aggregate_type="Execution",
                    aggregate_id=execution.execution_id,
                    event_type=EventType.EXECUTION_STARTED,
                    payload={
                        "decision_id": execution.decision_id,
                        "worker_id": self.worker_id,
                        "attempt": execution.attempt,
                        "lease_expires_at": lease_expires_at.isoformat(),
                    },
                    correlation_id=decision.message_id,
                )
            )
            return ExecutionLease(
                execution=execution,
                worker_id=self.worker_id,
                lease_token=execution.lease_token,
                lease_expires_at=lease_expires_at,
            )

    def renew(self, lease: ExecutionLease) -> ExecutionLease:
        if lease.worker_id != self.worker_id:
            raise LeaseLost("lease belongs to another worker")
        now = self._clock()
        lease_expires_at = now + self.lease_duration
        with self._uow_factory() as uow:
            renewed = uow.require_repository().renew_execution_lease(
                lease.execution.execution_id,
                self.worker_id,
                lease.lease_token,
                now,
                lease_expires_at,
            )
        if not renewed:
            raise LeaseLost(
                f"execution lease is no longer owned: {lease.execution.execution_id}"
            )
        return lease.model_copy(update={"lease_expires_at": lease_expires_at})
