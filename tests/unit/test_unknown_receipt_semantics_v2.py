from channel_engine.execution.receipt_facts import (
    TransportConfirmationState,
    assert_unknown_receipt_details,
    unknown_receipt_details,
)


def test_unknown_receipt_never_claims_message_was_not_sent() -> None:
    details = unknown_receipt_details(
        {
            "mode": "EXECUTION_ADAPTER",
            "real_channel_called": False,
            "customer_message_sent": False,
        }
    )

    assert "real_channel_called" not in details
    assert details["transport_triggered"] is None
    assert details["customer_message_sent"] is None
    assert details["confirmation_state"] == TransportConfirmationState.UNCONFIRMED
    assert details["reconciliation_required"] is True
    assert details["automatic_retry_allowed"] is False
    assert_unknown_receipt_details(details)


def test_unknown_receipt_can_record_known_transport_trigger_without_claiming_delivery() -> None:
    details = unknown_receipt_details(transport_triggered=True)

    assert details["transport_triggered"] is True
    assert details["customer_message_sent"] is None
    assert_unknown_receipt_details(details)
