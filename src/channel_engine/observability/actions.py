from __future__ import annotations

from channel_engine.execution import ExecutionCoordinator

from .models import (
    OpsApprovalAction,
    OpsApprovalActionResult,
    OpsApprovalCommand,
)


class ApprovalConfirmationMismatch(ValueError):
    pass


class OperationsApprovalService:
    """UI safety adapter over the existing human approval domain service.

    A successful approval creates or replays one PENDING Execution.  This
    adapter never runs a worker or invokes a channel transport.
    """

    def __init__(self, coordinator: ExecutionCoordinator) -> None:
        self._coordinator = coordinator

    def approve(
        self, decision_id: str, command: OpsApprovalCommand
    ) -> OpsApprovalActionResult:
        self._assert_confirmation("APPROVE", decision_id, command.confirmation_text)
        if command.reason is not None:
            raise ValueError("reason is not accepted for approval")
        outcome = self._coordinator.approve_and_enqueue(
            decision_id, command.operator
        )
        return OpsApprovalActionResult(
            action=OpsApprovalAction.APPROVE,
            decision_id=outcome.decision_id,
            approval_id=outcome.approval_id,
            execution_id=outcome.execution_id,
            decision_state="APPROVED",
            execution_state=outcome.execution_state.value,
            automatic_execution_started=False,
            real_send_triggered=False,
            next_step=(
                "Execution is PENDING; a separately controlled worker may claim it"
            ),
        )

    def reject(
        self, decision_id: str, command: OpsApprovalCommand
    ) -> OpsApprovalActionResult:
        self._assert_confirmation("REJECT", decision_id, command.confirmation_text)
        if command.reason is None or not command.reason.strip():
            raise ValueError("reason is required for rejection")
        outcome = self._coordinator.reject(
            decision_id,
            command.operator,
            command.reason.strip(),
        )
        return OpsApprovalActionResult(
            action=OpsApprovalAction.REJECT,
            decision_id=outcome.decision_id,
            approval_id=outcome.approval_id,
            decision_state=outcome.decision_state.value,
            automatic_execution_started=False,
            real_send_triggered=False,
            next_step="Decision rejected; no Execution was created",
        )

    @staticmethod
    def _assert_confirmation(action: str, decision_id: str, supplied: str) -> None:
        localized_action = {"APPROVE": "批准", "REJECT": "拒绝"}[action]
        expected = f"{localized_action} {decision_id}"
        legacy_expected = f"{action} {decision_id}"
        if supplied.strip() not in {expected, legacy_expected}:
            raise ApprovalConfirmationMismatch(
                f"确认短语必须完全等于：{expected}"
            )


__all__ = [
    "ApprovalConfirmationMismatch",
    "OperationsApprovalService",
]
