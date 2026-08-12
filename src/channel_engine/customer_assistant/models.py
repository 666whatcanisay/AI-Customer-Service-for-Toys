from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from channel_engine.gateway import GatewayRiskLevel


CUSTOMER_ASSISTANT_VERSION = "1.0"


class CustomerAssistantModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class CustomerServiceRuntimeState(StrEnum):
    STARTING = "STARTING"
    PDD_LOGIN_REQUIRED = "PDD_LOGIN_REQUIRED"
    PDD_AUTHENTICATED = "PDD_AUTHENTICATED"
    CUSTOMER_SERVICE_READY = "CUSTOMER_SERVICE_READY"
    CUSTOMER_SERVICE_RUNNING = "CUSTOMER_SERVICE_RUNNING"
    HUMAN_INTERVENTION = "HUMAN_INTERVENTION"
    STOPPED = "STOPPED"


class AssistantWorkState(StrEnum):
    BUFFERING = "BUFFERING"
    GENERATING = "GENERATING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class BufferedMessageDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"


class ContextPageState(StrEnum):
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    ORDER = "ORDER"
    AFTERSALES = "AFTERSALES"
    PRODUCT = "PRODUCT"
    UNKNOWN = "UNKNOWN"


class ProductContext(CustomerAssistantModel):
    product_reference: str | None = Field(default=None, max_length=255)
    product_name: str | None = Field(default=None, max_length=512)
    sku_reference: str | None = Field(default=None, max_length=255)
    sku_name: str | None = Field(default=None, max_length=512)
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def bound_attributes(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 32:
            raise ValueError("product context cannot contain more than 32 attributes")
        for key, item in value.items():
            if not key.strip() or len(key) > 80 or len(item) > 512:
                raise ValueError("product context attribute is outside its bound")
        return value


class TransactionContext(CustomerAssistantModel):
    order_reference: str | None = Field(default=None, max_length=255)
    order_status: str | None = Field(default=None, max_length=128)
    logistics_status: str | None = Field(default=None, max_length=128)
    aftersales_status: str | None = Field(default=None, max_length=128)
    payment_data_included: Literal[False] = False
    address_data_included: Literal[False] = False


class PageContext(CustomerAssistantModel):
    store_id: str = Field(min_length=1, max_length=128)
    catalog_tenant_id: str = Field(
        default="CHANNEL-AGENT-PILOT", min_length=1, max_length=100
    )
    catalog_platform: str = Field(default="pdd", min_length=1, max_length=40)
    store_name: str | None = Field(default=None, min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    state: ContextPageState
    product: ProductContext = Field(default_factory=ProductContext)
    captured_at: AwareDatetime
    read_only: Literal[True] = True
    page_write_operations: Literal[0] = 0


class BufferedCustomerMessage(CustomerAssistantModel):
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
        repr=False,
    )
    timestamp: AwareDatetime
    received_at: AwareDatetime
    privacy_filtered: Literal[True] = True
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def from_redacted(
        cls,
        *,
        store_id: str,
        conversation_id: str,
        external_message_id: str,
        content: str,
        timestamp: datetime,
        received_at: datetime,
    ) -> "BufferedCustomerMessage":
        customer_reference = "sha256:" + hashlib.sha256(
            json.dumps(
                [store_id, conversation_id],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            store_id=store_id,
            conversation_id=conversation_id,
            external_message_id=external_message_id,
            customer_reference=customer_reference,
            content=content,
            timestamp=timestamp,
            received_at=received_at,
            content_digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )


class ConversationHistoryEntry(CustomerAssistantModel):
    """Privacy-filtered visible chat history from the selected conversation."""

    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["customer", "operator"]
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
        repr=False,
    )
    timestamp: AwareDatetime
    privacy_filtered: Literal[True] = True
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConversationTurn(CustomerAssistantModel):
    turn_id: str = Field(pattern=r"^assistant-turn:[a-f0-9]{64}$")
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    messages: tuple[BufferedCustomerMessage, ...] = Field(min_length=1, max_length=32)
    combined_question: str = Field(min_length=1, max_length=8_000, repr=False)
    opened_at: AwareDatetime
    closed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_alignment(self) -> "ConversationTurn":
        ordered = tuple(
            sorted(
                self.messages,
                key=lambda item: (item.timestamp, item.external_message_id),
            )
        )
        if ordered != self.messages:
            raise ValueError("conversation turn messages must be ordered")
        for message in self.messages:
            if (
                message.store_id != self.store_id
                or message.conversation_id != self.conversation_id
                or message.customer_reference != self.customer_reference
            ):
                raise ValueError("conversation turn crossed its store/customer boundary")
        if self.combined_question != "\n".join(item.content for item in self.messages):
            raise ValueError("combined question must preserve the ordered messages")
        return self


class CustomerContext(CustomerAssistantModel):
    context_id: str = Field(pattern=r"^customer-context:[a-f0-9]{64}$")
    turn_id: str = Field(pattern=r"^assistant-turn:[a-f0-9]{64}$")
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    page: PageContext
    transaction: TransactionContext
    conversation_history: tuple[BufferedCustomerMessage, ...] = Field(max_length=50)
    visible_conversation_history: tuple[ConversationHistoryEntry, ...] = Field(
        default=(), max_length=100
    )
    current_question: str = Field(min_length=1, max_length=8_000, repr=False)
    knowledge_scopes: tuple[str, ...] = Field(default=(), max_length=32)
    assembled_at: AwareDatetime
    contains_direct_customer_identity: Literal[False] = False

    @model_validator(mode="after")
    def validate_scope(self) -> "CustomerContext":
        if (
            self.page.store_id != self.store_id
            or self.page.conversation_id != self.conversation_id
        ):
            raise ValueError("page context does not match the current conversation")
        for message in self.conversation_history:
            if (
                message.store_id != self.store_id
                or message.conversation_id != self.conversation_id
                or message.customer_reference != self.customer_reference
            ):
                raise ValueError("conversation history crossed its isolation boundary")
        for message in self.visible_conversation_history:
            if (
                message.store_id != self.store_id
                or message.conversation_id != self.conversation_id
            ):
                raise ValueError("visible conversation history crossed its isolation boundary")
        return self

    def gateway_context(self) -> dict[str, object]:
        """Return bounded business context compatible with Gateway Contract V1."""

        product = self.page.product.model_dump(mode="json")
        transaction = self.transaction.model_dump(mode="json")
        product_reference = (
            self.page.product.product_reference or "PDD-CURRENT-PAGE-UNKNOWN"
        )
        return {
            "customer_context_version": CUSTOMER_ASSISTANT_VERSION,
            "store_id": self.store_id,
            "store_name": self.page.store_name,
            "conversation_id": self.conversation_id,
            "customer_reference": self.customer_reference,
            "page_state": self.page.state.value,
            "product": product,
            "transaction": transaction,
            "conversation_history": [
                {
                    "message_id": item.external_message_id,
                    "content": item.content,
                    "timestamp": item.timestamp.isoformat(),
                }
                for item in self.conversation_history
            ],
            "visible_conversation_history": [
                {
                    "message_id": item.external_message_id,
                    "sender": item.sender,
                    "content": item.content,
                    "timestamp": item.timestamp.isoformat(),
                }
                for item in self.visible_conversation_history
            ],
            "knowledge_scopes": list(self.knowledge_scopes),
            "privacy_filtered": True,
            "ai_cs_scope": {
                "tenant_id": self.page.catalog_tenant_id,
                "platform": self.page.catalog_platform,
                "store_code": self.store_id,
                "product_id": product_reference,
                "sku_id": self.page.product.sku_reference,
            },
        }


class KnowledgeCitation(CustomerAssistantModel):
    reference: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=256)
    product_id: str | None = Field(default=None, max_length=160)
    sku_id: str | None = Field(default=None, max_length=160)
    source_kind: str | None = Field(default=None, max_length=64)


