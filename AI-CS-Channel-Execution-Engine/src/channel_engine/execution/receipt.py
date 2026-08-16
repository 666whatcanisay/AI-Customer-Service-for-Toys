from __future__ import annotations

import re
from datetime import timezone

from channel_engine.gateway import (
    CONTRACT_VERSION,
    ExecutionReceipt as GatewayExecutionReceipt,
    ReceiptError as GatewayReceiptError,
)
from channel_engine.models import Execution, Receipt, ReceiptOutcome

from .receipt_facts import assert_unknown_receipt_details, unknown_receipt_details


def to_gateway_execution_receipt(
    execution: Execution,
    receipt: Receipt,
    correlation_id: str,
) -> GatewayExecutionReceipt:
    """Map an immutable ledger receipt to the frozen Gateway Contract V1."""

    if execution.execution_id != receipt.execution_id:
        raise ValueError("execution and receipt do not belong together")
    if execution.attempt < 1:
        raise ValueError("a gateway receipt requires at least one execution attempt")

    error: GatewayReceiptError | None = None
    if receipt.outcome is not ReceiptOutcome.SUCCESS:
        error_code = _contract_error_code(
            execution.error_code or f"EXECUTION_{receipt.outcome.value}"
        )
        message = str(receipt.details.get("reason") or error_code).strip()[:512]
        error = GatewayReceiptError(
            code=error_code,
            message=message,
            retryable=False,
        )

    details = dict(receipt.details)
    if receipt.outcome is ReceiptOutcome.UNKNOWN:
        details = unknown_receipt_details(
            details,
            transport_triggered=details.get("transport_triggered"),
        )
        assert_unknown_receipt_details(details)

    return GatewayExecutionReceipt(
        contract_version=CONTRACT_VERSION,
        receipt_id=receipt.receipt_id,
        idempotency_key=receipt.receipt_id,
        correlation_id=correlation_id,
        execution_id=execution.execution_id,
        decision_id=execution.decision_id,
        attempt=execution.attempt,
        outcome=receipt.outcome,
        external_reference=receipt.external_reference,
        error=error,
        reconciliation_required=receipt.outcome is ReceiptOutcome.UNKNOWN,
        details=details,
        recorded_at=(
            receipt.recorded_at.replace(tzinfo=timezone.utc)
            if receipt.recorded_at.tzinfo is None
            else receipt.recorded_at.astimezone(timezone.utc)
        ),
    )


def _contract_error_code(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9_]", "_", value.upper()).strip("_")[:64]
    if not normalized or not normalized[0].isalpha():
        normalized = f"EXECUTION_{normalized}"[:64]
    return normalized
