from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from string import Formatter
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ReplyRuleScopeKind(StrEnum):
    TENANT = "TENANT"
    STORE = "STORE"
    PRODUCT = "PRODUCT"
    SKU = "SKU"


class ReplyRuleAction(StrEnum):
    DIRECT_ANSWER = "DIRECT_ANSWER"
    CONTROLLED_ANSWER = "CONTROLLED_ANSWER"
    ASK_CLARIFY = "ASK_CLARIFY"
    REQUIRE_LOOKUP = "REQUIRE_LOOKUP"
    TRANSFER_HUMAN = "TRANSFER_HUMAN"
    REFUSE = "REFUSE"


class ReplyRuleRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReplyRuleStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class ReplyRuleReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ReplyRuleEventType(StrEnum):
    CREATED = "CREATED"
    DRAFT_UPDATED = "DRAFT_UPDATED"
    REVIEW_SUBMITTED = "REVIEW_SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_CREATED = "REVISION_CREATED"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


ALLOWED_FIXED_VARIABLES = frozenset(
    {"product_name", "particle_count", "finished_size", "material", "ship_origin"}
)
ALLOWED_CONTEXT_FIELDS = frozenset(
    {"tenant_id", "platform", "store_code", "product_id", "sku_id"}
)


class ReplyRuleSourceScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_kind: ReplyRuleScopeKind
    tenant_id: str = Field(min_length=1, max_length=96, pattern=r"^[^\r\n]+$")
    platform: str = Field(min_length=1, max_length=32, pattern=r"^[^\r\n]+$")
    store_code: str | None = Field(default=None, min_length=1, max_length=96)
    product_id: str | None = Field(default=None, min_length=1, max_length=96)
    sku_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def identifiers_match_kind(self) -> "ReplyRuleSourceScope":
        expected = {
            ReplyRuleScopeKind.TENANT: (False, False, False),
            ReplyRuleScopeKind.STORE: (True, False, False),
            ReplyRuleScopeKind.PRODUCT: (True, True, False),
            ReplyRuleScopeKind.SKU: (True, True, True),
        }[self.scope_kind]
        actual = (
            self.store_code is not None,
            self.product_id is not None,
            self.sku_id is not None,
        )
        if actual != expected:
            raise ValueError("source scope identifiers do not match scope_kind")
        return self


class ReplyRuleSourceMaterialEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(min_length=1, max_length=255, pattern=r"^[^\r\n]+$")
    revision: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    governance_status: Literal["REVIEWED_VALID"]
    scope: ReplyRuleSourceScope
    reviewed_by: str = Field(min_length=1, max_length=255, pattern=r"^[^\r\n]+$")
    reviewed_at: AwareDatetime


class ReplyRuleContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=96, pattern=r"^[^\r\n]+$")
    platform: str = Field(min_length=1, max_length=32, pattern=r"^[^\r\n]+$")
    scope_kind: ReplyRuleScopeKind
    store_code: str | None = Field(default=None, min_length=1, max_length=96)
    product_id: str | None = Field(default=None, min_length=1, max_length=96)
    sku_id: str | None = Field(default=None, min_length=1, max_length=128)
    canonical_question: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(min_length=1, max_length=64)
    fixed_reply: str = Field(min_length=1, max_length=8000)
    variable_names: list[str] = Field(default_factory=list, max_length=5)
    action: ReplyRuleAction
    risk_level: ReplyRuleRiskLevel
    required_context_fields: list[str] = Field(default_factory=list, max_length=5)
    prohibited_claims: list[str] = Field(default_factory=list, max_length=32)
    allow_auto_candidate: bool = False
    source_material_ids: list[str] = Field(min_length=1, max_length=32)
    source_confirmed: bool = False
    high_risk_source_confirmed: bool = False
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None

    @field_validator(
        "tenant_id",
        "platform",
        "store_code",
        "product_id",
        "sku_id",
        "canonical_question",
        "fixed_reply",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator(
        "aliases",
        "variable_names",
        "required_context_fields",
        "prohibited_claims",
        "source_material_ids",
    )
    @classmethod
    def strip_string_lists(cls, values: list[str]) -> list[str]:
        stripped = [value.strip() for value in values]
        if any(not value for value in stripped):
            raise ValueError("list items cannot be blank")
        if len(stripped) != len(set(stripped)):
            raise ValueError("list items must be unique")
        return stripped

    @model_validator(mode="after")
    def validate_business_rules(self) -> "ReplyRuleContent":
        expected_scope = {
            ReplyRuleScopeKind.TENANT: (False, False, False),
            ReplyRuleScopeKind.STORE: (True, False, False),
            ReplyRuleScopeKind.PRODUCT: (True, True, False),
            ReplyRuleScopeKind.SKU: (True, True, True),
        }[self.scope_kind]
        actual_scope = (
            self.store_code is not None,
            self.product_id is not None,
            self.sku_id is not None,
        )
        if actual_scope != expected_scope:
            raise ValueError("scope identifiers do not match scope_kind")
        if not set(self.variable_names).issubset(ALLOWED_FIXED_VARIABLES):
            raise ValueError("unsupported fixed reply variable")
        if not set(self.required_context_fields).issubset(ALLOWED_CONTEXT_FIELDS):
            raise ValueError("unsupported required context field")
        required_for_scope = {
            ReplyRuleScopeKind.TENANT: {"tenant_id", "platform"},
            ReplyRuleScopeKind.STORE: {"tenant_id", "platform", "store_code"},
            ReplyRuleScopeKind.PRODUCT: {
                "tenant_id",
                "platform",
                "store_code",
                "product_id",
            },
            ReplyRuleScopeKind.SKU: set(ALLOWED_CONTEXT_FIELDS),
        }[self.scope_kind]
        if not required_for_scope.issubset(self.required_context_fields):
            raise ValueError("required context fields do not cover the rule scope")
        try:
            parsed = list(Formatter().parse(self.fixed_reply))
        except ValueError as exc:
            raise ValueError("fixed reply template is malformed") from exc
        placeholders: list[str] = []
        for _, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            if not field_name or format_spec or conversion:
                raise ValueError("fixed reply variables cannot use formatting syntax")
            placeholders.append(field_name)
        if set(placeholders) != set(self.variable_names):
            raise ValueError("fixed reply placeholders must match variable_names")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must follow effective_from")
        allowed_auto = (
            self.risk_level is ReplyRuleRiskLevel.LOW
            and self.action is ReplyRuleAction.DIRECT_ANSWER
        ) or (
            self.risk_level is ReplyRuleRiskLevel.MEDIUM
            and self.action
            in {ReplyRuleAction.CONTROLLED_ANSWER, ReplyRuleAction.ASK_CLARIFY}
        )
        if self.allow_auto_candidate and not allowed_auto:
            raise ValueError("risk/action combination cannot become an auto candidate")
        return self


class ReplyRuleCreate(ReplyRuleContent):
    rule_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )
    change_reason: str = Field(min_length=1, max_length=1000)


