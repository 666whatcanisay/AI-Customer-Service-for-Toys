"""Versioned request and response schemas for Customer Feedback Loop V1."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InteractionActionType(StrEnum):
    DIRECT_ACCEPT = "DIRECT_ACCEPT"
    EDITED_ACCEPT = "EDITED_ACCEPT"
    REJECTED = "REJECTED"


class InteractionEventStatus(StrEnum):
    RECORDED = "RECORDED"


class AIProblemType(StrEnum):
    UNCLASSIFIED = "UNCLASSIFIED"
    KNOWLEDGE_MISSING = "KNOWLEDGE_MISSING"
    PRODUCT_INFO_ERROR = "PRODUCT_INFO_ERROR"
    SKU_ERROR = "SKU_ERROR"
    INCOMPLETE_ANSWER = "INCOMPLETE_ANSWER"
    RISK_ISSUE = "RISK_ISSUE"
    EXPRESSION_ISSUE = "EXPRESSION_ISSUE"


class AIProblemStatus(StrEnum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    SOLVED = "SOLVED"
    VERIFIED = "VERIFIED"


class KnowledgeTaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"


class VerificationResult(StrEnum):
    IMPROVED = "IMPROVED"
    NOT_IMPROVED = "NOT_IMPROVED"


class InteractionEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(min_length=1, max_length=160)
    store_code: str = Field(min_length=1, max_length=96)
    store_name: str = Field(min_length=1, max_length=256)
    product_id: str = Field(min_length=1, max_length=128)
    product_name: str = Field(min_length=1, max_length=256)
    sku_id: str | None = Field(default=None, max_length=128)
    sku_name: str | None = Field(default=None, max_length=256)
    action_type: InteractionActionType
    question_summary: str = Field(min_length=1, max_length=1200)
    ai_answer_summary: str = Field(min_length=1, max_length=1200)
    final_answer_summary: str | None = Field(default=None, max_length=1200)
    created_by: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_action_content(self) -> "InteractionEventCreate":
        if self.action_type is InteractionActionType.EDITED_ACCEPT:
            if not self.final_answer_summary or not self.final_answer_summary.strip():
                raise ValueError("final_answer_summary is required for EDITED_ACCEPT")
        return self


class InteractionEventReceipt(BaseModel):
    event_id: str
    interaction_id: str
    status: InteractionEventStatus
    occurred_at: datetime


class AdminInteractionEvent(BaseModel):
    event_id: str
    interaction_id: str
    store_code: str
    store_name: str
    product_id: str
    product_name: str
    sku_id: str | None
    sku_name: str | None
    action_type: InteractionActionType
    occurred_at: datetime
    created_by: str


class AdminInteractionEventList(BaseModel):
    items: list[AdminInteractionEvent]
    total: int


class KnowledgeTaskProjection(BaseModel):
    task_id: str
    source_problem_id: str
    store_code: str
    product_id: str
    sku_id: str | None
    missing_topic: str
    status: KnowledgeTaskStatus
    status_note: str | None
    verification_result: VerificationResult | None
    verification_note: str | None
    verified_by: str | None
    verified_at: datetime | None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class AIProblemProjection(BaseModel):
    problem_id: str
    store_code: str
    store_name: str
    product_id: str
    product_name: str
    sku_id: str | None
    sku_name: str | None
    question_summary: str
    ai_answer_summary: str
    issue_type: AIProblemType
    occurrence_count: int
    status: AIProblemStatus
    first_seen_at: datetime
    last_seen_at: datetime
    knowledge_task: KnowledgeTaskProjection | None


class AIProblemList(BaseModel):
    items: list[AIProblemProjection]
    total: int


class AIProblemStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AIProblemStatus
    operator: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=1000)
    issue_type: AIProblemType | None = None


class KnowledgeTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_topic: str = Field(min_length=1, max_length=256)
    operator: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=1000)


class KnowledgeTaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: KnowledgeTaskStatus
    operator: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=1000)


class KnowledgeTaskVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: VerificationResult
    operator: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=1, max_length=1000)
