from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiKnowledgePublicationStatus(StrEnum):
    NOT_GENERATED = "NOT_GENERATED"
    PUBLISHED = "PUBLISHED"
    NEED_RESYNC = "NEED_RESYNC"
    SYNC_FAILED = "SYNC_FAILED"


class ProductKnowledgeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=40)
    store_code: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)

    @field_validator("tenant_id", "platform", "store_code", "product_id")
    @classmethod
    def safe_single_line(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\r" in normalized or "\n" in normalized:
            raise ValueError("知识范围字段不能为空或包含换行符")
        return normalized


class ProductKnowledgePublishRequest(ProductKnowledgeScope):
    schema_version: Literal["ai-product-knowledge-publication.v1"]
    idempotency_key: str = Field(min_length=1, max_length=255)
    product_name: str = Field(min_length=1, max_length=255)
    data_source: Literal["TEST", "INITIAL_IMPORT", "PILOT"]
    knowledge_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    document: str = Field(min_length=1, max_length=200_000)
    source_ids: list[str] = Field(min_length=1, max_length=100)
    operator: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key", "product_name", "document", "operator")
    @classmethod
    def non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("发布字段不能为空")
        return normalized

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_safe(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or "\r" in value or "\n" in value for value in normalized):
            raise ValueError("source_ids 必须为非空单行文本")
        return list(dict.fromkeys(normalized))


class ProductKnowledgePublishReceipt(BaseModel):
    schema_version: Literal["ai-product-knowledge-publication.v1"] = (
        "ai-product-knowledge-publication.v1"
    )
    publication_receipt_id: str
    product_id: str
    status: Literal["PUBLISHED"] = "PUBLISHED"
    active_collection: str
    knowledge_fingerprint: str
    chunk_count: int = Field(ge=1)
    embedding_count: int = Field(ge=1)
    published_at: datetime


class ProductKnowledgeVisibilityRequest(ProductKnowledgeScope):
    current_fingerprint: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class ProductKnowledgeVisibilityBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ProductKnowledgeVisibilityRequest] = Field(min_length=1, max_length=200)


class ProductKnowledgeVisibility(BaseModel):
    product_id: str
    status: AiKnowledgePublicationStatus
    active_collection: str
    chunk_count: int = Field(ge=0)
    embedding_count: int = Field(ge=0)
    indexed_fingerprint: str | None = None
    current_fingerprint: str | None = None
    updated_at: datetime | None = None


class ProductKnowledgeVisibilityBatchResponse(BaseModel):
    schema_version: Literal["ai-product-knowledge-visibility.v1"] = (
        "ai-product-knowledge-visibility.v1"
    )
    active_collection: str
    items: list[ProductKnowledgeVisibility]
