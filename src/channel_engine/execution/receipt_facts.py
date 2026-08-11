from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class TransportConfirmationState(StrEnum):
    NOT_TRIGGERED = "NOT_TRIGGERED"
    CONFIRMED_SENT = "CONFIRMED_SENT"
    CONFIRMED_NOT_SENT = "CONFIRMED_NOT_SENT"
    UNCONFIRMED = "UNCONFIRMED"


def unknown_receipt_details(
    details: Mapping[str, Any] | None = None,
    *,
    transport_triggered: bool | None = None,
) -> dict[str, Any]:
    """Return conservative facts for an execution whose outcome is unknowable.

    Calling an adapter is not proof that a transport was triggered, and a timeout
    after a trigger is not proof that a customer did or did not receive a message.
    UNKNOWN therefore uses tri-state facts and always requires reconciliation.
    """

    normalized = dict(details or {})
    normalized.pop("real_channel_called", None)
    normalized.update(
        {
            "transport_triggered": transport_triggered,
            "customer_message_sent": None,
            "confirmation_state": TransportConfirmationState.UNCONFIRMED.value,
            "reconciliation_required": True,
            "automatic_retry_allowed": False,
        }
    )
    return normalized


def assert_unknown_receipt_details(details: Mapping[str, Any]) -> None:
    if details.get("customer_message_sent") is not None:
        raise ValueError("UNKNOWN receipt cannot assert customer delivery")
    if details.get("confirmation_state") != TransportConfirmationState.UNCONFIRMED.value:
        raise ValueError("UNKNOWN receipt must be unconfirmed")
    if details.get("reconciliation_required") is not True:
        raise ValueError("UNKNOWN receipt must require reconciliation")
    if details.get("automatic_retry_allowed") is not False:
        raise ValueError("UNKNOWN receipt must prohibit automatic retry")


__all__ = [
    "TransportConfirmationState",
    "assert_unknown_receipt_details",
    "unknown_receipt_details",
]