class AIReplyPackage(CustomerAssistantModel):
    package_version: Literal["1.0"] = CUSTOMER_ASSISTANT_VERSION
    turn_id: str = Field(pattern=r"^assistant-turn:[a-f0-9]{64}$")
    context_id: str = Field(pattern=r"^customer-context:[a-f0-9]{64}$")
    request_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    customer_question: str = Field(min_length=1, max_length=8_000, repr=False)
    action: Literal["SUGGEST_REPLY", "NO_ACTION"] = "SUGGEST_REPLY"
    reply_content: str | None = Field(default=None, min_length=1, max_length=8_000, repr=False)
    citations: tuple[KnowledgeCitation, ...] = Field(default=(), max_length=32)
    risk_level: GatewayRiskLevel
    ai_cs_action: str = Field(default="UNKNOWN", min_length=1, max_length=64)
    warnings: tuple[str, ...] = Field(default=(), max_length=32)
    required_fields: tuple[str, ...] = Field(default=(), max_length=32)
    requires_human_approval: Literal[True] = True
    state: Literal["WAITING_APPROVAL", "MANUAL_INTERVENTION"] = "WAITING_APPROVAL"
    gateway_version: str = Field(min_length=1, max_length=128)
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_action_content(self) -> "AIReplyPackage":
        if self.action == "SUGGEST_REPLY" and self.reply_content is None:
            raise ValueError("SUGGEST_REPLY requires reply content")
        if self.action == "NO_ACTION" and self.reply_content is not None:
            raise ValueError("NO_ACTION cannot contain locally invented reply content")
        if self.action == "NO_ACTION" and self.state != "MANUAL_INTERVENTION":
            raise ValueError("NO_ACTION must enter manual intervention")
        return self


