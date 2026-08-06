from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from channel_engine.models import Event, EventType, ExecutionState, Receipt, ReceiptOutcome
from channel_engine.models.entities import utc_now
from channel_engine.observability import (
    StructuredEvent,
    StructuredEventStatus,
    StructuredEventType,
)
from channel_engine.storage import SqlAlchemyUnitOfWork


class RecoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    execution_state: ExecutionState
    receipt_id: str
    receipt_outcome: ReceiptOutcome
    reason: str


class ExecutionRecovery:
    """Conservatively turns expired RUNNING leases into UNKNOWN receipts."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def recover_expired(self, limit: int = 100) -> list[RecoveryResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        now = self._clock()
        with self._uow_factory() as uow:
            candidates = uow.require_repository().list_expired_running_executions(
                now, limit
            )

        recovered: list[RecoveryResult] = []
        for candidate in candidates:
            if candidate.lease_token is None:
                continue
            with self._uow_factory() as uow:
                repo = uow.require_repository()
                decision = repo.get_decision(candidate.decision_id)
                repo.append_observability_event(
                    StructuredEvent(
                        event_type=StructuredEventType.RECOVERY_STARTED,
                        trace_id=decision.message_id,
                        message_id=decision.message_id,
                        decision_id=decision.decision_id,
                        execution_id=candidate.execution_id,
                        status=StructuredEventStatus.PENDING,
                        metadata={
                            "component": "EXECUTION_WORKER",
                            "attempt": candidate.attempt,
                            "reason_code": "WORKER_LEASE_EXPIRED",
                        },
                    )
                )
                execution = repo.expire_execution_lease(
                    candidate.execution_id,
                    candidate.lease_token,
                    now,
                    "WORKER_LEASE_EXPIRED",
                )
                if execution is None:
                    continue
                receipt = Receipt(
                    execution_id=execution.execution_id,
                    outcome=ReceiptOutcome.UNKNOWN,
                    external_reference=None,
                    details={
                        "mode": "RECOVERY",
                        "reason": "WORKER_LEASE_EXPIRED",
                        "real_channel_called": False,
                        "customer_message_sent": False,
                        "automatic_retry_allowed": False,
                        "attempt": execution.attempt,
                    },
                    recorded_at=now,
                )
                repo.append_receipt(receipt)
                repo.append_event(
                    Event(
                        aggregate_type="Execution",
                        aggregate_id=execution.execution_id,
                        event_type=EventType.EXECUTION_UNKNOWN,
                        payload={
                            "receipt_id": receipt.receipt_id,
                            "outcome": ReceiptOutcome.UNKNOWN.value,
                            "error_code": "WORKER_LEASE_EXPIRED",
                        },
                        correlation_id=decision.message_id,
                    )
                )
                repo.append_event(
                    Event(
                        aggregate_type="Receipt",
                        aggregate_id=receipt.receipt_id,
                        event_type=EventType.RECEIPT_RECORDED,
                        payload={"execution_id": execution.execution_id},
                        correlation_id=decision.message_id,
                    )
                )
                repo.append_observability_event(
                    StructuredEvent(
                        event_type=StructuredEventType.RECOVERY_COMPLETED,
                        trace_id=decision.message_id,
                        message_id=decision.message_id,
                        decision_id=decision.decision_id,
                        execution_id=execution.execution_id,
                        receipt_id=receipt.receipt_id,
                        status=StructuredEventStatus.UNKNOWN,
                        metadata={
                            "component": "EXECUTION_WORKER",
                            "attempt": execution.attempt,
                            "reason_code": "WORKER_LEASE_EXPIRED",
                            "automatic_retry_allowed": False,
                        },
                    )
                )
                recovered.append(
                    RecoveryResult(
                        execution_id=execution.execution_id,
                        execution_state=execution.state,
                        receipt_id=receipt.receipt_id,
                        receipt_outcome=receipt.outcome,
                        reason="WORKER_LEASE_EXPIRED",
                    )
                )
        return recovered
