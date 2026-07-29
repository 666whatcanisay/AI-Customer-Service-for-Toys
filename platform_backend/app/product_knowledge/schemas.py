"""Schemas for the C-only product knowledge operations projection."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class KnowledgeTopicStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class ProductKnowledgeState(StrEnum):
    WELL_COVERED = "WELL_COVERED"
    BASIC_AVAILABLE = "BASIC_AVAILABLE"
    NEEDS_COMPLETION = "NEEDS_COMPLETION"


class KnowledgeDataStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"


class KnowledgeAiStatus(StrEnum):
    EFFECTIVE = "EFFECTIVE"
    PARTIALLY_AVAILABLE = "PARTIALLY_AVAILABLE"
    MISSING_KNOWLEDGE = "MISSING_KNOWLEDGE"
    UNCONFIRMED = "UNCONFIRMED"


class KnowledgeGapWorkflowStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    RESOLVED = "RESOLVED"


class OverviewStats(BaseModel):
    store_count: int | None = None
    product_count: int | None = None
    ai_usable_product_count: int | None = None
    gap_count: int | None = None
    pending_review_count: int | None = None


class TechnicalDetails(BaseModel):
    store_code: str | None = None
    platform: str | None = None
    product_id: str | None = None
    product_code: str | None = None
    sku_id: str | None = None
    sku_code: str | None = None
    source_id: str | None = None
    material_id: str | None = None
    revision: int | None = None
    content_hash: str | None = None


class StoreKnowledgeSummary(BaseModel):
    store_name: str
    platform_name: str
    remarks: str = ""
    product_count: int
    ai_usable_product_count: int
    gap_count: int
    pending_review_count: int
    technical_details: TechnicalDetails


class ProductKnowledgeOverview(BaseModel):
    generated_at: datetime
    has_data: bool
    stats: OverviewStats
    stores: list[StoreKnowledgeSummary]
    boundary_note: str


class TopicCoverage(BaseModel):
    key: str
    name: str
    level: str = Field(pattern="^[AB]$")
    status: KnowledgeTopicStatus
    evidence_summary: str | None = None


class KnowledgeGap(BaseModel):
    key: str
    title: str
    severity: str
    description: str
    recommended_action: str
    safe_fallback: str
    source: str


class SkuKnowledgeSummary(BaseModel):
    sku_name: str
    color_style: str | None
    specification_difference: str | None
    package_difference: str | None
    faq_count: int
    difference_confirmed: bool
    attributes: list[str]
    technical_details: TechnicalDetails


class ProductKnowledgeListItem(BaseModel):
    store_name: str
    product_name: str
    product_summary: str | None
    core_selling_points: list[str]
    applicable_age: str | None
    material_safety: str | None
    package_contents: str | None
    faq_count: int
    sku_names: list[str]
    coverage_percent: int
    ai_usable: bool
    knowledge_state: ProductKnowledgeState
    data_status: KnowledgeDataStatus
    ai_status: KnowledgeAiStatus
    answerable_topics: list[str]
    missing_topics: list[str]
    gap_count: int
    technical_details: TechnicalDetails


class ProductKnowledgeListResponse(BaseModel):
    items: list[ProductKnowledgeListItem]
    total: int


class FaqSummary(BaseModel):
    question: str
    recommended_reply: str
    answer_strategy: str
    risk_level: str
    sku_name: str | None = None


class SafetySummary(BaseModel):
    title: str
    content: str
    risk_level: str | None = None
    forbidden_claim: str | None = None
    handoff_condition: str | None = None


class KnowledgeSourceSummary(BaseModel):
    source_name: str
    source_type: str
    review_status: str | None = None
    technical_details: TechnicalDetails


class ProductOverviewDetail(BaseModel):
    product_name: str
    product_summary: str | None
    core_selling_points: list[str]
    applicable_age: str | None
    material: str | None
    package_contents: str | None
    usage_instructions: str | None
    technical_details: TechnicalDetails


class ProductKnowledgeDetail(BaseModel):
    store: StoreKnowledgeSummary
    product: ProductOverviewDetail
    skus: list[SkuKnowledgeSummary]
    faqs: list[FaqSummary]
    safety_information: list[SafetySummary]
    sources: list[KnowledgeSourceSummary]
    coverage_percent: int
    ai_usable: bool
    knowledge_state: ProductKnowledgeState
    data_status: KnowledgeDataStatus
    ai_status: KnowledgeAiStatus
    topic_coverage: list[TopicCoverage]
    answerable_topics: list[str]
    missing_topics: list[str]
    gaps: list[KnowledgeGap]
    next_actions: list[str]
    boundary_note: str


class KnowledgeGapListItem(BaseModel):
    store_name: str
    product_name: str
    sku_name: str
    missing_topic: str
    occurrence_count: int = Field(ge=1)
    impact_level: str
    priority: str = Field(pattern="^P[0-3]$")
    workflow_status: KnowledgeGapWorkflowStatus
    description: str
    recommended_action: str
    safe_fallback: str


class KnowledgeGapListResponse(BaseModel):
    items: list[KnowledgeGapListItem]
    total: int
