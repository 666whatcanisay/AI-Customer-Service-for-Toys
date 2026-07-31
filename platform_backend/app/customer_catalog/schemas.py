"""Frozen V1 schemas for the C-owned customer available catalog."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge_publishing.schemas import AiKnowledgeStatus, EmbeddingStatus


CATALOG_SCHEMA_VERSION = "pilot-business-catalog.v1.1"
CUSTOMER_AI_KNOWLEDGE_SCHEMA_VERSION = "customer-product-ai-knowledge-status.v1"
ACTIVATION_RESPONSE_SCHEMA_VERSION = "pilot-business-catalog-activation-response.v1"
ACTIVATION_RECEIPT_SCHEMA_VERSION = "pilot-business-catalog-activation-receipt.v1"


class DataSource(StrEnum):
    TEST = "TEST"
    PILOT = "PILOT"


class CustomerServiceStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class CatalogResultStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class CatalogEntityType(StrEnum):
    STORE = "STORE"
    PRODUCT = "PRODUCT"
    SKU = "SKU"


class ActivatableEntityType(StrEnum):
    STORE = "STORE"
    PRODUCT = "PRODUCT"


class ActivationSource(StrEnum):
    LEGACY_INITIALIZATION = "LEGACY_INITIALIZATION"
    OPERATOR = "OPERATOR"


class CatalogWarning(BaseModel):
    code: str
    entity_type: CatalogEntityType
    count: int = Field(ge=1)
    message: str


class CustomerCatalogStore(BaseModel):
    entity_type: CatalogEntityType = CatalogEntityType.STORE
    tenant_id: str
    platform: str
    store_code: str
    store_name: str
    data_source: DataSource
    customer_service_status: CustomerServiceStatus = CustomerServiceStatus.ENABLED
    allow_auto_send: bool = False


class CustomerCatalogProduct(BaseModel):
    entity_type: CatalogEntityType = CatalogEntityType.PRODUCT
    product_id: str
    platform: str
    store_code: str
    product_name_official: str
    product_name_display: str
    sales_status: str
    knowledge_status: str
    age_min: int | None = None
    age_max: int | None = None
    safety_summary: str | None = None
    data_source: DataSource
    customer_service_status: CustomerServiceStatus = CustomerServiceStatus.ENABLED


class CustomerProductAiKnowledgeStatus(BaseModel):
    schema_version: str = CUSTOMER_AI_KNOWLEDGE_SCHEMA_VERSION
    product_id: str
    status: AiKnowledgeStatus
    embedding_status: EmbeddingStatus
    publication_receipt_id: str | None = None
    active_collection: str | None = None
    chunk_count: int = Field(ge=0)
    embedding_count: int = Field(ge=0)
    indexed_fingerprint: str | None = None
    published_at: datetime | None = None
    last_checked_at: datetime


class CustomerCatalogSku(BaseModel):
    entity_type: CatalogEntityType = CatalogEntityType.SKU
    sku_id: str
    product_id: str
    sku_code: str
    sku_name_official: str
    sku_name_display: str
    relation_type: str
    canonical_sku_id: str | None = None
    reference_sku_id: str | None = None
    component_sku_refs: list[str]
    data_source: DataSource
    customer_service_status: CustomerServiceStatus = CustomerServiceStatus.ENABLED


class StoreCatalogResponse(BaseModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    result_status: CatalogResultStatus
    items: list[CustomerCatalogStore]
    total: int = Field(ge=0)
    warnings: list[CatalogWarning]


class ProductCatalogResponse(BaseModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    result_status: CatalogResultStatus
    items: list[CustomerCatalogProduct]
    total: int = Field(ge=0)
    warnings: list[CatalogWarning]


class SkuCatalogResponse(BaseModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    result_status: CatalogResultStatus
    items: list[CustomerCatalogSku]
    total: int = Field(ge=0)
    warnings: list[CatalogWarning]


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_service_status: CustomerServiceStatus
    confirmed_by: str = Field(min_length=1, max_length=128)
    confirmation_note: str = Field(min_length=1, max_length=500)

    @field_validator("confirmed_by", "confirmation_note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ActivationEntity(BaseModel):
    entity_type: ActivatableEntityType
    entity_ref: str
    data_source: DataSource
    customer_service_status: CustomerServiceStatus
    customer_service_status_updated_at: datetime | None = None
    customer_service_status_updated_by: str | None = None


class ActivationReceipt(BaseModel):
    schema_version: str = ACTIVATION_RECEIPT_SCHEMA_VERSION
    activation_receipt_id: str
    entity_type: ActivatableEntityType
    entity_ref: str
    data_source: DataSource
    previous_status: CustomerServiceStatus | None
    customer_service_status: CustomerServiceStatus
    activation_source: ActivationSource
    confirmed_by: str
    confirmation_note: str
    confirmed_at: datetime


class ActivationResponse(BaseModel):
    schema_version: str = ACTIVATION_RESPONSE_SCHEMA_VERSION
    changed: bool
    entity: ActivationEntity
    activation_receipt: ActivationReceipt | None
    server_time: datetime


class BatchActivationResultStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class BatchActivationItemStatus(StrEnum):
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    FAILED = "FAILED"


class BatchActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[str] = Field(min_length=1, max_length=100)
    confirmed_by: str = Field(min_length=1, max_length=128)
    confirmation_note: str = Field(min_length=1, max_length=500)

    @field_validator("product_ids")
    @classmethod
    def product_ids_must_be_unique(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or "\r" in value or "\n" in value for value in normalized):
            raise ValueError("product_ids 必须是非空单行文本")
        if len(set(normalized)) != len(normalized):
            raise ValueError("product_ids 不能重复")
        return normalized

    @field_validator("confirmed_by", "confirmation_note")
    @classmethod
    def strip_batch_text(cls, value: str) -> str:
        return value.strip()


class BatchActivationItem(BaseModel):
    product_id: str
    status: BatchActivationItemStatus
    activation_receipt: ActivationReceipt | None = None
    error_code: str | None = None
    message: str


class BatchActivationResponse(BaseModel):
    schema_version: str = "pilot-business-catalog-batch-activation.v1"
    result_status: BatchActivationResultStatus
    target_status: CustomerServiceStatus = CustomerServiceStatus.ENABLED
    items: list[BatchActivationItem]
    changed_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    server_time: datetime


class ActivationReceiptListResponse(BaseModel):
    items: list[ActivationReceipt]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    size: int = Field(ge=1)
