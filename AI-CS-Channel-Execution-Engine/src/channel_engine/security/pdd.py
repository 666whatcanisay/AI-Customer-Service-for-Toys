from __future__ import annotations

from channel_engine.execution.pdd_sandbox import (
    PDDApprovalExecutionResult,
    PDDHumanApprovalExecutionSandbox,
)
from channel_engine.execution.coordinator import ExecutionEnqueued

from .rbac import (
    OperatorPermission,
    OperatorPrincipal,
    RBACAuthorizer,
)


class PDDRBACApprovalExecutionService:
    """RBAC gate around the manual PDD approval and execution boundary."""

    def __init__(
        self,
        sandbox: PDDHumanApprovalExecutionSandbox,
        authorizer: RBACAuthorizer | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._authorizer = authorizer or RBACAuthorizer()

    def approve(
        self,
        decision_id: str,
        *,
        principal: OperatorPrincipal,
    ) -> ExecutionEnqueued:
        self._authorizer.require(principal, OperatorPermission.APPROVAL_DECIDE)
        return self._sandbox.approve(
            decision_id,
            operator=principal.principal_id,
        )

    def execute(
        self,
        execution_id: str,
        *,
        principal: OperatorPrincipal,
    ) -> PDDApprovalExecutionResult:
        self._authorizer.require(principal, OperatorPermission.EXECUTION_TRIGGER)
        return self._sandbox.execute_approved(execution_id)


__all__ = ["PDDRBACApprovalExecutionService"]
