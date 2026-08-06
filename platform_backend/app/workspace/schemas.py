"""Strict Store Context Resolver V1 wire objects."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.iam.schemas import RoleName


STORE_CONTEXT_SCHEMA_VERSION = "ai-cs.store-context.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceContextState(StrEnum):
    READY = "READY"
    STORE_SELECTION_REQUIRED = "STORE_SELECTION_REQUIRED"


class ResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    STORE_SELECTION_REQUIRED = "STORE_SELECTION_REQUIRED"
    PRODUCT_CONFIRMATION_REQUIRED = "PRODUCT_CONFIRMATION_REQUIRED"
    SKU_CONFIRMATION_REQUIRED = "SKU_CONFIRMATION_REQUIRED"
    UNKNOWN = "UNKNOWN"


class StoreContextProjection(StrictModel):
    store_id: int
    tenant_id: str
    platform: str
    store_code: str
    store_name: str
    is_default: bool


class ProductCandidate(StrictModel):
    product_id: str
    display_name: str


class SkuCandidate(StrictModel):
    sku_id: str
    display_name: str


class WorkspaceContextResponse(StrictModel):
    schema_version: str = STORE_CONTEXT_SCHEMA_VERSION
    user_id: str
    roles: list[RoleName]
    all_store_access: bool
    state: WorkspaceContextState
    stores: list[StoreContextProjection]
    effective_store: StoreContextProjection | None


class ConversationRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"


class ConversationMessage(StrictModel):
    role: ConversationRole
    content: str = Field(min_length=1, max_length=4000)


class ContextResolutionRequest(StrictModel):
    conversation: list[ConversationMessage] = Field(min_length=1, max_length=100)
    store_id: int | None = Field(default=None, ge=1)
    confirmed_product_id: str | None = Field(default=None, min_length=1, max_length=128)
    confirmed_sku_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def sku_confirmation_requires_product(self) -> "ContextResolutionRequest":
        if self.confirmed_sku_id is not None and self.confirmed_product_id is None:
            raise ValueError("confirmed_sku_id requires confirmed_product_id")
        return self


class ContextResolutionResponse(StrictModel):
    schema_version: str = STORE_CONTEXT_SCHEMA_VERSION
    resolution_id: str
    status: ResolutionStatus
    store: StoreContextProjection | None
    product: ProductCandidate | None
    sku: SkuCandidate | None
    product_candidates: list[ProductCandidate]
    sku_candidates: list[SkuCandidate]
    reason_code: str
    created_at: datetime


class ResolutionAuditProjection(StrictModel):
    resolution_id: str
    user_id: str
    store_id: int | None
    status: ResolutionStatus
    product_id: str | None
    sku_id: str | None
    product_candidate_ids: list[str]
    sku_candidate_ids: list[str]
    reason_code: str
    created_at: datetime


class ResolutionAuditListResponse(StrictModel):
    schema_version: str = STORE_CONTEXT_SCHEMA_VERSION
    items: list[ResolutionAuditProjection]
    total: int


class ChatContext(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=96)
    platform: str = Field(min_length=1, max_length=32)
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str = Field(min_length=1, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)


class WorkspaceChatRequest(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    context: ChatContext | None = None
    resolution_id: str | None = Field(default=None, min_length=36, max_length=36)

    @model_validator(mode="after")
    def require_one_context_source(self) -> "WorkspaceChatRequest":
        if (self.context is None) == (self.resolution_id is None):
            raise ValueError("exactly one of context or resolution_id is required")
        return self
