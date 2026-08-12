from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from channel_engine.customer_assistant import (
    OfflineReceipt,
    OfflineReplyControlStore,
    ReceiptKind,
    TransportKind,
)
from channel_engine.execution import ExecutionCommand, FakeExecutionAdapter


NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def synthetic_receipt(**updates) -> OfflineReceipt:
    values = {
        "receipt_id": "synthetic-receipt-001",
        "execution_id": "synthetic-execution-001",
        "receipt_kind": ReceiptKind.SYNTHETIC,
        "transport_kind": TransportKind.SYNTHETIC_PDD,
        "environment": "SIMULATOR",
        "outcome": "SUCCESS",
        "external_side_effect": False,
        "customer_message_sent": False,
        "recorded_at": NOW,
    }
    values.update(updates)
    return OfflineReceipt(**values)


def test_synthetic_success_never_counts_as_real_send_success(tmp_path) -> None:
    store = OfflineReplyControlStore(tmp_path / "offline-control.sqlite3", clock=lambda: NOW)
    stored = store.record_receipt(synthetic_receipt())

    assert stored.receipt_kind == "SYNTHETIC"
    assert stored.external_side_effect is False
    assert stored.customer_message_sent is False
    assert store.real_success_count() == 0


@pytest.mark.parametrize(
    "updates",
    [
        {"customer_message_sent": True},
        {"external_side_effect": True},
        {"transport_kind": TransportKind.REAL_PDD},
        {"environment": "PRODUCTION"},
        {"external_reference": "real-message-001"},
    ],
)
def test_synthetic_receipt_cannot_claim_real_delivery_evidence(updates) -> None:
    with pytest.raises(ValidationError):
        synthetic_receipt(**updates)


def test_real_receipt_requires_all_future_activation_evidence() -> None:
    with pytest.raises(ValidationError):
        OfflineReceipt(
            receipt_id="real-receipt-001",
            execution_id="real-execution-001",
            receipt_kind=ReceiptKind.REAL,
            transport_kind=TransportKind.REAL_PDD,
            environment="PRODUCTION",
            outcome="SUCCESS",
            external_side_effect=True,
            customer_message_sent=True,
            recorded_at=NOW,
        )


def test_legacy_synthetic_execution_result_is_explicitly_non_real() -> None:
    result = FakeExecutionAdapter().execute(
        ExecutionCommand(
            execution_id="execution-synthetic-001",
            decision_id="decision-synthetic-001",
            proposed_content="synthetic reply",
            idempotency_key="synthetic-key-001",
        )
    )

    assert result.details["receipt_kind"] == "SYNTHETIC"
    assert result.details["transport_kind"] == "SYNTHETIC_PDD"
    assert result.details["environment"] == "SIMULATOR"
    assert result.details["external_side_effect"] is False
    assert result.details["customer_message_sent"] is False
