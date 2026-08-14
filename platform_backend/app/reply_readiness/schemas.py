from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def canonical_sha256(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExpectedAction(StrEnum):
    DIRECT_ANSWER = "DIRECT_ANSWER"
    CONTROLLED_ANSWER = "CONTROLLED_ANSWER"
    ASK_CLARIFY = "ASK_CLARIFY"
    REQUIRE_LOOKUP = "REQUIRE_LOOKUP"
    TRANSFER_HUMAN = "TRANSFER_HUMAN"
    REFUSE = "REFUSE"


class ReplyReadinessExecutionMode(StrEnum):
    READINESS_SANDBOX = "READINESS_SANDBOX"
    PUBLISHED_ROUTER_DEBUG = "PUBLISHED_ROUTER_DEBUG"


class ExtensionScopeKind(StrEnum):
    STORE = "STORE"
    PRODUCT = "PRODUCT"


class PddReplyReadinessQuestionV1(StrictModel):
    schema_version: Literal["pdd-reply-readiness-question.v1"] = "pdd-reply-readiness-question.v1"
    question_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Z0-9][A-Z0-9-]+$")
    category: str = Field(min_length=1, max_length=64)
    canonical_question: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=64)
    policy_risk_floor: RiskLevel
    expected_action: ExpectedAction
    required_fact_keys: list[str] = Field(default_factory=list, max_length=32)
    requires_realtime_lookup: bool = False
    prohibited_claims: list[str] = Field(default_factory=list, max_length=32)
    mandatory: bool = True


class PddQuestionSetProjection(StrictModel):
    schema_version: Literal["pdd-reply-readiness-question-set.v1"] = "pdd-reply-readiness-question-set.v1"
    baseline_version: str
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    questions: list[PddReplyReadinessQuestionV1] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def fingerprint_matches(self) -> "PddQuestionSetProjection":
        expected = canonical_sha256({
            "baseline_version": self.baseline_version,
            "questions": [item.model_dump(mode="json") for item in self.questions],
        })
        if self.fingerprint != expected:
            raise ValueError("question set fingerprint mismatch")
        return self


class QuestionSetExtensionCreate(StrictModel):
    extension_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$")
    scope_kind: ExtensionScopeKind
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str | None = Field(default=None, max_length=96)
    questions: list[PddReplyReadinessQuestionV1] = Field(min_length=1, max_length=100)
    change_reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def scope_matches(self) -> "QuestionSetExtensionCreate":
        if (self.scope_kind is ExtensionScopeKind.PRODUCT) != (self.product_id is not None):
            raise ValueError("product_id must match PRODUCT scope")
        return self


class QuestionSetExtensionProjection(QuestionSetExtensionCreate):
    extension_id: str
    version: int = Field(ge=1)
    status: Literal["ACTIVE", "RETIRED"]
    content_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_by: str
    created_at: datetime


class QuestionSetExtensionList(StrictModel):
    items: list[QuestionSetExtensionProjection]
    total: int = Field(ge=0)


class ReplyReadinessScopeV1(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=96)
    platform: str = Field(min_length=1, max_length=32)
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str = Field(min_length=1, max_length=96)
    sku_id: str | None = Field(default=None, max_length=128)


class ReplyReadinessKnowledgeSnapshotV1(StrictModel):
    material_id: str
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    material_status: str
    template_type: str | None = None
    store_code: str | None = Field(default=None, max_length=96)
    product_id: str | None = Field(default=None, max_length=96)
    sku_id: str | None = Field(default=None, max_length=128)
    analysis_text: str = Field(min_length=1, max_length=64_000)


class ReplyReadinessPublicationStateV1(StrictModel):
    status: str = Field(min_length=1, max_length=32)
    current_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    indexed_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    active_collection: str | None = Field(default=None, max_length=128)


class ReplyReadinessVerifiedProductV1(StrictModel):
    product_reference: str | None = Field(default=None, max_length=255)
    product_name: str | None = Field(default=None, max_length=512)
    sku_reference: str | None = Field(default=None, max_length=255)
    sku_name: str | None = Field(default=None, max_length=512)
    attributes: dict[str, str] = Field(default_factory=dict, max_length=32)


