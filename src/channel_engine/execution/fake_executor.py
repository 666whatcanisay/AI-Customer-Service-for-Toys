from __future__ import annotations

import hashlib
import json
from threading import Lock
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.models.enums import ReceiptOutcome


class ExecutionCommand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    decision_id: str
    proposed_content: str | None
    idempotency_key: str


class ClaimedExecutionContext(BaseModel):
    """Lease-fenced context supplied only by ExecutionWorker after claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str
    decision_id: str
    approval_id: str
    approved_by: str
    worker_id: str
    lease_token: str = Field(repr=False)
    lease_expires_at: AwareDatetime


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: ReceiptOutcome
    external_reference: str | None = None
    error_code: str | None = None
    details: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_error_code(self) -> ExecutionResult:
        if self.outcome is ReceiptOutcome.SUCCESS and self.error_code is not None:
            raise ValueError("SUCCESS cannot carry error_code")
        if self.outcome is not ReceiptOutcome.SUCCESS and self.error_code is None:
            raise ValueError("FAILED and UNKNOWN require error_code")
        return self


class ExecutionAdapter(Protocol):
    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        """Execute a previously approved action."""


@runtime_checkable
class ClaimedExecutionAdapter(Protocol):
    def execute_claimed(
        self,
        command: ExecutionCommand,
        context: ClaimedExecutionContext,
    ) -> ExecutionResult:
        """Execute with the current worker/lease fencing context."""


class AdapterOutcomeUnknown(RuntimeError):
    """The adapter cannot prove whether the external operation happened."""


class AdapterIdempotencyConflict(ValueError):
    pass


class FakeExecutionAdapter:
    """Idempotent synthetic adapter that never calls a real channel."""

    def __init__(
        self,
        outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
        *,
        simulate_network_uncertainty: bool = False,
    ) -> None:
        self.outcome = outcome
        self.simulate_network_uncertainty = simulate_network_uncertainty
        self.call_count = 0
        self._lock = Lock()
        self._results: dict[
            str, tuple[str, ExecutionResult | AdapterOutcomeUnknown]
        ] = {}

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        fingerprint = hashlib.sha256(
            json.dumps(
                command.model_dump(mode="json"),
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        with self._lock:
            replay = self._results.get(command.idempotency_key)
            if replay is not None:
                original_fingerprint, original_result = replay
                if fingerprint != original_fingerprint:
                    raise AdapterIdempotencyConflict(
                        "adapter idempotency key was reused with a different command"
                    )
                if isinstance(original_result, AdapterOutcomeUnknown):
                    raise AdapterOutcomeUnknown(str(original_result))
                return original_result

            self.call_count += 1
            if self.simulate_network_uncertainty:
                uncertain = AdapterOutcomeUnknown(
                    "simulated network interruption; external outcome is unknown"
                )
                self._results[command.idempotency_key] = (fingerprint, uncertain)
                raise uncertain

            error_code = {
                ReceiptOutcome.SUCCESS: None,
                ReceiptOutcome.FAILED: "FAKE_ADAPTER_FAILED",
                ReceiptOutcome.UNKNOWN: "FAKE_ADAPTER_UNKNOWN",
            }[self.outcome]
            result = ExecutionResult(
                outcome=self.outcome,
                external_reference=(
                    f"fake-execution-{command.execution_id}"
                    if self.outcome is ReceiptOutcome.SUCCESS
                    else None
                ),
                error_code=error_code,
                details={
                    "mode": "FAKE",
                    "real_channel_called": False,
                    "customer_message_sent": False,
                    "idempotency_key": command.idempotency_key,
                },
            )
            self._results[command.idempotency_key] = (fingerprint, result)
            return result


ChannelExecutor = ExecutionAdapter
FakeExecutor = FakeExecutionAdapter
