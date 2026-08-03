from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from channel_engine.models.enums import ReceiptOutcome


class ExecutionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    decision_id: str
    proposed_content: str | None
    idempotency_key: str


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReceiptOutcome
    external_reference: str | None = None
    details: dict[str, object]


class ChannelExecutor(Protocol):
    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        """Execute a previously approved action."""


class FakeExecutor:
    """Records a synthetic result and never calls a real channel."""

    def __init__(self, outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS) -> None:
        self.outcome = outcome
        self.call_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        self.call_count += 1
        return ExecutionResult(
            outcome=self.outcome,
            external_reference=f"fake-execution-{command.execution_id}",
            details={
                "mode": "FAKE",
                "real_channel_called": False,
                "customer_message_sent": False,
                "idempotency_key": command.idempotency_key,
            },
        )