class PddReplyReadinessInputV1(StrictModel):
    schema_version: Literal["pdd-reply-readiness-input.v1"] = "pdd-reply-readiness-input.v1"
    run_id: str = Field(min_length=1, max_length=64)
    test_data_mode: Literal[True] = True
    production_usable: Literal[False] = False
    allow_auto_send: Literal[False] = False
    execution_mode: ReplyReadinessExecutionMode = (
        ReplyReadinessExecutionMode.READINESS_SANDBOX
    )
    scope: ReplyReadinessScopeV1
    question_set: PddQuestionSetProjection
    knowledge_snapshot: ReplyReadinessKnowledgeSnapshotV1 | None = None
    knowledge_sources: list[ReplyReadinessKnowledgeSnapshotV1] = Field(default_factory=list, max_length=64)
    reply_rule_snapshot_revision: int | None = Field(default=None, ge=1)
    reply_rule_snapshot_fingerprint: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    router_build_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    sandbox_vector_identity: str | None = Field(default=None, min_length=1, max_length=255)
    publication_state: ReplyReadinessPublicationStateV1 | None = None
    verified_product: ReplyReadinessVerifiedProductV1 | None = None

    @model_validator(mode="after")
    def one_knowledge_shape(self) -> "PddReplyReadinessInputV1":
        if self.knowledge_snapshot is not None and self.knowledge_sources:
            raise ValueError("knowledge_snapshot and knowledge_sources are mutually exclusive")
        if self.execution_mode is ReplyReadinessExecutionMode.READINESS_SANDBOX:
            if (
                self.reply_rule_snapshot_revision is None
                or self.reply_rule_snapshot_fingerprint is None
                or self.sandbox_vector_identity is None
            ):
                raise ValueError("sandbox evaluation requires frozen rule and vector identities")
            if self.publication_state is not None or self.verified_product is not None:
                raise ValueError("sandbox evaluation cannot consume published debug context")
            return self
        if len(self.question_set.questions) != 1:
            raise ValueError("published router debug requires exactly one question")
        if self.knowledge_snapshot is not None or self.knowledge_sources:
            raise ValueError("published router debug cannot consume sandbox knowledge")
        if self.sandbox_vector_identity is not None:
            raise ValueError("published router debug cannot consume a sandbox vector identity")
        if self.publication_state is None:
            raise ValueError("published router debug requires publication state facts")
        return self


class PddReplyReadinessItemResultV1(StrictModel):
    schema_version: Literal["pdd-reply-readiness-item-result.v1"] = "pdd-reply-readiness-item-result.v1"
    question_id: str
    effective_risk: RiskLevel
    action: ExpectedAction
    origin: str
    answer_preview: str = Field(max_length=2000)
    answer_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    missing_fact_keys: list[str] = Field(default_factory=list, max_length=32)
    blocker_codes: list[str] = Field(default_factory=list, max_length=32)
    prohibited_claim_hits: list[str] = Field(default_factory=list, max_length=32)
    citation_ids: list[str] = Field(default_factory=list, max_length=32)
    evidence_bundle_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def answer_hash_matches(self) -> "PddReplyReadinessItemResultV1":
        expected = hashlib.sha256(self.answer_preview.encode("utf-8")).hexdigest()
        if self.answer_sha256 != expected:
            raise ValueError("answer hash mismatch")
        return self


class PddReplyReadinessResultV1(StrictModel):
    schema_version: Literal["pdd-reply-readiness-result.v1"] = "pdd-reply-readiness-result.v1"
    run_id: str
    status: Literal["COMPLETED"] = "COMPLETED"
    question_set_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    items: list[PddReplyReadinessItemResultV1] = Field(min_length=1, max_length=200)
    result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def hash_matches(self) -> "PddReplyReadinessResultV1":
        expected = canonical_sha256(self.model_dump(mode="json", exclude={"result_sha256"}))
        if self.result_sha256 != expected:
            raise ValueError("result hash mismatch")
        return self


