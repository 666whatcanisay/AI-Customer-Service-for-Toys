"""Frozen MVP-PLUS-01 schemas and lifecycle rules for experience cases."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExperienceCaseSourceType(StrEnum):
    CUSTOMER_SERVICE_SUBMITTED = "CUSTOMER_SERVICE_SUBMITTED"
    SUPERVISOR_SELECTED = "SUPERVISOR_SELECTED"
    AI_DISCOVERED = "AI_DISCOVERED"
    MANUAL_IMPORTED = "MANUAL_IMPORTED"


class ExperienceCaseFeedbackType(StrEnum):
    ADOPTED = "ADOPTED"
    EDITED_ADOPTED = "EDITED_ADOPTED"
    CORRECTION = "CORRECTION"
    ESCALATED = "ESCALATED"


class ExperienceCaseReviewStatus(StrEnum):
    NEW = "NEW"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EvaluationStatus(StrEnum):
    NOT_EXPORTED = "NOT_EXPORTED"
    EXPORTED = "EXPORTED"
    EVALUATED = "EVALUATED"
    WRITEBACK_REJECTED = "WRITEBACK_REJECTED"


ALLOWED_REVIEW_TRANSITIONS: dict[ExperienceCaseReviewStatus, set[ExperienceCaseReviewStatus]] = {
    ExperienceCaseReviewStatus.NEW: {
        ExperienceCaseReviewStatus.REVIEWING,
        ExperienceCaseReviewStatus.REJECTED,
    },
    ExperienceCaseReviewStatus.REVIEWING: {
        ExperienceCaseReviewStatus.APPROVED,
        ExperienceCaseReviewStatus.REJECTED,
    },
    ExperienceCaseReviewStatus.APPROVED: set(),
    ExperienceCaseReviewStatus.REJECTED: set(),
}


class CustomerExperienceCaseCreate(BaseModel):
    """B-facing submission. Governance and review fields are server-controlled."""

    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=96)
    product_id: str | None = Field(default=None, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)
    question: str = Field(min_length=1, max_length=8000)
    ai_answer: str = Field(min_length=1, max_length=12000)
    final_answer: str = Field(min_length=1, max_length=12000)
    feedback_type: ExperienceCaseFeedbackType
    created_by: str = Field(min_length=1, max_length=128)


class CustomerExperienceCaseCreated(BaseModel):
    case_id: str
    revision: int
    review_status: ExperienceCaseReviewStatus
    created_at: datetime
    updated_at: datetime


class CustomerExperienceCaseProjection(BaseModel):
    case_id: str
    revision: int
    store_code: str
    product_id: str | None
    sku_id: str | None
    feedback_type: ExperienceCaseFeedbackType
    review_status: ExperienceCaseReviewStatus
    created_at: datetime
    updated_at: datetime


class CustomerExperienceCaseListResponse(BaseModel):
    items: list[CustomerExperienceCaseProjection]
    total: int
    page: int
    size: int


class AdminExperienceCaseResponse(BaseModel):
    case_id: str
    revision: int
    source_type: ExperienceCaseSourceType
    store_code: str
    product_id: str | None
    sku_id: str | None
    question: str
    ai_answer: str
    final_answer: str
    feedback_type: ExperienceCaseFeedbackType
    created_by: str
    review_status: ExperienceCaseReviewStatus
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    export_revision: str | None
    content_hash: str | None
    redaction_version: str
    evaluation_status: EvaluationStatus
    latest_evaluation_run_id: str | None
    created_at: datetime
    updated_at: datetime


class AdminExperienceCaseListResponse(BaseModel):
    items: list[AdminExperienceCaseResponse]
    total: int
    page: int
    size: int


class ExperienceCaseReviewUpdate(BaseModel):
    """C Admin-only review data; content fields cannot be edited through this API."""

    model_config = ConfigDict(extra="forbid")

    review_status: ExperienceCaseReviewStatus
    review_note: str | None = Field(default=None, max_length=4000)
    reviewed_by: str | None = Field(default=None, min_length=1, max_length=128)


class ExportContext(BaseModel):
    store_code: str
    product_id: str | None
    sku_id: str | None


class ExperienceCaseExportItem(BaseModel):
    case_id: str
    revision: int
    export_revision: str
    store_code: str
    product_id: str | None
    sku_id: str | None
    question: str
    ai_answer: str
    final_answer: str
    context: ExportContext
    content_hash: str
    redaction_version: str


class ExperienceCaseExportResponse(BaseModel):
    items: list[ExperienceCaseExportItem]
    next_cursor: str | None


class ExperienceCaseEvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    export_revision: str = Field(min_length=1, max_length=160)
    content_hash: str = Field(min_length=1, max_length=80)
    evaluation_run_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=160)
    result: dict[str, Any]
    suggestions: list[dict[str, Any]]


class ExperienceCaseEvaluationResponse(BaseModel):
    evaluation_run_id: str
    case_id: str
    revision: int
    export_revision: str
    evaluation_status: EvaluationStatus
    model_version: str
    prompt_version: str
    result: dict[str, Any]
    suggestions: list[dict[str, Any]]
    recorded_at: datetime


class AiOptimizationCaseResponse(BaseModel):
    case_id: str
    revision: int
    store_code: str
    product_id: str | None
    sku_id: str | None
    question: str
    ai_answer: str
    final_answer: str
    feedback_type: ExperienceCaseFeedbackType
    export_revision: str
    content_hash: str
    evaluation_status: EvaluationStatus
    latest_evaluation_run_id: str | None
    latest_evaluation: ExperienceCaseEvaluationResponse | None


class AiOptimizationCaseListResponse(BaseModel):
    items: list[AiOptimizationCaseResponse]
    total: int
    page: int
    size: int


class ExperienceCaseEvaluationListResponse(BaseModel):
    items: list[ExperienceCaseEvaluationResponse]
    total: int
