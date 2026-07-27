"""Frozen v1 request, response, and lifecycle schemas for AI response feedback."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIResponseFeedbackType(StrEnum):
    FACT_ERROR = "FACT_ERROR"
    MISSING_INFO = "MISSING_INFO"
    STYLE_ISSUE = "STYLE_ISSUE"
    RISK_ISSUE = "RISK_ISSUE"
    OTHER = "OTHER"


class AIResponseFeedbackStatus(StrEnum):
    NEW = "NEW"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"


class FeedbackContext(BaseModel):
    """The controlled B context; raw chat context and unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=96)
    product_id: str | None = Field(default=None, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)


class AIResponseFeedbackCreate(BaseModel):
    """B-to-C submission. C-controlled lifecycle fields are forbidden."""

    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=96)
    product_id: str | None = Field(default=None, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)
    question: str = Field(min_length=1, max_length=8000)
    ai_answer: str = Field(min_length=1, max_length=12000)
    feedback_type: AIResponseFeedbackType
    feedback_note: str | None = Field(default=None, max_length=4000)
    final_answer: str | None = Field(default=None, max_length=12000)
    created_by: str = Field(min_length=1, max_length=128)
    context: FeedbackContext

    @model_validator(mode="after")
    def validate_controlled_context(self) -> "AIResponseFeedbackCreate":
        if self.context.store_code != self.store_code:
            raise ValueError("context.store_code must match store_code")
        if self.context.product_id != self.product_id:
            raise ValueError("context.product_id must match product_id")
        if self.context.sku_id != self.sku_id:
            raise ValueError("context.sku_id must match sku_id")
        if self.feedback_type is AIResponseFeedbackType.OTHER:
            if not self.feedback_note or not self.feedback_note.strip():
                raise ValueError("feedback_note is required when feedback_type is OTHER")
        return self


class AIResponseFeedbackCreated(BaseModel):
    feedback_id: str
    status: AIResponseFeedbackStatus


class AIResponseFeedbackProjection(BaseModel):
    feedback_id: str
    revision: int
    store_code: str
    product_id: str | None
    sku_id: str | None
    feedback_type: AIResponseFeedbackType
    status: AIResponseFeedbackStatus
    analysis_status: AIResponseFeedbackStatus
    created_at: datetime


class AIResponseFeedbackListResponse(BaseModel):
    items: list[AIResponseFeedbackProjection]
    total: int
    page: int
    size: int


class AIResponseFeedbackConfirmation(BaseModel):
    """C-owned internal control for making a de-identified record exportable."""

    model_config = ConfigDict(extra="forbid")

    confirmed_by: str = Field(min_length=1, max_length=128)
    confirmation_reason: str = Field(min_length=1, max_length=4000)


class AIResponseFeedbackExportItem(BaseModel):
    feedback_id: str
    revision: int
    store_code: str
    product_id: str | None
    sku_id: str | None
    question: str
    ai_answer: str
    final_answer: str | None
    feedback_type: AIResponseFeedbackType
    feedback_note: str | None
    context: FeedbackContext
    content_hash: str
    redaction_version: str


class AIResponseFeedbackExportResponse(BaseModel):
    items: list[AIResponseFeedbackExportItem]
    next_cursor: str | None


class AIResponseFeedbackAnalysisCreate(BaseModel):
    """A-to-C evidence only; it cannot carry an instruction to take action."""

    model_config = ConfigDict(extra="forbid")

    feedback_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=8, max_length=80)
    feedback_type: AIResponseFeedbackType
    analysis_run_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=160)
    analysis: dict[str, Any] = Field(min_length=1)
    suggestions: list[dict[str, Any]]


class AIResponseFeedbackAnalysisResponse(BaseModel):
    feedback_id: str
    revision: int
    status: AIResponseFeedbackStatus
    analysis_status: AIResponseFeedbackStatus
    analysis_run_id: str
    model_version: str
    prompt_version: str
    analysis: dict[str, Any]
    suggestions: list[dict[str, Any]]
    recorded_at: datetime


class AdminAIResponseFeedbackAnalysisResult(BaseModel):
    """Read-only C Admin projection of completed A analysis evidence."""

    feedback_id: str
    revision: int
    content_hash: str
    feedback_type: AIResponseFeedbackType
    analysis_run_id: str
    analysis_status: AIResponseFeedbackStatus
    model_version: str
    prompt_version: str
    analysis: dict[str, Any]
    suggestions: list[dict[str, Any]]
    created_at: datetime
    question: str
    ai_answer: str
    final_answer: str | None


class AdminAIResponseFeedbackAnalysisResultListResponse(BaseModel):
    items: list[AdminAIResponseFeedbackAnalysisResult]
    total: int


class AdminAIResponseFeedbackConfirmationResponse(BaseModel):
    feedback_id: str
    revision: int
    status: AIResponseFeedbackStatus
    analysis_status: AIResponseFeedbackStatus
    content_hash: str
    confirmed_at: datetime
