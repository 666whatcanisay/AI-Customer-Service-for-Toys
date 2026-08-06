from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Any


class ExecutionDenied(PermissionError):
    pass


class ReceiptOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    execution_id: str
    decision_id: str
    approval_id: str
    decision_status: str
    approval_status: str
    execution_status: str
    lease_owner: str
    lease_token: str
    lease_expires_at: datetime
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    receipt_id: str
    execution_id: str
    decision_id: str
    approval_id: str
    outcome: ReceiptOutcome
    idempotency_key: str
    recorded_at: str
    error_code: str | None = None
    reconciliation_required: bool = False
    automatic_retry_allowed: bool = False
    details: dict[str, str | int | bool | None] | None = None

    def __post_init__(self) -> None:
        if self.outcome is ReceiptOutcome.SUCCESS and self.error_code is not None:
            raise ValueError("SUCCESS receipt cannot carry an error")
        if self.outcome is not ReceiptOutcome.SUCCESS and not self.error_code:
            raise ValueError("FAILED and UNKNOWN receipts require an error code")
        if self.outcome is ReceiptOutcome.UNKNOWN and not self.reconciliation_required:
            raise ValueError("UNKNOWN receipt requires reconciliation")
        if self.outcome is ReceiptOutcome.UNKNOWN and self.automatic_retry_allowed:
            raise ValueError("UNKNOWN receipt cannot permit automatic retry")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["outcome"] = self.outcome.value
        return value


class ExecutionBoundary:
    """Authorizes a claimed execution; it performs no channel action."""

    @staticmethod
    def authorize(
        context: ExecutionContext,
        *,
        kill_switch: bool,
        worker_id: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> None:
        if kill_switch:
            raise ExecutionDenied("kill switch blocks execution")
        if context.decision_status != "APPROVED":
            raise ExecutionDenied("Decision is not approved")
        if context.approval_status != "APPROVED":
            raise ExecutionDenied("human Approval is not approved")
        if context.execution_status != "RUNNING":
            raise ExecutionDenied("Execution is not running")
        if context.lease_owner != worker_id or context.lease_token != lease_token:
            raise ExecutionDenied("execution lease does not match worker ownership")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("execution boundary clock must be timezone-aware")
        expiry = context.lease_expires_at
        if expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= current:
            raise ExecutionDenied("execution lease is expired")


class ReceiptLedger:
    """Append-only immutable receipt ledger with execution idempotency."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def append(self, receipt: ExecutionReceipt) -> ExecutionReceipt:
        with self._lock:
            existing = self._find(receipt.execution_id)
            if existing is not None:
                if existing.to_dict() != receipt.to_dict():
                    raise ValueError("execution already has a different immutable receipt")
                return existing
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                receipt.to_dict(), ensure_ascii=False, separators=(",", ":")
            ) + "\n"
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            return receipt

    def get(self, execution_id: str) -> ExecutionReceipt | None:
        with self._lock:
            return self._find(execution_id)

    def _find(self, execution_id: str) -> ExecutionReceipt | None:
        if not self.path.exists():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if value.get("execution_id") == execution_id:
                return ExecutionReceipt(
                    receipt_id=value["receipt_id"],
                    execution_id=value["execution_id"],
                    decision_id=value["decision_id"],
                    approval_id=value["approval_id"],
                    outcome=ReceiptOutcome(value["outcome"]),
                    idempotency_key=value["idempotency_key"],
                    recorded_at=value["recorded_at"],
                    error_code=value.get("error_code"),
                    reconciliation_required=bool(
                        value.get("reconciliation_required", False)
                    ),
                    automatic_retry_allowed=bool(
                        value.get("automatic_retry_allowed", False)
                    ),
                    details=value.get("details"),
                )
        return None
