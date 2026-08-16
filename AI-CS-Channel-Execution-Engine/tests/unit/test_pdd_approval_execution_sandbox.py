from __future__ import annotations

import pytest

from channel_engine.channel import (
    ExecutionBoundaryDenied,
    LedgerExecutionAuthorizationService,
)
from channel_engine.execution import (
    FakePDDExecutor,
    PDDApprovalSandboxSafetySnapshot,
    PDDHumanApprovalExecutionSandbox,
)


def test_fake_pdd_executor_rejects_bare_send_and_has_no_real_transport(
    foundation,
) -> None:
    executor = FakePDDExecutor(
        LedgerExecutionAuthorizationService(foundation["uow_factory"])
    )

    with pytest.raises(ExecutionBoundaryDenied, match="bare outbound"):
        executor.send_message("unapproved text")  # type: ignore[arg-type]

    assert executor.real_platform_transport is False
    assert executor.real_platform_call_count == 0
    assert executor.customer_message_sent is False
    assert executor.customer_message_send_count == 0


def test_sandbox_safety_snapshot_freezes_all_prohibited_effects(foundation) -> None:
    sandbox = PDDHumanApprovalExecutionSandbox(
        foundation["uow_factory"],
        worker_id="pdd-sandbox-unit-worker",
    )

    assert sandbox.safety_snapshot() == PDDApprovalSandboxSafetySnapshot()
    safety = sandbox.safety_snapshot()
    assert safety.fake_executor is True
    assert safety.real_pdd_connected is False
    assert safety.real_platform_called is False
    assert safety.customer_message_sent is False
    assert safety.automatic_approval is False
    assert safety.automatic_reply is False
    assert safety.refund_performed is False
    assert safety.order_modified is False
    assert safety.payment_performed is False
