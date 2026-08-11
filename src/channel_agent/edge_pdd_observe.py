from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .edge_spool import EdgeObservation


class PDDWorkspaceBoundaryError(RuntimeError):
    """Fail-closed boundary for read-only PDD observation."""


class EdgePDDObserveModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDSelectorRuntimeEvidence(EdgePDDObserveModel):
    evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_contract_version: str = Field(min_length=1, max_length=128)
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    capability: Literal["OBSERVE", "SEND_MESSAGE"]
    verified_at: AwareDatetime
    expires_at: AwareDatetime

    def assert_active(self, *, now: datetime, expected_capability: str) -> None:
        if self.capability != expected_capability:
            raise PDDWorkspaceBoundaryError("selector evidence capability mismatch")
        if self.expires_at <= now.astimezone(UTC):
            raise PDDWorkspaceBoundaryError("selector evidence expired")


class PDDWorkspaceProduct(EdgePDDObserveModel):
    product_id: str | None = Field(default=None, max_length=160)
    product_name: str | None = Field(default=None, max_length=512)
    sku_id: str | None = Field(default=None, max_length=160)
    sku_name: str | None = Field(default=None, max_length=512)
    attributes: dict[str, str] = Field(default_factory=dict)


class PDDWorkspaceOrder(EdgePDDObserveModel):
    order_reference: str | None = Field(default=None, max_length=255)
    order_status: str | None = Field(default=None, max_length=128)
    logistics_status: str | None = Field(default=None, max_length=128)
    aftersales_status: str | None = Field(default=None, max_length=128)
    contains_payment_data: Literal[False] = False
    contains_address_data: Literal[False] = False


class PDDWorkspaceMessage(EdgePDDObserveModel):
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM", "UNKNOWN"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    timestamp: AwareDatetime
    sequence: int = Field(ge=1)


class PDDWorkspaceSnapshot(EdgePDDObserveModel):
    platform: Literal["PDD"] = "PDD"
    store_id: str = Field(min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    store_name: str | None = Field(default=None, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_evidence_hash: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    page_state: Literal["CUSTOMER_SERVICE_READY", "CUSTOMER_SERVICE_RUNNING"]
    product: PDDWorkspaceProduct = Field(default_factory=PDDWorkspaceProduct)
    order: PDDWorkspaceOrder = Field(default_factory=PDDWorkspaceOrder)
    messages: tuple[PDDWorkspaceMessage, ...] = Field(max_length=100)
    captured_at: AwareDatetime

    @model_validator(mode="after")
    def validate_messages(self) -> "PDDWorkspaceSnapshot":
        ordered = tuple(
            sorted(
                self.messages,
                key=lambda item: (
                    item.sequence,
                    item.timestamp,
                    item.external_message_id,
                ),
            )
        )
        if ordered != self.messages:
            raise ValueError("PDD workspace messages must preserve source ordering")
        identities = [item.external_message_id for item in self.messages]
        if len(identities) != len(set(identities)):
            raise ValueError("PDD workspace message ids must be unique")
        return self


class PDDWorkspaceObservationMapper:
    """Map privacy-filtered customer messages into the durable edge contract."""

    def __init__(self, *, agent_id: str, device_id: str) -> None:
        self.agent_id = agent_id
        self.device_id = device_id

    def map_customer_messages(
        self,
        snapshot: PDDWorkspaceSnapshot,
        *,
        after_sequence: int = 0,
        origin: Literal["LIVE_PDD", "STARTUP_UNREAD", "SYNTHETIC"] = "LIVE_PDD",
        now: datetime | None = None,
    ) -> tuple[EdgeObservation, ...]:
        captured = (now or snapshot.captured_at).astimezone(UTC)
        results: list[EdgeObservation] = []
        for message in snapshot.messages:
            if message.sender != "CUSTOMER" or message.sequence <= after_sequence:
                continue
            content = privacy_filter(message.content)
            if not content:
                continue
            payload = {
                "schema_version": "channel-agent-pdd-observation.v2.1",
                "platform": "PDD",
                "store_id": snapshot.store_id,
                "platform_store_id": snapshot.platform_store_id,
                "store_name": snapshot.store_name,
                "conversation_id": snapshot.conversation_id,
                "customer_reference": snapshot.customer_reference,
                "external_message_id": message.external_message_id,
                "sender": "CUSTOMER",
                "origin": origin,
                "content": content,
                "timestamp": message.timestamp.isoformat(),
                "product": snapshot.product.model_dump(mode="json"),
                "order": snapshot.order.model_dump(mode="json"),
                "page_fingerprint": snapshot.page_fingerprint,
                "selector_evidence_hash": snapshot.selector_evidence_hash,
                "privacy_filtered": True,
            }
            digest = hashlib.sha256(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            results.append(
                EdgeObservation(
                    observation_id=f"pdd-observation:{digest}",
                    agent_id=self.agent_id,
                    device_id=self.device_id,
                    store_id=snapshot.store_id,
                    platform_store_id=snapshot.platform_store_id,
                    conversation_id=snapshot.conversation_id,
                    external_message_id=message.external_message_id,
                    source_cursor=(
                        f"{snapshot.store_id}:"
                        f"{snapshot.platform_store_id or 'unknown'}:"
                        f"{snapshot.conversation_id}:{message.sequence}"
                    ),
                    source_sequence=message.sequence,
                    payload=payload,
                    captured_at=captured,
                    expires_at=captured + timedelta(minutes=30),
                )
            )
        return tuple(results)


_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\w)")
_PAYMENT = re.compile(r"(?<!\d)\d{12,19}(?!\d)")


def privacy_filter(content: str) -> str:
    value = _PHONE.sub("[手机号已脱敏]", content)
    value = _ID_CARD.sub("[证件号已脱敏]", value)
    value = _PAYMENT.sub("[支付信息已脱敏]", value)
    return value.strip()


__all__ = [
    "EdgePDDObserveModel",
    "PDDSelectorRuntimeEvidence",
    "PDDWorkspaceBoundaryError",
    "PDDWorkspaceMessage",
    "PDDWorkspaceObservationMapper",
    "PDDWorkspaceOrder",
    "PDDWorkspaceProduct",
    "PDDWorkspaceSnapshot",
    "privacy_filter",
]
