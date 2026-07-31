from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiKnowledgeStatus(StrEnum):
    NOT_GENERATED = "NOT_GENERATED"
    GENERATING = "GENERATING"
    PUBLISHED = "PUBLISHED"
    SYNC_FAILED = "SYNC_FAILED"
    NEED_RESYNC = "NEED_RESYNC"


class EmbeddingStatus(StrEnum):
    NOT_GENERATED = "NOT_GENERATED"
    GENERATING = "GENERATING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AiKnowledgeSummary(BaseModel):
    status: AiKnowledgeStatus
    embedding_status: EmbeddingStatus
    current_fingerprint: str | None = None
    indexed_fingerprint: str | None = None
    active_collection: str | None = None
    chunk_count: int = Field(ge=0)
    embedding_count: int = Field(ge=0)
    updated_at: datetime | None = None
    published_at: datetime | None = None
    last_error_code: str | None = None


class ProductKnowledgePublishCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: str = Field(min_length=1, max_length=128)
    confirmation_note: str = Field(min_length=1, max_length=500)

    @field_validator("operator", "confirmation_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProductKnowledgeCheckCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: str = Field(min_length=1, max_length=128)

    @field_validator("operator")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProductKnowledgePublicationReceiptSchema(BaseModel):
    publication_receipt_id: str
    product_id: str
    knowledge_fingerprint: str
    active_collection: str
    chunk_count: int = Field(ge=1)
    embedding_count: int = Field(ge=1)
    status: AiKnowledgeStatus
    operator: str
    created_at: datetime


class ProductKnowledgePublicationResponse(BaseModel):
    schema_version: str = "product-knowledge-publication.v1"
    changed: bool
    product_id: str
    ai_knowledge: AiKnowledgeSummary
    publication_receipt: ProductKnowledgePublicationReceiptSchema | None = None


class ProductKnowledgePublicationReceiptList(BaseModel):
    items: list[ProductKnowledgePublicationReceiptSchema]
    total: int = Field(ge=0)
