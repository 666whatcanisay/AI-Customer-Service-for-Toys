"""Frozen knowledge-quality-loop v1 API schemas.

The C platform accepts controlled metadata and returns business summaries.  It
does not expose uploaded binaries to B, nor does it claim publication to RAG.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeMaterialType(StrEnum):
    PRODUCT_SPEC = "PRODUCT_SPEC"
    SAFETY_INSTRUCTION = "SAFETY_INSTRUCTION"
    ASSEMBLY_GUIDE = "ASSEMBLY_GUIDE"
    FAQ_SOURCE = "FAQ_SOURCE"
    OTHER = "OTHER"


class KnowledgeTemplateType(StrEnum):
    PRODUCT_KNOWLEDGE = "PRODUCT_KNOWLEDGE"
    SKU_DIFFERENCE = "SKU_DIFFERENCE"
    FAQ = "FAQ"
    SAFETY_RULE = "SAFETY_RULE"
    AI_FEEDBACK = "AI_FEEDBACK"
    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"


class KnowledgeMaterialStatus(StrEnum):
    RECEIVED = "RECEIVED"
    RECOGNIZED = "RECOGNIZED"
    REVIEWING = "REVIEWING"
    APPROVED_FOR_ANALYSIS = "APPROVED_FOR_ANALYSIS"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    REJECTED = "REJECTED"


class KnowledgeQualityOverallStatus(StrEnum):
    ANALYZED = "ANALYZED"
    FAILED = "FAILED"


class KnowledgeQualityGapSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class KnowledgeQualityGapStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class KnowledgeMaterialReviewDecision(StrEnum):
    APPROVE_FOR_ANALYSIS = "APPROVE_FOR_ANALYSIS"
    REJECT = "REJECT"


class RecognitionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readable: bool
    file_extension: str
    detected_fields: list[str]
    missing_expected_fields: list[str]
    privacy_reminder: str


class KnowledgeTemplateRecognitionSummary(RecognitionSummary):
    """C Admin-only template metadata; never added to the frozen A input."""

    template_type: KnowledgeTemplateType | None = None
    template_name: str | None = None
    record_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    high_risk_source_confirmed: bool | None = None


class KnowledgeMaterialReceipt(BaseModel):
    material_id: str
    revision: int
    content_hash: str
    material_status: KnowledgeMaterialStatus
    recognition_summary: KnowledgeTemplateRecognitionSummary


class KnowledgeMaterialSummary(BaseModel):
    material_id: str
    revision: int
    store_code: str
    product_id: str
    sku_id: str | None
    material_type: KnowledgeMaterialType
    display_name: str
    original_filename: str
    content_hash: str
    redaction_version: str
    recognition_summary: KnowledgeTemplateRecognitionSummary
    material_status: KnowledgeMaterialStatus
    submitted_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeMaterialDetail(KnowledgeMaterialSummary):
    """Admin-only readable excerpt; never the original upload binary."""

    analysis_text_preview: str


class KnowledgeMaterialListResponse(BaseModel):
    items: list[KnowledgeMaterialSummary]
    total: int
    page: int
    size: int


class KnowledgeMaterialReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    decision: KnowledgeMaterialReviewDecision
    reviewed_by: str = Field(min_length=1, max_length=128)
    review_note: str = Field(min_length=1, max_length=4000)


class KnowledgeQualityAnalysisInput(BaseModel):
    material_id: str
    revision: int
    content_hash: str
    store_code: str
    product_id: str
    sku_id: str | None
    material_type: KnowledgeMaterialType
    analysis_text: str
    recognition_summary: RecognitionSummary


class KnowledgeQualityAnalysisInputListResponse(BaseModel):
    items: list[KnowledgeQualityAnalysisInput]
    total: int


class KnowledgeQualityGapCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_code: str = Field(min_length=1, max_length=80)
    severity: KnowledgeQualityGapSeverity
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=4000)
    recommended_action: str = Field(min_length=1, max_length=4000)


class KnowledgeQualityGap(KnowledgeQualityGapCreate):
    """C-generated governance fields are returned, never submitted by A."""

    gap_id: str
    status: KnowledgeQualityGapStatus


class KnowledgeQualityAnalysisResultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=8, max_length=80)
    analysis_run_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=8000)
    gaps: list[KnowledgeQualityGapCreate] = Field(default_factory=list, max_length=100)


class KnowledgeQualityAssessmentResponse(BaseModel):
    assessment_id: str
    material_id: str
    revision: int
    content_hash: str
    analysis_run_id: str
    model_version: str
    prompt_version: str
    overall_status: KnowledgeQualityOverallStatus
    summary: str
    gaps: list[KnowledgeQualityGap]
    created_at: datetime


class KnowledgeQualityAssessmentListResponse(BaseModel):
    items: list[KnowledgeQualityAssessmentResponse]
    total: int


class CustomerKnowledgeStatusValue(StrEnum):
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NO_APPROVED_MATERIAL = "NO_APPROVED_MATERIAL"
    UNAVAILABLE = "UNAVAILABLE"


class CustomerKnowledgeStatusResponse(BaseModel):
    status: CustomerKnowledgeStatusValue
    summary: str
    last_checked_at: datetime


def gap_as_dict(gap: KnowledgeQualityGap) -> dict[str, Any]:
    return gap.model_dump(mode="json")
