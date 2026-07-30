"""HTTP and domain schemas for product-knowledge import V1."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ProductKnowledgeImportStatus(StrEnum):
    PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
    IDENTIFIED_PENDING_REVIEW = "IDENTIFIED_PENDING_REVIEW"
    NO_CHANGE = "NO_CHANGE"
    PARTIALLY_REVIEWED = "PARTIALLY_REVIEWED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProductMatchType(StrEnum):
    NEW = "NEW"
    EXISTING = "EXISTING"
    CONFLICT = "CONFLICT"


class ChangeType(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    KEEP = "KEEP"
    NO_CHANGE = "NO_CHANGE"


class ChangeSetOperation(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    NO_CHANGE = "NO_CHANGE"
    CONFLICT = "CONFLICT"


class ChangeSetStatus(StrEnum):
    IDENTIFIED_PENDING_REVIEW = "IDENTIFIED_PENDING_REVIEW"
    NO_CHANGE = "NO_CHANGE"
    CONFLICT = "CONFLICT"
    APPROVED_APPLIED = "APPROVED_APPLIED"
    REJECTED = "REJECTED"
    STALE_REVIEW_REQUIRED = "STALE_REVIEW_REQUIRED"
    APPLY_FAILED = "APPLY_FAILED"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ReviewOutcome(StrEnum):
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    STALE_REVIEW_REQUIRED = "STALE_REVIEW_REQUIRED"
    APPLY_FAILED = "APPLY_FAILED"


class ParsedProductKnowledgeRow(BaseModel):
    source_row_number: int
    store_name: str
    product_name: str
    fields: dict[str, Any]
    source_name: str
    source_date: str
    human_confirmation: str
    remark: str | None = None


class ProductKnowledgeParseResult(BaseModel):
    template_type: str
    template_version: str
    parser_version: str
    template_metadata: dict[str, Any]
    sheet_results: list[dict[str, Any]]
    field_validation_result: dict[str, Any]
    products: list[ParsedProductKnowledgeRow]


class ImportAcceptedResponse(BaseModel):
    batch_id: str
    status: str


class ProductKnowledgePreflightResponse(BaseModel):
    batch_id: str
    status: str
    can_review: bool
    file_result: dict[str, Any]
    sheet_results: list[dict[str, Any]]
    field_validation_result: dict[str, Any]
    product_identification_result: dict[str, Any]


class MergeFieldPreview(BaseModel):
    field_key: str
    field_label: str
    old_value: Any = None
    incoming_value: Any = None
    merged_value: Any = None
    change_type: ChangeType


class MergeProductPreview(BaseModel):
    change_set_id: str
    product_name: str
    target_product_id: str | None
    operation: ChangeSetOperation
    status: ChangeSetStatus
    base_snapshot_hash: str
    version: int


class MergePreviewItem(BaseModel):
    product: MergeProductPreview
    fields: list[MergeFieldPreview]


class MergePreviewResponse(BaseModel):
    batch_id: str
    status: str
    items: list[MergePreviewItem]
    page: int
    page_size: int
    total: int


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    operator: str = Field(min_length=1, max_length=128)
    review_note: str | None = Field(default=None, max_length=4000)
    expected_base_snapshot_hash: str = Field(min_length=64, max_length=64)
    expected_change_set_version: int = Field(ge=1)

    @model_validator(mode="after")
    def reject_requires_note(self) -> "ReviewRequest":
        self.operator = self.operator.strip()
        if self.review_note is not None:
            self.review_note = self.review_note.strip() or None
        if self.decision == ReviewDecision.REJECT and not self.review_note:
            raise ValueError("review_note is required when decision is REJECT")
        return self


class ReviewReceipt(BaseModel):
    receipt_id: str
    batch_id: str
    change_set_id: str
    decision: ReviewDecision
    outcome: ReviewOutcome
    reviewed_by: str
    reviewed_at: str
    applied_product_id: str | None
    applied_field_count: int
    before_snapshot_hash: str | None
    after_snapshot_hash: str | None


class ReviewResponse(BaseModel):
    review_receipt: ReviewReceipt
