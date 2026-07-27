"""Safe, read-only schema for AI operations metrics.

The operational overview intentionally exposes only process aggregates and
saved evaluation summaries. It never returns customer content, prompt text,
identifiers, platform URLs, or individual feedback/evaluation records.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MetricStatus = Literal[
    "AVAILABLE",
    "NOT_AVAILABLE",
    "NOT_CONFIGURED",
    "NOT_REGISTERED",
]


class AnswerVolumeMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    metrics_scope: str = Field(..., max_length=80)
    processed_request_count: int | None = Field(default=None, ge=0)
    direct_answer_count: int | None = Field(default=None, ge=0)
    controlled_answer_count: int | None = Field(default=None, ge=0)
    transfer_human_count: int | None = Field(default=None, ge=0)
    other_outcome_count: int | None = Field(default=None, ge=0)
    durable: Literal[False] = False
    explanation: str = Field(..., max_length=500)


class AnswerQualityMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    evaluation_id: str | None = Field(default=None, max_length=160)
    evaluated_case_count: int | None = Field(default=None, ge=0)
    passed_case_count: int | None = Field(default=None, ge=0)
    pass_rate_percent: float | None = Field(default=None, ge=0, le=100)
    measured_at: str | None = Field(default=None, max_length=80)
    explanation: str = Field(..., max_length=500)


class KnowledgeCoverageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    indexed_chunk_count: int | None = Field(default=None, ge=0)
    source_attribution_checked_case_count: int | None = Field(default=None, ge=0)
    source_attribution_pass_rate_percent: float | None = Field(
        default=None, ge=0, le=100
    )
    explanation: str = Field(..., max_length=500)


class BadcaseCategoryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["FACT_ERROR", "MISSING_INFO", "STYLE_ISSUE", "RISK_ISSUE"]
    count: None = None


class BadcaseMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"
    categories: list[BadcaseCategoryMetric]
    explanation: str = Field(..., max_length=500)
    raw_content_exposed: Literal[False] = False


class ModelStatusMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["CONFIGURED", "NOT_CONFIGURED"]
    provider: str | None = Field(default=None, max_length=80)
    model_version: str | None = Field(default=None, max_length=160)
    service_ready: bool
    availability_probed: Literal[False] = False
    average_latency_ms: float | None = Field(default=None, ge=0)
    error_count: int | None = Field(default=None, ge=0)
    last_error_category: str | None = Field(default=None, max_length=100)
    explanation: str = Field(..., max_length=500)


class ExternalDataIntegrationMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: Literal["feedback", "efficiency"]
    status: MetricStatus
    read_attempted: Literal[False] = False
    explanation: str = Field(..., max_length=500)
    operator_action: str = Field(..., max_length=500)


class OperationsNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., max_length=100)
    severity: Literal["INFO", "WARNING", "ERROR"]
    message: str = Field(..., max_length=500)
    operator_action: str = Field(..., max_length=500)
    automatic_action_taken: Literal[False] = False


class AiOperationsOverviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-operations.v1"] = "ai-operations.v1"
    generated_at: str = Field(..., max_length=80)
    answer_volume: AnswerVolumeMetric
    answer_quality: AnswerQualityMetric
    knowledge_coverage: KnowledgeCoverageMetric
    badcase: BadcaseMetric
    model_status: ModelStatusMetric
    external_data: list[ExternalDataIntegrationMetric]
    notices: list[OperationsNotice]
    raw_content_exposed: Literal[False] = False


class AiOperationsOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    data: AiOperationsOverviewSnapshot
