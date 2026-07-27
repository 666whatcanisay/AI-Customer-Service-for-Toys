"""Public, read-only schema for the AI control-center snapshot.

The schema deliberately contains operational metadata and aggregate counters
only. It must never grow fields for prompts, source excerpts, questions,
answers, customer identifiers, environment values, or platform URLs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ControlCenterStatus = Literal[
    "RUNNING",
    "PAUSED",
    "ERROR",
    "PLANNED",
    "CONFIGURED",
    "NOT_CONFIGURED",
    "AVAILABLE",
    "NOT_AVAILABLE",
    "MANUAL_ONLY",
]


class AiCustomerServiceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: Literal["ai_customer_service"]
    name: str = Field(..., max_length=120)
    description: str = Field(..., max_length=500)
    status: Literal["RUNNING", "PAUSED", "ERROR"]
    ready: bool
    model_provider: str | None = Field(default=None, max_length=80)
    model_name: str | None = Field(default=None, max_length=160)
    model_configured: bool | None = None
    knowledge_count: int | None = Field(default=None, ge=0)
    metrics_scope: str | None = Field(default=None, max_length=80)
    call_count: int | None = Field(default=None, ge=0)
    success_count: int | None = Field(default=None, ge=0)
    error_count: int | None = Field(default=None, ge=0)
    average_latency_ms: float | None = Field(default=None, ge=0)
    last_called_at: str | None = Field(default=None, max_length=80)
    last_error_summary: str | None = Field(default=None, max_length=100)
    supported_actions: list[str] = Field(default_factory=list)


class PromptReadOnlyState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: Literal["ai_customer_service"]
    prompt_version: str = Field(..., max_length=160)
    prompt_hash: str = Field(..., max_length=128)
    updated_at: str = Field(..., max_length=80)
    source_type: str = Field(..., max_length=80)
    safe_preview: str = Field(..., max_length=1000)
    answer_style_rules: list[str] = Field(default_factory=list)


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(..., max_length=160)
    executed_at: str = Field(..., max_length=80)
    dataset_version: str = Field(..., max_length=160)
    total_cases: int | None = Field(default=None, ge=0)
    passed_cases: int | None = Field(default=None, ge=0)
    pass_rate: float | None = Field(default=None, ge=0, le=100)
    checks: dict[str, int | None] = Field(default_factory=dict)
    failed_case_ids: list[str] = Field(default_factory=list)
    report_available: bool


class EvaluationReadOnlyState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: Literal["ai_customer_service"]
    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    evaluation: EvaluationSummary | None = None
    execution_mode: Literal["EXPLICIT_MANUAL"] = "EXPLICIT_MANUAL"
    platform_integration_status: Literal["CONFIGURED", "NOT_CONFIGURED"]
    current_model_version: str | None = Field(default=None, max_length=160)
    current_prompt_version: str = Field(..., max_length=160)
    version_note: str = Field(..., max_length=500)


class BadcaseCategoryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["FACT_ERROR", "MISSING_INFO", "STYLE_ISSUE", "RISK_ISSUE"]
    count: None = None


class BadcaseReadOnlyState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"
    reason: str = Field(..., max_length=500)
    categories: list[BadcaseCategoryState]
    raw_content_exposed: Literal[False] = False


class FeedbackAnalysisRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed_at: str = Field(..., max_length=80)
    input_feedback_count: int = Field(..., ge=0)
    completed_analysis_count: int = Field(..., ge=0)
    analyzed_writeback_count: int = Field(..., ge=0)
    idempotency_verified_count: int = Field(..., ge=0)
    model_version: str | None = Field(default=None, max_length=160)
    prompt_version: str | None = Field(default=None, max_length=160)


class FeedbackAnalysisReadOnlyState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["MANUAL_ONLY", "NOT_CONFIGURED"]
    execution_mode: Literal["EXPLICIT_LOOPBACK"] = "EXPLICIT_LOOPBACK"
    platform_integration_status: Literal["CONFIGURED", "NOT_CONFIGURED"]
    configured_model_version: str | None = Field(default=None, max_length=160)
    prompt_version: str = Field(..., max_length=160)
    latest_run: FeedbackAnalysisRunSummary | None = None
    result_retention: Literal["PROCESS_MEMORY_ONLY"] = "PROCESS_MEMORY_ONLY"
    raw_content_exposed: Literal[False] = False


class AiOperationalCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: Literal[
        "rag",
        "qwen_local_model",
        "experience_evaluation",
        "badcase_analysis",
        "feedback_analysis",
    ]
    name: str = Field(..., max_length=120)
    status: ControlCenterStatus
    data_status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    operator_mode: Literal["READ_ONLY", "EXPLICIT_MANUAL"]
    summary: str = Field(..., max_length=500)


class ControlCenterDataSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., max_length=80)
    read_path: str = Field(..., max_length=200)
    purpose: str = Field(..., max_length=500)
    contains_raw_customer_content: Literal[False] = False


class AiControlCenterSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-control-center.v1.1"] = "ai-control-center.v1.1"
    generated_at: str = Field(..., max_length=80)
    customer_service: AiCustomerServiceState
    prompt: PromptReadOnlyState
    evaluation: EvaluationReadOnlyState
    badcase: BadcaseReadOnlyState
    feedback_analysis: FeedbackAnalysisReadOnlyState
    capabilities: list[AiOperationalCapability]
    data_sources: list[ControlCenterDataSource]


class AiControlCenterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    data: AiControlCenterSnapshot
