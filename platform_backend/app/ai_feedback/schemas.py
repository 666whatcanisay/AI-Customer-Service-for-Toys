"""Versioned C-to-A feedback-case interface schemas.

The C service owns the lifecycle.  This module intentionally contains no B
submission endpoint or A-side execution logic.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class AIResponseFeedbackConfirmation(BaseModel):
    """C-owned internal control for making a de-identified record exportable."""

    model_config = ConfigDict(extra="forbid")

    confirmed_by: str = Field(min_length=1, max_length=128)
    confirmation_reason: str = Field(min_length=1, max_length=4000)


class AIResponseFeedbackExportItem(BaseModel):
    feedback_id: str
    revision: int
    question: str
    ai_answer: str
    final_answer: str | None
    feedback_type: AIResponseFeedbackType
    content_hash: str
    created_at: datetime


class AIResponseFeedbackExportResponse(BaseModel):
    items: list[AIResponseFeedbackExportItem]
    next_cursor: str | None


class AIResponseFeedbackAnalysisCreate(BaseModel):
    """A-to-C evidence only; it cannot carry an instruction to take action."""

    model_config = ConfigDict(extra="forbid")

    feedback_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
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


class AdminAIResponseFeedbackConfirmationResponse(BaseModel):
    feedback_id: str
    revision: int
    status: AIResponseFeedbackStatus
    analysis_status: AIResponseFeedbackStatus
    content_hash: str
    confirmed_at: datetime
