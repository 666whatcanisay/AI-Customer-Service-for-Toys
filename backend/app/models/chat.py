from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr, field_validator


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("检索问题不能为空")
        return value


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
