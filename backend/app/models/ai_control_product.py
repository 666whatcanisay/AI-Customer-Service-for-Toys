"""Stable, product-facing read-only projection for the AI control center.

This schema is intentionally a presentation projection over existing safe A
snapshots. It contains no customer content, prompt text, platform endpoint,
secret, raw exception, or write operation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductServiceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["RUNNING", "INITIALIZING", "ERROR"]
    display_status: str = Field(..., max_length=80)
    summary: str = Field(..., max_length=300)
    last_initialization_status: Literal["READY", "INITIALIZING", "FAILED"]
    last_initialized_at: None = None
    initialization_error_exposed: Literal[False] = False


class ProductModelState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY", "INITIALIZING", "ERROR", "NOT_CONFIGURED"]
    display_status: str = Field(..., max_length=80)
    provider: str | None = Field(default=None, max_length=80)
    model_name: str | None = Field(default=None, max_length=160)
    availability_probed: Literal[False] = False
    last_initialization_status: Literal[
        "READY", "INITIALIZING", "FAILED", "NOT_CONFIGURED"
    ]
    last_initialized_at: None = None
    summary: str = Field(..., max_length=300)


class ProductKnowledgeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    indexed_chunk_count: int | None = Field(default=None, ge=0)
    last_sync_at: None = None
    last_sync_status: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"
    display_status: str = Field(..., max_length=80)
    summary: str = Field(..., max_length=300)


class ProductAnswerUsageState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    metrics_scope: Literal["A_PROCESS_SINCE_START", "NOT_AVAILABLE"]
    processed_request_count: int | None = Field(default=None, ge=0)
    direct_answer_count: int | None = Field(default=None, ge=0)
    controlled_answer_count: int | None = Field(default=None, ge=0)
    transfer_human_count: int | None = Field(default=None, ge=0)
    other_outcome_count: int | None = Field(default=None, ge=0)
    reset_on_restart: Literal[True] = True
    summary: str = Field(..., max_length=300)


class ProductEvaluationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    source: Literal["SAVED_LIVE_C_API", "NOT_AVAILABLE"]
    evaluation_id: str | None = Field(default=None, max_length=160)
    recorded_at: str | None = Field(default=None, max_length=80)
    recorded_at_status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    dataset_version: str | None = Field(default=None, max_length=160)
    dataset_version_status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    total_case_count: int | None = Field(default=None, ge=0)
    passed_case_count: int | None = Field(default=None, ge=0)
    failed_case_count: int | None = Field(default=None, ge=0)
    pass_rate_percent: float | None = Field(default=None, ge=0, le=100)
    summary: str = Field(..., max_length=300)


ProductIssueCategory = Literal[
    "KNOWLEDGE_PROBLEM",
    "RETRIEVAL_PROBLEM",
    "PROMPT_OR_MODEL_PROBLEM",
    "DATA_PROBLEM",
    "RULE_DECISION_PROBLEM",
]


class ProductIssueFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ProductIssueCategory
    display_name: str = Field(..., max_length=80)
    evidence: Literal["DIRECT_EVALUATOR_SIGNAL", "NO_SIGNAL_IN_CURRENT_REPORT"]
    affected_case_count: int = Field(..., ge=0)
    summary: str = Field(..., max_length=300)
    manual_next_step: str = Field(..., max_length=300)
    automatic_change_allowed: Literal[False] = False


class ProductQualityAnalysisState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    source_evaluation_id: str | None = Field(default=None, max_length=160)
    source_recorded_at: str | None = Field(default=None, max_length=80)
    source_recorded_at_status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    failed_case_count: int | None = Field(default=None, ge=0)
    summary: str = Field(..., max_length=300)
    findings: list[ProductIssueFinding]
    automatic_change_allowed: Literal[False] = False


class ProductModuleCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(..., max_length=80)
    name: str = Field(..., max_length=120)
    status: Literal[
        "RUNNING", "PAUSED", "ERROR", "PLANNED", "CONFIGURED",
        "NOT_CONFIGURED", "AVAILABLE", "NOT_AVAILABLE", "MANUAL_ONLY",
    ]
    data_status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    operator_mode: Literal["READ_ONLY", "EXPLICIT_MANUAL"]
    display_status: str = Field(..., max_length=80)
    summary: str = Field(..., max_length=500)


class ProductFeedbackAnalysisState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["MANUAL_ONLY", "NOT_CONFIGURED"]
    latest_completed_at: str | None = Field(default=None, max_length=80)
    completed_analysis_count: int | None = Field(default=None, ge=0)
    summary: str = Field(..., max_length=300)
    raw_content_exposed: Literal[False] = False


class ProductNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., max_length=100)
    severity: Literal["INFO", "WARNING", "ERROR"]
    title: str = Field(..., max_length=80)
    summary: str = Field(..., max_length=300)
    manual_next_step: str = Field(..., max_length=300)
    automatic_action_taken: Literal[False] = False


class ProductRuntimeIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_version: str = Field(..., max_length=80)
    runtime_commit_sha: None = None
    runtime_commit_sha_status: Literal["NOT_AVAILABLE"] = "NOT_AVAILABLE"
    metrics_scope: Literal["A_PROCESS_SINCE_START"] = "A_PROCESS_SINCE_START"
    metrics_reset_on_restart: Literal[True] = True


class AiControlCenterProductSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-control-center.product.v1"] = "ai-control-center.product.v1"
    generated_at: str = Field(..., max_length=80)
    service: ProductServiceState
    model: ProductModelState
    knowledge: ProductKnowledgeState
    answer_usage: ProductAnswerUsageState
    latest_evaluation: ProductEvaluationState
    latest_quality_analysis: ProductQualityAnalysisState
    modules: list[ProductModuleCapability]
    feedback_analysis: ProductFeedbackAnalysisState
    notices: list[ProductNotice]
    runtime: ProductRuntimeIdentity
    raw_content_exposed: Literal[False] = False
    model_call_performed: Literal[False] = False
    business_write_performed: Literal[False] = False


class AiControlCenterProductResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    data: AiControlCenterProductSnapshot