class HumanSendConfirmation(CustomerAssistantModel):
    decision_id: str = Field(min_length=1, max_length=128)
    operator_id: str = Field(min_length=1, max_length=160)
    expected_store_id: str = Field(min_length=1, max_length=128)
    expected_conversation_id: str = Field(min_length=1, max_length=255)
    expected_customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    current_store_id: str = Field(min_length=1, max_length=128)
    current_conversation_id: str = Field(min_length=1, max_length=255)
    current_customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=512, repr=False)
    confirmed_at: AwareDatetime

    def assert_exact_target(self) -> None:
        if self.current_store_id != self.expected_store_id:
            raise ValueError("current store does not match the approved reply")
        if self.current_conversation_id != self.expected_conversation_id:
            raise ValueError("current conversation does not match the approved reply")
        if self.current_customer_reference != self.expected_customer_reference:
            raise ValueError("current customer does not match the approved reply")
        expected = f"CONFIRM SEND {self.decision_id}"
        if self.confirmation_phrase != expected:
            raise ValueError("explicit send confirmation phrase does not match")


class AssistantExecutionResult(CustomerAssistantModel):
    decision_id: str
    approval_id: str
    execution_id: str
    receipt_id: str | None
    outcome: Literal["SUCCESS", "FAILED", "UNKNOWN"]
    customer_message_sent: bool | None
    automatic_retry_allowed: bool
    manual_intervention_required: bool


class DesktopAssistantSnapshot(CustomerAssistantModel):
    assistant_version: Literal["1.0"] = CUSTOMER_ASSISTANT_VERSION
    runtime_state: CustomerServiceRuntimeState
    work_state: AssistantWorkState | None = None
    agent_online: bool
    pdd_status: str
    store_id: str | None = None
    store_name: str | None = Field(default=None, max_length=128)
    customer_reference: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    current_question: str | None = Field(default=None, repr=False)
    product_summary: str | None = None
    reply_package: AIReplyPackage | None = Field(default=None, repr=False)
    risk_notice: str | None = None
    available_actions: tuple[
        Literal["ADOPT_REPLY", "EDIT_REPLY", "REGENERATE", "CONFIRM_SEND"], ...
    ] = ()
    real_send_enabled: Literal[False] = False
    auto_reply_enabled: Literal[False] = False
    manual_approval_required: Literal[True] = True
    updated_at: AwareDatetime
