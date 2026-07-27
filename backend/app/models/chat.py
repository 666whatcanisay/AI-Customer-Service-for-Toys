from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class FrozenChatContext(BaseModel):
    """Frozen V0.3.1 test scope supplied by the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: Literal["TENANT-PDD-SM-TEST"]
    platform: Literal["pdd"]
    store_code: Literal["PDD-SM"]
    product_id: str = Field(..., min_length=1, max_length=100)
    sku_id: str | None = Field(default=None, max_length=100)

    @field_validator("platform", "store_code", "product_id")
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
