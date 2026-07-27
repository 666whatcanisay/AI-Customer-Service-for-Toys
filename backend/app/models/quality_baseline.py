"""Read-only schema for saved RAG quality-baseline diagnosis.

The endpoint exposes only aggregate evaluator signals and internal case IDs.
It must never return the original question, answer, source excerpts, expected
facts, source IDs, prompt text, platform URLs, or secrets from a report.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DiagnosisCategory = Literal[
    "KNOWLEDGE_PROBLEM",
    "RETRIEVAL_PROBLEM",
    "PROMPT_OR_MODEL_PROBLEM",
    "DATA_PROBLEM",
    "RULE_DECISION_PROBLEM",
]

DiagnosisEvidence = Literal[
    "DIRECT_EVALUATOR_SIGNAL",
    "NO_SIGNAL_IN_CURRENT_REPORT",
]


class QualityCheckSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check: Literal[
        "action",
        "source_ids",
        "key_facts",
        "forbidden_claims",
        "required_fields",
        "risk_level",
        "scope",
    ]
    passed_case_count: int | None = Field(default=None, ge=0)


class QualityBaselineSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(..., max_length=160)
    executed_at: str = Field(..., max_length=80)
    dataset_version: str = Field(..., max_length=160)
    total_case_count: int = Field(..., ge=0)
    passed_case_count: int = Field(..., ge=0)
    failed_case_count: int = Field(..., ge=0)
    pass_rate_percent: float = Field(..., ge=0, le=100)
    checks: list[QualityCheckSummary]


class FailedCaseDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., max_length=160)
    categories: list[DiagnosisCategory]
    evaluator_failure_classes: list[
        Literal[
            "metadata_loss",
            "retrieval_miss",
            "model_expression_error",
            "structured_decision_error",
        ]
    ]
    failed_checks: list[
        Literal[
            "action",
            "source_ids",
            "key_facts",
            "forbidden_claims",
            "required_fields",
            "risk_level",
            "scope",
        ]
    ]
    expected_source_count: int = Field(..., ge=0)
    missing_expected_source_count: int = Field(..., ge=0)
    expected_fact_count: int = Field(..., ge=0)
    suggested_verifications: list[str] = Field(default_factory=list, max_length=5)


class CauseFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: DiagnosisCategory
    affected_case_count: int = Field(..., ge=0)
    evidence: DiagnosisEvidence
    conclusion: str = Field(..., max_length=500)
    recommended_verification: str = Field(..., max_length=500)
    automatic_change_allowed: Literal[False] = False


class QualityRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: Literal["P0", "P1", "P2"]
    category: DiagnosisCategory
    recommendation: str = Field(..., max_length=500)
    rationale: str = Field(..., max_length=500)
    automatic_change_allowed: Literal[False] = False


class QualityBaselineSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ai-quality-baseline.v1"] = "ai-quality-baseline.v1"
    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    summary: QualityBaselineSummary | None = None
    failed_cases: list[FailedCaseDiagnosis] = Field(default_factory=list)
    cause_findings: list[CauseFinding]
    recommendations: list[QualityRecommendation]
    raw_content_exposed: Literal[False] = False
    model_or_prompt_changed: Literal[False] = False


class QualityBaselineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str
    data: QualityBaselineSnapshot
