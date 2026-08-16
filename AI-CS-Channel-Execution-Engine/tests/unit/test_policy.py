from __future__ import annotations

import pytest

from channel_engine.models import (
    Approval,
    ApprovalState,
    Decision,
    DecisionAction,
    DecisionState,
)
from channel_engine.policy import ApprovalPolicy, ApprovalRequired


def build_decision(state: DecisionState) -> Decision:
    return Decision(
        conversation_id="conv-1",
        message_id="msg-1",
        action=DecisionAction.SUGGEST_REPLY,
        proposed_content="proposal",
        gateway_version="fake.v1",
        state=state,
    )


def test_unapproved_decision_cannot_execute() -> None:
    policy = ApprovalPolicy()
    decision = build_decision(DecisionState.WAITING_APPROVAL)
    approval = Approval(decision_id=decision.decision_id)

    with pytest.raises(ApprovalRequired):
        policy.assert_can_execute(decision, approval)


def test_approved_decision_requires_named_human() -> None:
    policy = ApprovalPolicy()
    decision = build_decision(DecisionState.APPROVED)
    approval = Approval(
        decision_id=decision.decision_id,
        state=ApprovalState.APPROVED,
        decided_by=None,
    )

    with pytest.raises(ApprovalRequired):
        policy.assert_can_execute(decision, approval)


def test_named_human_approval_allows_fake_execution() -> None:
    policy = ApprovalPolicy()
    decision = build_decision(DecisionState.APPROVED)
    approval = Approval(
        decision_id=decision.decision_id,
        state=ApprovalState.APPROVED,
        decided_by="operator-1",
    )

    policy.assert_can_execute(decision, approval)
