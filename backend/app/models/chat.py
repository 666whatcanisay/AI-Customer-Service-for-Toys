from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class VerifiedProductContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_reference: str | None = Field(default=None, max_length=255)
    product_name: str | None = Field(default=None, max_length=512)
    sku_reference: str | None = Field(default=None, max_length=255)
    sku_name: str | None = Field(default=None, max_length=512)
    attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def attributes_are_bounded(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 32:
            raise ValueError("verified product attributes exceed the bounded context")
        if any(
            not key.strip() or len(key) > 80 or len(item) > 512
            for key, item in value.items()
        ):
            raise ValueError("verified product attribute is invalid")
        return value


class VerifiedTransactionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    order_reference: str | None = Field(default=None, max_length=255)
    order_status: str | None = Field(default=None, max_length=128)
    logistics_status: str | None = Field(default=None, max_length=128)
    aftersales_status: str | None = Field(default=None, max_length=128)
    payment_data_included: bool = False
    address_data_included: bool = False

    @model_validator(mode="after")
    def reject_sensitive_transaction_fields(self) -> "VerifiedTransactionContext":
        if self.payment_data_included or self.address_data_included:
            raise ValueError("payment and address data are forbidden in AI context")
        return self


class VerifiedConversationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: str = Field(min_length=1, max_length=255)
    sender: str | None = Field(default=None, max_length=32)
    content: str = Field(min_length=1, max_length=2_000)
    timestamp: str = Field(min_length=1, max_length=64)


class FrozenChatContext(BaseModel):
    """Caller-supplied business scope from the C-owned customer catalog.

    A validates only that the identifiers are safe and complete.  Product
    permission and catalog availability remain C responsibilities.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(..., min_length=1, max_length=100)
    platform: str = Field(..., min_length=1, max_length=40)
    store_code: str = Field(..., min_length=1, max_length=100)
    product_id: str = Field(..., min_length=1, max_length=100)
    sku_id: str | None = Field(default=None, max_length=100)
    verified_product: VerifiedProductContext | None = None
    verified_transaction: VerifiedTransactionContext | None = None
    recent_conversation: tuple[VerifiedConversationEntry, ...] = Field(
        default=(), max_length=20
    )

    @field_validator("tenant_id", "platform", "store_code", "product_id")
    @classmethod
    def required_scope_must_be_safe(cls, value: str) -> str:
        value = value.strip()
        if not value or "\r" in value or "\n" in value:
            raise ValueError("范围字段不能为空或包含换行符")
        return value

    @field_validator("sku_id")
    @classmethod
    def optional_sku_must_be_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if "\r" in value or "\n" in value:
            raise ValueError("SKU 不能包含换行符")
        return value

    @model_validator(mode="after")
    def verified_context_matches_scope(self) -> "FrozenChatContext":
        if self.verified_product is None:
            return self
        product_reference = self.verified_product.product_reference
        if (
            product_reference
            and not self.product_id.startswith("__STORE_LEVEL_")
            and product_reference != self.product_id
        ):
            raise ValueError("verified product does not match the frozen product scope")
        sku_reference = self.verified_product.sku_reference
        if sku_reference and self.sku_id and sku_reference != self.sku_id:
            raise ValueError("verified SKU does not match the frozen SKU scope")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, min_length=1, max_length=4000)
    message: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description="Legacy alias; new clients must send question.",
    )
    context: FrozenChatContext | None = None

    @field_validator("question", "message")
    @classmethod
    def message_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value

    @model_validator(mode="after")
    def exactly_one_question_field(self) -> "ChatRequest":
        if bool(self.question) == bool(self.message):
            raise ValueError("必须且只能提供 question；message 仅用于旧客户端兼容")
        if self.question and self.context is None:
            raise ValueError("新规范 question 请求必须提供冻结 context")
        if self.message and self.context is not None:
            raise ValueError("context 只能与新规范 question 一起使用")
        return self

    @property
    def resolved_question(self) -> str:
        return self.question or self.message or ""


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    context: FrozenChatContext | None = None

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("检索问题不能为空")
        return value


class AIOnlineTestRequest(BaseModel):
    """A bounded, no-side-effect test invocation for an implemented AI module."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=4000)
    context: FrozenChatContext
    include_diagnostics: bool = False

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class ExperienceEvaluationRunRequest(BaseModel):
    """An explicit operator request to evaluate one approved case snapshot."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., min_length=1, max_length=64)
    revision: int = Field(..., ge=1)

    @field_validator("case_id")
    @classmethod
    def case_id_must_be_safe(cls, value: str) -> str:
        value = value.strip()
        if not value or "\r" in value or "\n" in value:
            raise ValueError("case_id must be a single non-empty line")
        return value


class FeedbackAnalysisRunRequest(BaseModel):
    """An explicit, bounded local request to analyze C-confirmed feedback."""

    model_config = ConfigDict(extra="forbid")

    maximum: int = Field(default=1, ge=1, le=100)


class KnowledgeQualityRunRequest(BaseModel):
    """An explicit, bounded local run over C-approved material snapshots."""

    model_config = ConfigDict(extra="forbid")

    maximum: int = Field(default=1, ge=1, le=20)


class ModelConfigUpdate(BaseModel):
    provider: str = Field(default="ollama", min_length=1, max_length=40)
    model: str = Field(default="qwen3.5:9b", min_length=1, max_length=100)
    api_key: SecretStr | None = None
    clear_api_key: bool = False

    @field_validator("provider", "model")
    @classmethod
    def value_must_be_safe(cls, value: str) -> str:
        value = value.strip()
        if not value or "\r" in value or "\n" in value:
            raise ValueError("配置值不能为空或包含换行符")
        return value

    @field_validator("provider")
    @classmethod
    def provider_must_be_supported(cls, value: str) -> str:
        if value not in {"ollama", "bailian"}:
            raise ValueError("仅支持 ollama 或 bailian")
        return value