class ReplyRuleDraftUpdate(ReplyRuleContent):
    change_reason: str = Field(min_length=1, max_length=1000)


class ReplyRuleTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class ReplyRuleReview(ReplyRuleTransition):
    decision: ReplyRuleReviewDecision


class ReplyRuleRevisionCreate(ReplyRuleTransition):
    pass


class ReplyRuleSnapshotPublishCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=96, pattern=r"^[^\r\n]+$")
    platform: str = Field(min_length=1, max_length=32, pattern=r"^[^\r\n]+$")
    confirmation_note: str = Field(min_length=1, max_length=1000)

    @field_validator("tenant_id", "platform", "confirmation_note")
    @classmethod
    def strip_publish_text(cls, value: str) -> str:
        return value.strip()


class ReplyRuleWithdrawalCommand(ReplyRuleTransition):
    pass


class ReplyRuleSnapshotReceiptProjection(BaseModel):
    schema_version: str = "reply-rule-publication-receipt.v1"
    publication_id: str
    tenant_id: str
    platform: str
    snapshot_revision: int = Field(ge=1)
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: str = "PUBLISHED"
    changed: bool
    accepted_rule_count: int = Field(ge=0)
    published_at: datetime
    operator: str


class ReplyRulePublicationReceiptWire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["reply-rule-publication-receipt.v1"]
    publication_id: str = Field(min_length=1, max_length=255, pattern=r"^[^\r\n]+$")
    tenant_id: str = Field(min_length=1, max_length=96, pattern=r"^[^\r\n]+$")
    platform: str = Field(min_length=1, max_length=32, pattern=r"^[^\r\n]+$")
    snapshot_revision: int = Field(ge=1)
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["PUBLISHED"]
    changed: bool
    accepted_rule_count: int = Field(ge=0, le=10_000)
    published_at: AwareDatetime


class ReplyRuleSnapshotPublicationResponse(BaseModel):
    schema_version: str = "reply-rule-snapshot-publication.v1"
    changed: bool
    tenant_id: str
    platform: str
    snapshot_revision: int = Field(ge=1)
    snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    rules_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    accepted_rule_count: int = Field(ge=0)
    publication_receipt: ReplyRuleSnapshotReceiptProjection


class ReplyRuleSnapshotReceiptListResponse(BaseModel):
    items: list[ReplyRuleSnapshotReceiptProjection]
    total: int = Field(ge=0)


class ReplyRuleProjection(ReplyRuleContent):
    schema_version: str = "reply-rule-governance.v1"
    rule_id: str
    rule_version: int = Field(ge=1)
    status: ReplyRuleStatus
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    source_material_evidence: list[ReplyRuleSourceMaterialEvidence]
    created_at: datetime
    updated_at: datetime


class ReplyRuleListResponse(BaseModel):
    items: list[ReplyRuleProjection]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    size: int = Field(ge=1)


class ReplyRuleEventProjection(BaseModel):
    event_id: str
    rule_id: str
    rule_version: int
    event_type: ReplyRuleEventType
    previous_status: ReplyRuleStatus | None
    next_status: ReplyRuleStatus
    actor_user_id: str
    reason: str
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    occurred_at: datetime


class ReplyRuleEventListResponse(BaseModel):
    items: list[ReplyRuleEventProjection]
    total: int = Field(ge=0)