class ReplyReadinessDependencyUsageV1(StrictModel):
    router: bool
    reply_rule: bool
    rag_collection: bool
    knowledge: bool
    model: bool


class ReplyReadinessDiagnosticChangeV1(StrictModel):
    dependency: Literal[
        "router", "reply_rule", "rag_collection", "knowledge", "model"
    ]
    before: str | None = Field(default=None, max_length=512)
    after: str | None = Field(default=None, max_length=512)


class PddReplyReadinessPublishedDebugResultV1(StrictModel):
    schema_version: Literal["pdd-reply-readiness-published-debug-result.v1"]
    simulation_mode: Literal["PUBLISHED_ROUTER_DEBUG"]
    run_id: str = Field(min_length=1, max_length=64)
    status: Literal["COMPLETED", "FAILED"]
    question_set_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    item: PddReplyReadinessItemResultV1 | None = None
    failure_code: str | None = Field(default=None, max_length=96)
    quality_gate_status: Literal["PASS", "MANUAL"]
    rule_references: list[str] = Field(default_factory=list, max_length=32)
    router_build_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    reply_rule_snapshot_fingerprint: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    rag_collection_identity: str | None = Field(default=None, max_length=128)
    knowledge_publication_fingerprint: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    knowledge_publication_status: str = Field(min_length=1, max_length=32)
    model_config_identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime
    dependency_usage: ReplyReadinessDependencyUsageV1
    diagnostic_changes: list[ReplyReadinessDiagnosticChangeV1] = Field(
        default_factory=list, max_length=5
    )
    drifted_dependencies: list[
        Literal["router", "reply_rule", "rag_collection", "knowledge", "model"]
    ] = Field(default_factory=list, max_length=5)
    production_usable: Literal[False]
    allow_auto_send: Literal[False]
    result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def result_is_consistent(self) -> "PddReplyReadinessPublishedDebugResultV1":
        if self.status == "COMPLETED":
            if self.item is None or self.failure_code is not None or self.drifted_dependencies:
                raise ValueError("completed debug result is inconsistent")
        elif (
            self.item is not None
            or self.failure_code != "PRODUCTION_RUNTIME_VERSION_DRIFT"
            or not self.drifted_dependencies
        ):
            raise ValueError("failed debug result is inconsistent")
        expected = canonical_sha256(
            self.model_dump(mode="json", exclude={"result_sha256"})
        )
        if self.result_sha256 != expected:
            raise ValueError("published debug result hash mismatch")
        return self


class ReplyReadinessDebugRequest(StrictModel):
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str = Field(min_length=1, max_length=96)
    sku_id: str | None = Field(default=None, max_length=128)
    customer_message: str = Field(min_length=1, max_length=2000)

    @field_validator("customer_message")
    @classmethod
    def customer_message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("customer_message must not be blank")
        return value


class ReplyReadinessRunCreate(StrictModel):
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str = Field(min_length=1, max_length=96)
    sku_id: str | None = Field(default=None, max_length=128)
    material_id: str | None = Field(default=None, max_length=64)
    material_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def material_reference_complete(self) -> "ReplyReadinessRunCreate":
        if (self.material_id is None) != (self.material_revision is None):
            raise ValueError("material_id and material_revision must be provided together")
        return self


class ReplyReadinessRunProjection(StrictModel):
    run_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    tenant_id: str
    platform: str
    store_code: str
    product_id: str
    sku_id: str | None
    question_set_fingerprint: str
    question_count: int = Field(ge=1)
    material_id: str | None
    material_revision: int | None
    material_content_hash: str | None
    knowledge_source_count: int = Field(ge=0)
    reply_rule_snapshot_revision: int = Field(ge=1)
    reply_rule_snapshot_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    result: PddReplyReadinessResultV1 | None = None
    failure_code: str | None = None
    requested_by: str
    requested_at: datetime
    completed_at: datetime | None


class ReplyReadinessRunList(StrictModel):
    items: list[ReplyReadinessRunProjection]
    total: int = Field(ge=0)


class ReplyReadinessRunComparison(StrictModel):
    baseline_run_id: str
    candidate_run_id: str
    changed_items: list[dict[str, object]]
