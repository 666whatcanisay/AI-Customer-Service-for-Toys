from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProviderModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ProviderVisibleHistoryItem(ProviderModel):
    message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]
    source: Literal["REAL_PDD", "SYNTHETIC"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    timestamp: AwareDatetime
    privacy_filtered: Literal[True] = True


class NormalizedChannelObservation(ProviderModel):
    """Provider-neutral, privacy-filtered input to the ChannelAgent boundary."""

    provider_observation_version: Literal["1.0"] = "1.0"
    provider_id: str = Field(min_length=1, max_length=128)
    provider_kind: Literal["SYNTHETIC_PDD", "RECORDED_REPLAY", "REAL_PDD"]
    trace_id: str = Field(pattern=r"^trace:[a-f0-9]{64}$")
    platform: Literal["PDD"] = "PDD"
    catalog_tenant_id: str = Field(
        default="CHANNEL-AGENT-PILOT", min_length=1, max_length=100
    )
    catalog_platform: str = Field(default="pdd", min_length=1, max_length=40)
    store_id: str = Field(min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    store_name: str | None = Field(default=None, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    external_message_id: str = Field(min_length=1, max_length=255)
    source_cursor: str = Field(min_length=1, max_length=512)
    source_sequence: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    timestamp: AwareDatetime
    captured_at: AwareDatetime
    product: dict[str, object] = Field(default_factory=dict)
    order: dict[str, object] = Field(default_factory=dict)
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_evidence_hash: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    privacy_filtered: Literal[True] = True
    visible_history: tuple[ProviderVisibleHistoryItem, ...] = Field(
        default_factory=tuple, max_length=20
    )

    @classmethod
    def synthetic(
        cls,
        *,
        provider_id: str,
        store_id: str,
        conversation_id: str,
        external_message_id: str,
        source_sequence: int,
        content: str,
        timestamp: datetime,
        product: dict[str, object] | None = None,
        order: dict[str, object] | None = None,
        store_name: str | None = None,
        catalog_tenant_id: str = "CHANNEL-AGENT-PILOT",
        catalog_platform: str = "pdd",
    ) -> "NormalizedChannelObservation":
        material = json.dumps(
            [provider_id, store_id, conversation_id, external_message_id],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        captured = timestamp.astimezone(UTC)
        return cls(
            provider_id=provider_id,
            provider_kind="SYNTHETIC_PDD",
            trace_id="trace:" + hashlib.sha256(material.encode("utf-8")).hexdigest(),
            store_id=store_id,
            catalog_tenant_id=catalog_tenant_id,
            catalog_platform=catalog_platform,
            platform_store_id=f"synthetic:{store_id}",
            store_name=store_name,
            conversation_id=conversation_id,
            customer_reference="sha256:"
            + hashlib.sha256(f"{store_id}\0{conversation_id}".encode("utf-8")).hexdigest(),
            external_message_id=external_message_id,
            source_cursor=f"{provider_id}:{store_id}:{conversation_id}:{source_sequence}",
            source_sequence=source_sequence,
            content=content,
            timestamp=captured,
            captured_at=captured,
            product=product or {},
            order=order or {},
            page_fingerprint="sha256:"
            + hashlib.sha256(f"synthetic-page:{store_id}".encode("utf-8")).hexdigest(),
        )

    def pdd_payload(self) -> dict[str, object]:
        return {
            "schema_version": "channel-agent-pdd-observation.v2.2",
            "platform": self.platform,
            "catalog_tenant_id": self.catalog_tenant_id,
            "catalog_platform": self.catalog_platform,
            "store_id": self.store_id,
            "platform_store_id": self.platform_store_id,
            "store_name": self.store_name,
            "conversation_id": self.conversation_id,
            "customer_reference": self.customer_reference,
            "external_message_id": self.external_message_id,
            "sender": "CUSTOMER",
            "origin": (
                "LIVE_PDD" if self.provider_kind == "REAL_PDD" else "SYNTHETIC"
            ),
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "product": self.product,
            "order": self.order,
            "page_fingerprint": self.page_fingerprint,
            "selector_evidence_hash": self.selector_evidence_hash,
            "privacy_filtered": True,
            "trace_id": self.trace_id,
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "visible_history": [
                item.model_dump(mode="json") for item in self.visible_history
            ],
        }


@runtime_checkable
class ChannelMessageProvider(Protocol):
    """External input port. Core services depend only on this protocol."""

    provider_id: str

    def poll(self, *, limit: int = 100) -> tuple[NormalizedChannelObservation, ...]: ...


class ProviderIngress:
    """Runs a Provider without knowing whether its data is synthetic or real."""

    def __init__(
        self,
        provider: ChannelMessageProvider,
        accept: Callable[[NormalizedChannelObservation], object],
    ) -> None:
        self._provider = provider
        self._accept = accept

    def run_once(self, *, limit: int = 100) -> int:
        observations = self._provider.poll(limit=max(1, min(limit, 100)))
        for observation in observations:
            self._accept(observation)
        return len(observations)


__all__ = [
    "ChannelMessageProvider",
    "NormalizedChannelObservation",
    "ProviderVisibleHistoryItem",
    "ProviderIngress",
]
