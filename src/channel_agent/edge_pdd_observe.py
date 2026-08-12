from __future__ import annotations

import hashlib
import hmac
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
    logistics_reference: str | None = Field(default=None, max_length=255)
    aftersales_reference: str | None = Field(default=None, max_length=255)
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
    # Zero means the page exposes no stable sequence.  The Observer must replace
    # it with its durable per-conversation monotonic sequence before mapping.
    sequence: int = Field(ge=0)


class PDDVisibleHistoryItem(EdgePDDObserveModel):
    """Privacy-filtered page history carried by Observation v2.2."""

    message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]
    source: Literal["REAL_PDD", "SYNTHETIC"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    timestamp: AwareDatetime
    privacy_filtered: Literal[True] = True


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
    def validate_messages(self) -> PDDWorkspaceSnapshot:
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

    def __init__(
        self,
        *,
        agent_id: str,
        device_id: str,
        provider_id: str = "pdd-readonly",
        reference_tokenizer: PDDLocalReferenceTokenizer | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.device_id = device_id
        self.provider_id = provider_id
        self._reference_tokenizer = reference_tokenizer

    def map_customer_messages(
        self,
        snapshot: PDDWorkspaceSnapshot,
        *,
        after_sequence: int = 0,
        origin: Literal["LIVE_PDD", "STARTUP_UNREAD", "SYNTHETIC"] = "LIVE_PDD",
        selected_message_ids: frozenset[str] | None = None,
        now: datetime | None = None,
    ) -> tuple[EdgeObservation, ...]:
        captured = (now or snapshot.captured_at).astimezone(UTC)
        is_real = origin != "SYNTHETIC"
        provider_kind = "REAL_PDD" if is_real else "RECORDED_REPLAY"
        history_source = "REAL_PDD" if is_real else "SYNTHETIC"
        visible_history = tuple(
            PDDVisibleHistoryItem(
                message_id=item.external_message_id,
                sender=item.sender,
                source=history_source,
                content=filtered,
                content_sha256=hashlib.sha256(filtered.encode("utf-8")).hexdigest(),
                timestamp=item.timestamp,
            )
            for item in snapshot.messages[-20:]
            if item.sender != "UNKNOWN"
            and (
                filtered := privacy_filter(
                    item.content,
                    tokenizer=self._reference_tokenizer,
                    store_id=snapshot.store_id,
                )
            )
        )
        results: list[EdgeObservation] = []
        for message in snapshot.messages:
            if message.sender != "CUSTOMER" or message.sequence <= after_sequence:
                continue
            if (
                selected_message_ids is not None
                and message.external_message_id not in selected_message_ids
            ):
                continue
            content = privacy_filter(
                message.content,
                tokenizer=self._reference_tokenizer,
                store_id=snapshot.store_id,
            )
            if not content:
                continue
            payload = {
                "schema_version": "channel-agent-pdd-observation.v2.2",
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
                "order": _privacy_safe_order(
                    snapshot.order,
                    tokenizer=self._reference_tokenizer,
                    store_id=snapshot.store_id,
                    real_pdd=is_real,
                ),
                "page_fingerprint": snapshot.page_fingerprint,
                "selector_evidence_hash": snapshot.selector_evidence_hash,
                "privacy_filtered": True,
                "provider_id": self.provider_id,
                "provider_kind": provider_kind,
                "trace_id": "trace:"
                + hashlib.sha256(
                    (
                        f"{self.provider_id}\0{snapshot.store_id}\0"
                        f"{snapshot.conversation_id}\0{message.external_message_id}"
                    ).encode()
                ).hexdigest(),
                "visible_history": [
                    item.model_dump(mode="json") for item in visible_history
                ],
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
_ADDRESS = re.compile(
    r"(?:收货地址|详细地址|地址|address)\s*[:：]?\s*[^。；;\n]{2,180}",
    re.IGNORECASE,
)
_SOCIAL_ACCOUNT = re.compile(
    r"(?:微信号|微信|wx|wechat)\s*[:：]?\s*[A-Za-z0-9_-]{5,64}",
    re.IGNORECASE,
)
_EXPLICIT_NAME = re.compile(
    r"(?:收货人|姓名|我叫|name)\s*[:：]?\s*"
    r"(?:[\u4e00-\u9fff·]{2,12}|[A-Za-z][A-Za-z .'-]{1,40})",
    re.IGNORECASE,
)
_BUSINESS_REFERENCE = re.compile(
    r"(?P<label>订单号|订单编号|order(?:\s*id)?|"
    r"物流单号|运单号|tracking(?:\s*(?:id|number))?)"
    r"\s*[:：#]?\s*(?P<value>[A-Za-z0-9_-]{6,64})",
    re.IGNORECASE,
)


class PDDLocalReferenceTokenizer:
    """Create stable non-reversible tokens for business-critical identifiers."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("PDD reference token key must contain at least 32 bytes")
        self._key = bytes(key)

    def tokenize(self, kind: str, value: str, *, store_id: str) -> str:
        canonical_kind = kind.strip().upper()
        prefix = {
            "ORDER": "PDD_ORDER",
            "LOGISTICS": "PDD_LOGISTICS",
            "AFTERSALES": "PDD_AFTERSALES",
        }.get(canonical_kind)
        if prefix is None or not value.strip() or not store_id.strip():
            raise ValueError("PDD business reference token input is invalid")
        digest = hmac.new(
            self._key,
            f"{store_id}\0{canonical_kind}\0{value.strip()}".encode(),
            hashlib.sha256,
        ).hexdigest()[:16].upper()
        return f"{prefix}_{digest}"


def privacy_filter(
    content: str,
    *,
    tokenizer: PDDLocalReferenceTokenizer | None = None,
    store_id: str = "UNKNOWN",
) -> str:
    def replace_reference(match: re.Match[str]) -> str:
        label = match.group("label").casefold()
        kind = (
            "LOGISTICS"
            if any(marker in label for marker in ("物流", "运单", "tracking"))
            else "ORDER"
        )
        if tokenizer is None:
            return f"{kind}_[REFERENCE_REDACTED]"
        return tokenizer.tokenize(kind, match.group("value"), store_id=store_id)

    value = _BUSINESS_REFERENCE.sub(replace_reference, content)
    value = _PHONE.sub("[手机号已脱敏]", value)
    value = _ID_CARD.sub("[证件号已脱敏]", value)
    value = _PAYMENT.sub("[支付信息已脱敏]", value)
    value = _ADDRESS.sub("[ADDRESS_REDACTED]", value)
    value = _SOCIAL_ACCOUNT.sub("[SOCIAL_ACCOUNT_REDACTED]", value)
    value = _EXPLICIT_NAME.sub("[NAME_REDACTED]", value)

    return value.strip()


def _privacy_safe_order(
    order: PDDWorkspaceOrder,
    *,
    tokenizer: PDDLocalReferenceTokenizer | None,
    store_id: str,
    real_pdd: bool,
) -> dict[str, object]:
    result = order.model_dump(mode="json")
    for field, kind in {
        "order_reference": "ORDER",
        "logistics_reference": "LOGISTICS",
        "aftersales_reference": "AFTERSALES",
    }.items():
        value = result.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        if real_pdd and tokenizer is None:
            raise PDDWorkspaceBoundaryError(
                "REAL_PDD business reference requires a local tokenizer"
            )
        if tokenizer is not None:
            result[field] = tokenizer.tokenize(kind, value, store_id=store_id)
    return result


__all__ = [
    "EdgePDDObserveModel",
    "PDDLocalReferenceTokenizer",
    "PDDSelectorRuntimeEvidence",
    "PDDVisibleHistoryItem",
    "PDDWorkspaceBoundaryError",
    "PDDWorkspaceMessage",
    "PDDWorkspaceObservationMapper",
    "PDDWorkspaceOrder",
    "PDDWorkspaceProduct",
    "PDDWorkspaceSnapshot",
    "privacy_filter",
]
