from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_agent.control_v2 import AgentObservationSubmission
from channel_engine.catalog_scope import canonical_catalog_platform
from channel_engine.channel import NormalizedMessage
from channel_engine.conversation import ConversationService, IntakeResult
from channel_engine.customer_assistant import (
    ContextPageState,
    ConversationHistoryCandidate,
    ConversationHistoryEntry,
    HistorySource,
    PageContext,
    ProductContext,
    TransactionContext,
    merge_visible_history,
)
from channel_engine.customer_assistant.buffer import SQLiteConversationBuffer
from channel_engine.gateway import AICSGateway
from channel_engine.storage import SqlAlchemyUnitOfWork


class ObservationPipelineError(RuntimeError):
    pass


class PDDVisibleHistoryPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]
    source: Literal["REAL_PDD", "SYNTHETIC"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    timestamp: AwareDatetime
    privacy_filtered: Literal[True] = True


class PDDObservationPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[
        "channel-agent-pdd-observation.v2.1",
        "channel-agent-pdd-observation.v2.2",
    ]
    platform: Literal["PDD"]
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
    sender: Literal["CUSTOMER"]
    origin: Literal["LIVE_PDD", "STARTUP_UNREAD", "SYNTHETIC"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    timestamp: AwareDatetime
    product: dict[str, object]
    order: dict[str, object]
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_evidence_hash: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    privacy_filtered: Literal[True]
    trace_id: str | None = Field(default=None, pattern=r"^trace:[a-f0-9]{64}$")
    provider_id: str | None = Field(default=None, min_length=1, max_length=128)
    provider_kind: Literal["SYNTHETIC_PDD", "RECORDED_REPLAY", "REAL_PDD"] | None = None
    visible_history: tuple[PDDVisibleHistoryPayload, ...] = Field(
        default_factory=tuple, max_length=20
    )

    @model_validator(mode="after")
    def validate_v22_provider_boundary(self) -> PDDObservationPayload:
        if self.schema_version.endswith("v2.2"):
            if self.provider_id is None or self.provider_kind is None:
                raise ValueError("PDD Observation v2.2 requires Provider identity")
            required_source = (
                "REAL_PDD" if self.provider_kind == "REAL_PDD" else "SYNTHETIC"
            )
            if any(item.source != required_source for item in self.visible_history):
                raise ValueError("visible history source does not match Provider kind")
            if self.provider_kind == "REAL_PDD":
                for field, prefix in {
                    "order_reference": "PDD_ORDER_",
                    "logistics_reference": "PDD_LOGISTICS_",
                    "aftersales_reference": "PDD_AFTERSALES_",
                }.items():
                    value = self.order.get(field)
                    if value is not None and (
                        not isinstance(value, str)
                        or re.fullmatch(rf"{prefix}[A-F0-9]{{16}}", value) is None
                    ):
                        raise ValueError(
                            f"REAL_PDD {field} must use a local privacy token"
                        )
        elif self.visible_history:
            raise ValueError("PDD Observation v2.1 cannot carry visible history")
        return self


class AgentObservationContextProvider:
    """Builds verified read-only CustomerContext ports from the Host inbox."""

    def __init__(
        self,
        control_store,
        history: SQLiteConversationBuffer,
        *,
        offline_control=None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = control_store
        self._history = history
        self._offline_control = offline_control
        self._clock = clock

    def _payload(self, store_id: str, conversation_id: str) -> PDDObservationPayload:
        raw = self._store.latest_observation_payload(store_id, conversation_id)
        if raw is None:
            raise ObservationPipelineError("observation-backed context is unavailable")
        return PDDObservationPayload.model_validate_json(
            json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
        )

    def capture_page_context(
        self, *, store_id: str, conversation_id: str
    ) -> PageContext:
        payload = self._payload(store_id, conversation_id)
        product = payload.product
        order = payload.order
        state = ContextPageState.CUSTOMER_SERVICE
        if order.get("aftersales_status"):
            state = ContextPageState.AFTERSALES
        elif order.get("order_reference") or order.get("order_status"):
            state = ContextPageState.ORDER
        elif product.get("product_id") or product.get("product_reference"):
            state = ContextPageState.PRODUCT
        attributes = product.get("attributes")
        normalized_attributes = (
            {
                str(key)[:80]: str(value)[:512]
                for key, value in attributes.items()
                if str(key).strip() and str(value).strip()
            }
            if isinstance(attributes, dict)
            else {}
        )
        return PageContext(
            store_id=store_id,
            catalog_tenant_id=payload.catalog_tenant_id,
            catalog_platform=payload.catalog_platform,
            store_name=payload.store_name,
            conversation_id=conversation_id,
            state=state,
            product=ProductContext(
                product_reference=_optional_text(
                    product.get("product_id") or product.get("product_reference"), 255
                ),
                product_name=_optional_text(product.get("product_name"), 512),
                sku_reference=_optional_text(
                    product.get("sku_id") or product.get("sku_reference"), 255
                ),
                sku_name=_optional_text(product.get("sku_name"), 512),
                attributes=dict(list(normalized_attributes.items())[:32]),
            ),
            captured_at=self._clock().astimezone(UTC),
        )

    def capture_transaction_context(
        self, *, store_id: str, conversation_id: str
    ) -> TransactionContext:
        order = self._payload(store_id, conversation_id).order
        return TransactionContext(
            order_reference=_optional_text(order.get("order_reference"), 255),
            order_status=_optional_text(order.get("order_status"), 128),
            logistics_status=_optional_text(order.get("logistics_status"), 128),
            aftersales_status=_optional_text(order.get("aftersales_status"), 128),
        )

    def load_history(self, *, store_id: str, conversation_id: str, limit: int):
        return self._history.load_history(
            store_id=store_id, conversation_id=conversation_id, limit=limit
        )

    def load_visible_history(
        self, *, store_id: str, conversation_id: str, limit: int
    ) -> tuple[ConversationHistoryEntry, ...]:
        return self.load_visible_history_for_turn(
            store_id=store_id,
            conversation_id=conversation_id,
            limit=limit,
            excluded_external_message_ids=(),
        )

    def load_visible_history_for_turn(
        self,
        *,
        store_id: str,
        conversation_id: str,
        limit: int,
        excluded_external_message_ids: tuple[str, ...],
    ) -> tuple[ConversationHistoryEntry, ...]:
        latest = self._store.latest_observation(store_id, conversation_id)
        if latest is None:
            raise ObservationPipelineError("observation-backed context is unavailable")
        payload = PDDObservationPayload.model_validate_json(
            json.dumps(latest.payload, ensure_ascii=False, separators=(",", ":"))
        )
        is_real = payload.provider_kind == "REAL_PDD"
        provider_kinds = self._store.observation_provider_kinds(store_id, conversation_id)
        excluded = set(excluded_external_message_ids)
        candidates: list[ConversationHistoryCandidate] = []
        for message in self._history.load_history(
            store_id=store_id, conversation_id=conversation_id, limit=50
        ):
            if message.external_message_id in excluded:
                continue
            provider_kind = provider_kinds.get(message.external_message_id)
            if is_real and provider_kind != "REAL_PDD":
                continue
            if not is_real and provider_kind == "REAL_PDD":
                continue
            source = HistorySource.REAL_PDD if is_real else HistorySource.SYNTHETIC
            candidates.append(
                ConversationHistoryCandidate(
                    entry=ConversationHistoryEntry(
                        store_id=store_id,
                        conversation_id=conversation_id,
                        external_message_id=message.external_message_id,
                        sender="customer",
                        content=message.content,
                        timestamp=message.timestamp,
                        content_digest=message.content_digest,
                    ),
                    source=source,
                    logical_key=f"message:{message.external_message_id}",
                )
            )
        real_operator_history_seen = False
        for message in payload.visible_history:
            if message.message_id in excluded or message.sender not in {
                "CUSTOMER",
                "OPERATOR",
            }:
                continue
            source = (
                HistorySource.REAL_PDD
                if message.source == "REAL_PDD"
                else HistorySource.SYNTHETIC
            )
            if is_real and source != HistorySource.REAL_PDD:
                continue
            if not is_real and source == HistorySource.REAL_PDD:
                continue
            if message.sender == "OPERATOR" and source == HistorySource.REAL_PDD:
                real_operator_history_seen = True
            candidates.append(
                ConversationHistoryCandidate(
                    entry=ConversationHistoryEntry(
                        store_id=store_id,
                        conversation_id=conversation_id,
                        external_message_id=message.message_id,
                        sender=message.sender.lower(),
                        content=message.content,
                        timestamp=message.timestamp,
                        content_digest=message.content_sha256,
                    ),
                    source=source,
                    logical_key=f"message:{message.message_id}",
                )
            )
        if not is_real and self._offline_control is not None:
            candidates.extend(
                self._offline_control.authorized_history_candidates(
                    store_id=store_id,
                    conversation_id=conversation_id,
                )
            )
        merged = merge_visible_history(
            tuple(candidates),
            store_id=store_id,
            conversation_id=conversation_id,
            limit=limit,
            real_operator_history_missing=is_real and not real_operator_history_seen,
        )
        if self._offline_control is not None:
            trace_id = payload.trace_id or (
                "trace:"
                + hashlib.sha256(
                    f"{store_id}\0{conversation_id}\0{latest.observation_id}".encode()
                ).hexdigest()
            )
            audit = dict(merged.audit)
            audit.update(
                {
                    "provider_id": payload.provider_id,
                    "provider_kind": payload.provider_kind,
                    "external_message_id": latest.external_message_id,
                    "observation_id": latest.observation_id,
                    "source_cursor": latest.source_cursor,
                    "source_sequence": latest.source_sequence,
                    "context_revision": self._offline_control.conversation_revision(
                        store_id, conversation_id
                    ),
                    "excluded_current_turn_message_ids": sorted(excluded),
                }
            )
            self._offline_control.record_history_audit(trace_id, audit)
        return merged.entries

    def scopes_for(self, *, store_id: str, conversation_id: str) -> tuple[str, ...]:
        page = self.capture_page_context(
            store_id=store_id, conversation_id=conversation_id
        )
        values = [f"store:{store_id}"]
        if page.product.product_reference:
            values.append(f"product:{page.product.product_reference}")
        if page.product.sku_reference:
            values.append(f"sku:{page.product.sku_reference}")
        return tuple(values)


def _optional_text(value: object, maximum: int) -> str | None:
    if not isinstance(value, (str, int, float)):
        return None
    normalized = str(value).strip()
    return normalized[:maximum] or None


class AgentObservationDecisionProjector:
    """Projects durable Agent observations through frozen Gateway Contract V1."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        gateway: AICSGateway,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway

    def __call__(self, submission: AgentObservationSubmission) -> IntakeResult:
        try:
            payload = PDDObservationPayload.model_validate_json(
                json.dumps(
                    submission.payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        except ValueError as exc:
            raise ObservationPipelineError("Agent observation payload is invalid") from exc
        if (
            payload.store_id != submission.store_id
            or payload.conversation_id != submission.conversation_id
            or payload.external_message_id != submission.external_message_id
        ):
            raise ObservationPipelineError("Agent observation envelope scope mismatch")

        context = {
            "customer_context_version": payload.schema_version,
            "store_id": payload.store_id,
            "store_name": payload.store_name,
            "conversation_id": payload.conversation_id,
            "customer_reference": payload.customer_reference,
            "product": payload.product,
            "transaction": payload.order,
            "privacy_filtered": True,
            "source": (
                "CHANNEL_AGENT_V2_2"
                if payload.schema_version.endswith("v2.2")
                else "CHANNEL_AGENT_V2_1"
            ),
            "ai_cs_scope": {
                "tenant_id": payload.catalog_tenant_id,
                "platform": canonical_catalog_platform(payload.catalog_platform),
                "store_code": payload.store_id,
                "product_id": (
                    payload.product.get("product_id")
                    or payload.product.get("product_reference")
                    or "PDD-CURRENT-PAGE-UNKNOWN"
                ),
                "sku_id": (
                    payload.product.get("sku_id")
                    or payload.product.get("sku_reference")
                ),
            },
        }
        service = ConversationService(
            self._uow_factory,
            self._gateway,
            decision_context_provider=lambda _message: context,
        )
        return service.receive(
            NormalizedMessage(
                channel="pdd",
                store_id=payload.store_id,
                conversation_id=payload.conversation_id,
                external_message_id=payload.external_message_id,
                sender="customer",
                content=payload.content,
                timestamp=payload.timestamp,
            )
        )


__all__ = [
    "AgentObservationContextProvider",
    "AgentObservationDecisionProjector",
    "ObservationPipelineError",
    "PDDObservationPayload",
    "PDDVisibleHistoryPayload",
]
