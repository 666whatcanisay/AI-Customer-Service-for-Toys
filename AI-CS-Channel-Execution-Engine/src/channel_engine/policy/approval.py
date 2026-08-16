from __future__ import annotations

from channel_engine.models import (
    Approval,
    ApprovalState,
    Decision,
    DecisionAction,
    DecisionState,
)


class ApprovalRequired(PermissionError):
    pass


class ApprovalPolicy:
    """Foundation policy: every executable suggestion requires a human approval."""

    def requires_approval(self, decision: Decision) -> bool:
        return decision.action is not DecisionAction.NO_ACTION

    def assert_can_execute(self, decision: Decision, approval: Approval) -> None:
        if decision.state is not DecisionState.APPROVED:
            raise ApprovalRequired("decision must be APPROVED before execution")
        if approval.state is not ApprovalState.APPROVED:
            raise ApprovalRequired("an explicit human approval is required")
        if not approval.decided_by:
            raise ApprovalRequired("approval must identify the human operator")
