from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Any, Literal, Mapping, TypeAlias

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationError,
    model_validator,
)


MAX_EVIDENCE_BUNDLE_BYTES = 32 * 1024
SHA256_PATTERN = r"^[a-f0-9]{64}$"
GIT_COMMIT_PATTERN = r"^[a-f0-9]{40,64}$"

ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS = (
    "reply_turn_producer",
    "reply_turn_negative_vectors",
    "reply_evidence_consumer",
    "reply_evidence_negative_vectors",
    "ai_reply_package_v2",
    "auto_policy_authorization_v2",
    "human_auto_ledger_separation",
    "execution_time_state_revalidation",
    "versioned_rate_policy",
    "kill_switch",
    "sender_binding",
    "receipt_binding",
    "unknown_no_retry",
    "cross_repo_replay",
)

Identifier: TypeAlias = Annotated[
    str,
    Field(min_length=1, max_length=255, pattern=r"^[^\r\n]+$"),
]
ShortText: TypeAlias = Annotated[
    str,
    Field(min_length=1, max_length=512, pattern=r"^[^\r\n]+$"),
]
Sha256Hex: TypeAlias = Annotated[str, Field(pattern=SHA256_PATTERN)]


def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CandidateModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class ReplyTurnMessageV1(CandidateModel):
    message_id: Identifier
    content_sha256: Sha256Hex
    range_start: int = Field(ge=0, le=8_000)
    range_end: int = Field(gt=0, le=8_000)

    @model_validator(mode="after")
    def range_is_non_empty(self) -> "ReplyTurnMessageV1":
        if self.range_end <= self.range_start:
            raise ValueError("message range must be non-empty")
        return self


class ReplyTurnEnvelopeError(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class ReplyTurnEnvelopeV1(CandidateModel):
    schema_version: Literal["ai-cs-reply-turn.v1"]
    turn_id: Identifier
    aggregate_content_sha256: Sha256Hex
    index_unit: Literal["UNICODE_CODE_POINT"]
    aggregation_separator: Literal["\n"]
    messages: tuple[ReplyTurnMessageV1, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def message_identities_and_ranges_are_ordered(self) -> "ReplyTurnEnvelopeV1":
        identities = [item.message_id for item in self.messages]
        if len(identities) != len(set(identities)):
            raise ValueError("reply turn message ids must be unique")
        if self.messages[0].range_start != 0:
            raise ValueError("reply turn must start at aggregate offset zero")
        for previous, current in zip(self.messages, self.messages[1:]):
            expected = previous.range_end + len(self.aggregation_separator)
            if current.range_start != expected:
                raise ValueError("reply turn ranges must be separated by one joiner")
        return self

    def validate_customer_message(self, customer_message: str) -> None:
        if text_sha256(customer_message) != self.aggregate_content_sha256:
            raise ReplyTurnEnvelopeError("REPLY_TURN_AGGREGATE_HASH_MISMATCH")
        if self.messages[-1].range_end != len(customer_message):
            raise ReplyTurnEnvelopeError("REPLY_TURN_RANGE_COVERAGE_MISMATCH")
        for index, message in enumerate(self.messages):
            fragment = customer_message[message.range_start : message.range_end]
            if not fragment or text_sha256(fragment) != message.content_sha256:
                raise ReplyTurnEnvelopeError("REPLY_TURN_MESSAGE_HASH_MISMATCH")
            if index:
                previous = self.messages[index - 1]
                separator = customer_message[previous.range_end : message.range_start]
                if separator != self.aggregation_separator:
                    raise ReplyTurnEnvelopeError("REPLY_TURN_SEPARATOR_MISMATCH")


class ReplyTurnParseStatus(StrEnum):
    VALID = "VALID"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


class ReplyTurnParseResult(CandidateModel):
    status: ReplyTurnParseStatus
    envelope: ReplyTurnEnvelopeV1 | None = None
    blocker_code: str | None = Field(default=None, max_length=96)

    @model_validator(mode="after")
    def result_is_consistent(self) -> "ReplyTurnParseResult":
        if self.status is ReplyTurnParseStatus.VALID:
            if self.envelope is None or self.blocker_code is not None:
                raise ValueError("valid parse result requires only an envelope")
        elif self.envelope is not None or not self.blocker_code:
            raise ValueError("manual parse result requires only a blocker")
        return self


def parse_reply_turn_envelope(
    context: Mapping[str, Any], customer_message: str
) -> ReplyTurnParseResult:
    raw = context.get("ai_cs_reply_turn")
    if raw is None:
        return ReplyTurnParseResult(
            status=ReplyTurnParseStatus.MANUAL_REQUIRED,
            blocker_code="REPLY_TURN_ENVELOPE_MISSING",
        )
    if not isinstance(raw, dict):
        return ReplyTurnParseResult(
            status=ReplyTurnParseStatus.MANUAL_REQUIRED,
            blocker_code="REPLY_TURN_ENVELOPE_INVALID",
        )
    try:
        envelope = ReplyTurnEnvelopeV1.model_validate_json(
            json.dumps(raw, ensure_ascii=False, allow_nan=False)
        )
        envelope.validate_customer_message(customer_message)
    except ValidationError:
        return ReplyTurnParseResult(
            status=ReplyTurnParseStatus.MANUAL_REQUIRED,
            blocker_code="REPLY_TURN_ENVELOPE_INVALID",
        )
    except ReplyTurnEnvelopeError as exc:
        return ReplyTurnParseResult(
            status=ReplyTurnParseStatus.MANUAL_REQUIRED,
            blocker_code=exc.error_code,
        )
    return ReplyTurnParseResult(
        status=ReplyTurnParseStatus.VALID,
        envelope=envelope,
    )


class RuleScopeKind(StrEnum):
    TENANT = "TENANT"
    STORE = "STORE"
    PRODUCT = "PRODUCT"
    SKU = "SKU"


class ReplyScopeV1(CandidateModel):
    scope_kind: RuleScopeKind
    tenant_id: Identifier
    platform: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[^\r\n]+$")]
    store_code: Identifier | None = None
    product_id: Identifier | None = None
    sku_id: Identifier | None = None

    @model_validator(mode="after")
    def scope_identifiers_match_kind(self) -> "ReplyScopeV1":
        expected = {
            RuleScopeKind.TENANT: (False, False, False),
            RuleScopeKind.STORE: (True, False, False),
            RuleScopeKind.PRODUCT: (True, True, False),
            RuleScopeKind.SKU: (True, True, True),
        }[self.scope_kind]
        actual = (
            self.store_code is not None,
            self.product_id is not None,
            self.sku_id is not None,
        )
        if actual != expected:
            raise ValueError("scope identifiers do not match scope_kind")
        return self

    def contains_frozen_scope(self, frozen: "ReplyScopeV1") -> bool:
        """Return whether this governed source may support the frozen scope."""

        if self.tenant_id != frozen.tenant_id or self.platform != frozen.platform:
            return False
        if self.scope_kind is RuleScopeKind.TENANT:
            return True
        if self.store_code != frozen.store_code:
            return False
        if self.scope_kind is RuleScopeKind.STORE:
            return True
        if self.product_id != frozen.product_id:
            return False
        if self.scope_kind is RuleScopeKind.PRODUCT:
            return True
        return (
            frozen.scope_kind is RuleScopeKind.SKU
            and self.sku_id == frozen.sku_id
        )


class ReplyAction(StrEnum):
    DIRECT_ANSWER = "DIRECT_ANSWER"
    CONTROLLED_ANSWER = "CONTROLLED_ANSWER"
    ASK_CLARIFY = "ASK_CLARIFY"
    REQUIRE_LOOKUP = "REQUIRE_LOOKUP"
    TRANSFER_HUMAN = "TRANSFER_HUMAN"
    REFUSE = "REFUSE"


class ReplyRiskLevel(StrEnum):
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


class ReplyRuleReviewV1(CandidateModel):
    reviewed_by: Identifier
    reviewed_at: AwareDatetime
    review_note: Annotated[str, Field(min_length=1, max_length=2_000)]


class ReplyRuleSourceMaterialV1(CandidateModel):
    """Content-free evidence for the exact governed source revision."""

    material_id: Identifier
    revision: int = Field(ge=1)
    content_sha256: Sha256Hex
    governance_status: Literal["REVIEWED_VALID"]
    scope: ReplyScopeV1
    reviewed_by: Identifier
    reviewed_at: AwareDatetime


ALLOWED_FIXED_VARIABLES = frozenset(
    {
        "product_name",
        "particle_count",
        "finished_size",
        "material",
        "ship_origin",
    }
)


class ReplyRuleV1(CandidateModel):
    schema_version: Literal["reply-rule.v1"]
    rule_id: Identifier
    rule_version: int = Field(ge=1)
    scope: ReplyScopeV1
    canonical_question: Annotated[str, Field(min_length=1, max_length=2_000)]
    aliases: tuple[ShortText, ...] = Field(min_length=1, max_length=64)
    fixed_reply: Annotated[str, Field(min_length=1, max_length=8_000)]
    variable_names: tuple[str, ...] = Field(default=(), max_length=5)
    action: ReplyAction
    risk_level: ReplyRiskLevel
    required_context_fields: tuple[ShortText, ...] = Field(default=(), max_length=32)
    prohibited_claims: tuple[ShortText, ...] = Field(default=(), max_length=32)
    allow_auto_candidate: bool
    source_materials: tuple[ReplyRuleSourceMaterialV1, ...] = Field(
        min_length=1, max_length=32
    )
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None = None
    status: ReplyRuleStatus
    review: ReplyRuleReviewV1 | None = None
    content_fingerprint: Sha256Hex

    @model_validator(mode="after")
    def validate_rule(self) -> "ReplyRuleV1":
        aliases = [item.strip() for item in self.aliases]
        if len(aliases) != len(set(aliases)):
            raise ValueError("reply rule aliases must be unique")
        if len(self.variable_names) != len(set(self.variable_names)):
            raise ValueError("reply rule variables must be unique")
        if not set(self.variable_names).issubset(ALLOWED_FIXED_VARIABLES):
            raise ValueError("reply rule contains an unsupported fixed variable")
        source_ids = [item.material_id for item in self.source_materials]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("reply rule source material ids must be unique")
        if any(
            not item.scope.contains_frozen_scope(self.scope)
            for item in self.source_materials
        ):
            raise ValueError("reply rule source material is narrower than its scope")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("reply rule effective_to must follow effective_from")
        reviewed = self.status in {
            ReplyRuleStatus.APPROVED,
            ReplyRuleStatus.PUBLISHED,
            ReplyRuleStatus.WITHDRAWN,
            ReplyRuleStatus.EXPIRED,
        }
        if reviewed != (self.review is not None):
            raise ValueError("reply rule review does not match lifecycle status")
        if self.content_fingerprint != self.expected_content_fingerprint():
            raise ValueError("reply rule content fingerprint is invalid")
        return self

    def expected_content_fingerprint(self) -> str:
        return canonical_sha256(
            self.model_dump(
                mode="json",
                exclude={
                    "content_fingerprint",
                    "status",
                    "review",
                    "source_materials",
                },
            )
        )


class ReplyRulePublicationV1(CandidateModel):
    schema_version: Literal["reply-rule-publication.v1"]
    publication_id: Identifier
    idempotency_key: Identifier
    tenant_id: Identifier
    platform: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[^\r\n]+$")]
    snapshot_revision: int = Field(ge=1)
    rules: tuple[ReplyRuleV1, ...] = Field(max_length=10_000)
    snapshot_fingerprint: Sha256Hex
    produced_by: Identifier
    produced_at: AwareDatetime

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ReplyRulePublicationV1":
        identities = [(item.rule_id, item.rule_version) for item in self.rules]
        if len(identities) != len(set(identities)):
            raise ValueError("publication contains duplicate rule versions")
        if any(
            item.scope.tenant_id != self.tenant_id
            or item.scope.platform != self.platform
            for item in self.rules
        ):
            raise ValueError("publication contains a rule outside its scope")
        if any(item.status is not ReplyRuleStatus.PUBLISHED for item in self.rules):
            raise ValueError("publication snapshot accepts only published rules")
        if self.snapshot_fingerprint != self.expected_snapshot_fingerprint():
            raise ValueError("publication snapshot fingerprint is invalid")
        return self

    def expected_snapshot_fingerprint(self) -> str:
        return canonical_sha256(
            {
                "tenant_id": self.tenant_id,
                "platform": self.platform,
                "snapshot_revision": self.snapshot_revision,
                "rules": [item.model_dump(mode="json") for item in self.rules],
            }
        )


class ReplyRulePublicationReceiptV1(CandidateModel):
    schema_version: Literal["reply-rule-publication-receipt.v1"]
    publication_id: Identifier
    tenant_id: Identifier
    platform: Annotated[str, Field(min_length=1, max_length=40)]
    snapshot_revision: int = Field(ge=1)
    snapshot_fingerprint: Sha256Hex
    status: Literal["PUBLISHED"]
    changed: bool
    accepted_rule_count: int = Field(ge=0, le=10_000)
    published_at: AwareDatetime


class ReplyRulePublicationContractV1(
    RootModel[ReplyRulePublicationV1 | ReplyRulePublicationReceiptV1]
):
    pass


class SplitStatus(StrEnum):
    SINGLE = "SINGLE"
    SPLIT_CONFIRMED = "SPLIT_CONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"


class SubQuestionRoute(StrEnum):
    FIXED_RULE = "FIXED_RULE"
    RAG = "RAG"
    MANUAL = "MANUAL"


class SourceTextRangeV1(CandidateModel):
    message_id: Identifier
    aggregate_start: int = Field(ge=0, le=8_000)
    aggregate_end: int = Field(gt=0, le=8_000)

    @model_validator(mode="after")
    def range_is_non_empty(self) -> "SourceTextRangeV1":
        if self.aggregate_end <= self.aggregate_start:
            raise ValueError("source range must be non-empty")
        return self


class SubQuestionV1(CandidateModel):
    sub_question_id: Identifier
    ordinal: int = Field(ge=1, le=8)
    source_ranges: tuple[SourceTextRangeV1, ...] = Field(min_length=1, max_length=32)
    source_content_sha256: Sha256Hex
    intent: ShortText
    route: SubQuestionRoute
    depends_on: tuple[Identifier, ...] = Field(default=(), max_length=8)
    blocker_codes: tuple[ShortText, ...] = Field(default=(), max_length=32)


class SubQuestionPlanV1(CandidateModel):
    schema_version: Literal["sub-question-plan.v1"]
    turn_id: Identifier
    aggregate_content_sha256: Sha256Hex
    split_status: SplitStatus
    sub_questions: tuple[SubQuestionV1, ...] = Field(max_length=8)
    blocker_codes: tuple[ShortText, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def validate_plan(self) -> "SubQuestionPlanV1":
        ids = [item.sub_question_id for item in self.sub_questions]
        if len(ids) != len(set(ids)):
            raise ValueError("sub-question ids must be unique")
        if [item.ordinal for item in self.sub_questions] != list(
            range(1, len(self.sub_questions) + 1)
        ):
            raise ValueError("sub-questions must have contiguous ordinals")
        known = set(ids)
        if any(
            dependency not in known or dependency == item.sub_question_id
            for item in self.sub_questions
            for dependency in item.depends_on
        ):
            raise ValueError("sub-question dependency is invalid")
        ambiguous = self.split_status is SplitStatus.AMBIGUOUS
        if ambiguous:
            if not self.blocker_codes:
                raise ValueError("ambiguous plan requires a blocker")
            if any(item.route is not SubQuestionRoute.MANUAL for item in self.sub_questions):
                raise ValueError("ambiguous plan may only route to manual handling")
        elif not self.sub_questions or self.blocker_codes:
            raise ValueError("confirmed plan requires questions and no plan blocker")
        if self.split_status is SplitStatus.SINGLE and len(self.sub_questions) != 1:
            raise ValueError("single plan requires exactly one sub-question")
        if self.split_status is SplitStatus.SPLIT_CONFIRMED and len(self.sub_questions) < 2:
            raise ValueError("split plan requires at least two sub-questions")
        return self


class ReplyOrigin(StrEnum):
    FIXED_RULE = "FIXED_RULE"
    RAG = "RAG"
    COMPOSITE = "COMPOSITE"


class EvidenceSourceType(StrEnum):
    FIXED_RULE = "FIXED_RULE"
    RAG_KNOWLEDGE = "RAG_KNOWLEDGE"


class EvidenceSourceV1(CandidateModel):
    source_id: Identifier
    source_type: EvidenceSourceType
    scope: ReplyScopeV1
    rule_id: Identifier | None = None
    rule_version: int | None = Field(default=None, ge=1)
    rule_content_fingerprint: Sha256Hex | None = None
    rule_snapshot_revision: int | None = Field(default=None, ge=1)
    rule_snapshot_fingerprint: Sha256Hex | None = None
    rule_source_materials: tuple[ReplyRuleSourceMaterialV1, ...] = Field(
        default=(), max_length=32
    )
    knowledge_reference: Identifier | None = None
    knowledge_publication_fingerprint: Sha256Hex | None = None

    @model_validator(mode="after")
    def source_identity_matches_type(self) -> "EvidenceSourceV1":
        rule_identity = (
            self.rule_id is not None
            and self.rule_version is not None
            and self.rule_content_fingerprint is not None
            and self.rule_snapshot_revision is not None
            and self.rule_snapshot_fingerprint is not None
            and bool(self.rule_source_materials)
        )
        knowledge_identity = (
            self.knowledge_reference is not None
            and self.knowledge_publication_fingerprint is not None
        )
        if self.source_type is EvidenceSourceType.FIXED_RULE:
            if not rule_identity or knowledge_identity:
                raise ValueError("fixed-rule evidence identity is invalid")
            if any(
                not item.scope.contains_frozen_scope(self.scope)
                for item in self.rule_source_materials
            ):
                raise ValueError("fixed-rule source material crossed its rule scope")
        elif (
            not knowledge_identity
            or rule_identity
            or self.rule_id is not None
            or self.rule_version is not None
            or self.rule_content_fingerprint is not None
            or self.rule_snapshot_revision is not None
            or self.rule_snapshot_fingerprint is not None
            or self.rule_source_materials
        ):
            raise ValueError("RAG evidence identity is invalid")
        return self


class ProposedContentRangeV1(CandidateModel):
    range_start: int = Field(ge=0, le=8_000)
    range_end: int = Field(gt=0, le=8_000)
    content_sha256: Sha256Hex

    @model_validator(mode="after")
    def range_is_non_empty(self) -> "ProposedContentRangeV1":
        if self.range_end <= self.range_start:
            raise ValueError("proposed content range must be non-empty")
        return self


class ReplySegmentV1(CandidateModel):
    segment_id: Identifier
    ordinal: int = Field(ge=1, le=8)
    sub_question_id: Identifier
    content_range: ProposedContentRangeV1
    action: ReplyAction
    risk_level: ReplyRiskLevel
    source_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=32)


class ReplyFactV1(CandidateModel):
    fact_id: Identifier
    segment_id: Identifier
    content_range: ProposedContentRangeV1
    source_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=32)


class ReplyEvidenceBundleV1(CandidateModel):
    schema_version: Literal["reply-evidence-bundle.v1"]
    reply_origin: ReplyOrigin
    scope: ReplyScopeV1
    sub_question_plan: SubQuestionPlanV1
    segments: tuple[ReplySegmentV1, ...] = Field(min_length=1, max_length=8)
    sources: tuple[EvidenceSourceV1, ...] = Field(min_length=1, max_length=32)
    facts: tuple[ReplyFactV1, ...] = Field(min_length=1, max_length=32)
    warnings: tuple[ShortText, ...] = Field(default=(), max_length=32)
    missing_fields: tuple[ShortText, ...] = Field(default=(), max_length=32)
    blocker_codes: tuple[ShortText, ...] = Field(default=(), max_length=32)
    bundle_sha256: Sha256Hex

    @model_validator(mode="after")
    def validate_bundle(self) -> "ReplyEvidenceBundleV1":
        source_ids = [item.source_id for item in self.sources]
        segment_ids = [item.segment_id for item in self.segments]
        fact_ids = [item.fact_id for item in self.facts]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence source ids must be unique")
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("reply segment ids must be unique")
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("reply fact ids must be unique")
        if [item.ordinal for item in self.segments] != list(
            range(1, len(self.segments) + 1)
        ):
            raise ValueError("reply segments must have contiguous ordinals")
        known_sources = set(source_ids)
        known_segments = set(segment_ids)
        known_questions = {
            item.sub_question_id for item in self.sub_question_plan.sub_questions
        }
        segment_questions = [item.sub_question_id for item in self.segments]
        if len(segment_questions) != len(set(segment_questions)) or set(
            segment_questions
        ) != known_questions:
            raise ValueError("reply segments must cover every sub-question exactly once")
        if any(
            source_id not in known_sources
            for item in (*self.segments, *self.facts)
            for source_id in item.source_ids
        ):
            raise ValueError("reply evidence references an unknown source")
        if any(
            len(item.source_ids) != len(set(item.source_ids))
            for item in (*self.segments, *self.facts)
        ):
            raise ValueError("reply evidence source references must be unique")
        if any(item.segment_id not in known_segments for item in self.facts):
            raise ValueError("reply fact references an unknown segment")
        if {item.segment_id for item in self.facts} != known_segments:
            raise ValueError("every reply segment requires fact evidence")
        segment_by_id = {item.segment_id: item for item in self.segments}
        if any(
            not set(item.source_ids).issubset(
                set(segment_by_id[item.segment_id].source_ids)
            )
            for item in self.facts
        ):
            raise ValueError("reply fact source must belong to its segment")
        if any(
            item.content_range.range_start
            < segment_by_id[item.segment_id].content_range.range_start
            or item.content_range.range_end
            > segment_by_id[item.segment_id].content_range.range_end
            for item in self.facts
        ):
            raise ValueError("reply fact must stay inside its segment")
        if any(not item.scope.contains_frozen_scope(self.scope) for item in self.sources):
            raise ValueError("reply evidence source crossed its frozen scope")
        source_types = {item.source_type for item in self.sources}
        expected_source_types = {
            ReplyOrigin.FIXED_RULE: {EvidenceSourceType.FIXED_RULE},
            ReplyOrigin.RAG: {EvidenceSourceType.RAG_KNOWLEDGE},
            ReplyOrigin.COMPOSITE: {
                EvidenceSourceType.FIXED_RULE,
                EvidenceSourceType.RAG_KNOWLEDGE,
            },
        }[self.reply_origin]
        if source_types != expected_source_types:
            raise ValueError("reply origin does not match its evidence sources")
        if self.bundle_sha256 != self.expected_bundle_sha256():
            raise ValueError("reply evidence bundle hash is invalid")
        if len(canonical_json_bytes(self)) > MAX_EVIDENCE_BUNDLE_BYTES:
            raise ValueError("reply evidence bundle exceeds the candidate size limit")
        return self

    def expected_bundle_sha256(self) -> str:
        return canonical_sha256(
            self.model_dump(mode="json", exclude={"bundle_sha256"})
        )

    def validate_proposed_content(self, proposed_content: str) -> None:
        ranges = [item.content_range for item in self.segments]
        if ranges[0].range_start != 0 or ranges[-1].range_end != len(proposed_content):
            raise ValueError("reply segments do not cover proposed_content")
        for index, content_range in enumerate(ranges):
            if index and content_range.range_start != ranges[index - 1].range_end:
                raise ValueError("reply segments must be contiguous")
            fragment = proposed_content[
                content_range.range_start : content_range.range_end
            ]
            if not fragment or text_sha256(fragment) != content_range.content_sha256:
                raise ValueError("reply segment content hash is invalid")
        for fact in self.facts:
            content_range = fact.content_range
            fragment = proposed_content[
                content_range.range_start : content_range.range_end
            ]
            if not fragment or text_sha256(fragment) != content_range.content_sha256:
                raise ValueError("reply fact content hash is invalid")
        covered = [False] * len(proposed_content)
        for fact in self.facts:
            for offset in range(
                fact.content_range.range_start,
                fact.content_range.range_end,
            ):
                if covered[offset]:
                    raise ValueError("reply fact ranges must not overlap")
                covered[offset] = True
        if any(
            not character.isspace() and not covered[offset]
            for offset, character in enumerate(proposed_content)
        ):
            raise ValueError("reply facts must cover all proposed content")


class EngineAutoreplyAcceptanceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class EngineAutoreplyCheckV1(CandidateModel):
    status: EngineAutoreplyAcceptanceStatus
    evidence_codes: tuple[Identifier, ...] = Field(min_length=1, max_length=16)


class EngineAutoreplySideEffectsV1(CandidateModel):
    engine_source_modified: bool
    runtime_started: bool
    pdd_connected: bool
    real_send_attempted: bool


class EngineAutoreplyV2AcceptanceV1(CandidateModel):
    """Engine-owned test artifact consumed only by the Card 6 verifier."""

    schema_version: Literal["engine-autoreply-v2-acceptance.v1"]
    engine_commit: Annotated[str, Field(pattern=GIT_COMMIT_PATTERN)]
    candidate_manifest_sha256: Sha256Hex
    gateway_wire: Literal["1.0"]
    gateway_raw_sha256: Sha256Hex
    gateway_canonical_sha256: Sha256Hex
    contract_status: Literal["UNCOORDINATED_CANDIDATE"]
    checks: dict[str, EngineAutoreplyCheckV1]
    side_effects: EngineAutoreplySideEffectsV1
    contains_secret_material: bool
    contains_customer_data: bool
    final_status: EngineAutoreplyAcceptanceStatus

    @model_validator(mode="after")
    def acceptance_is_complete_and_consistent(self) -> "EngineAutoreplyV2AcceptanceV1":
        if set(self.checks) != set(ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS):
            raise ValueError("engine acceptance checks are incomplete or unknown")
        all_checks_pass = all(
            item.status is EngineAutoreplyAcceptanceStatus.PASS
            for item in self.checks.values()
        )
        has_side_effect = any(self.side_effects.model_dump().values())
        safe_artifact = not self.contains_secret_material and not self.contains_customer_data
        expected = (
            EngineAutoreplyAcceptanceStatus.PASS
            if all_checks_pass and not has_side_effect and safe_artifact
            else EngineAutoreplyAcceptanceStatus.FAIL
        )
        if self.final_status is not expected:
            raise ValueError("engine acceptance final_status is inconsistent")
        return self


def reply_router_candidate_schemas() -> dict[str, dict[str, Any]]:
    models: dict[str, type[BaseModel]] = {
        "ai-cs-reply-turn.v1.candidate.schema.json": ReplyTurnEnvelopeV1,
        "reply-rule.v1.candidate.schema.json": ReplyRuleV1,
        "reply-rule-publication.v1.candidate.schema.json": (
            ReplyRulePublicationContractV1
        ),
        "sub-question-plan.v1.candidate.schema.json": SubQuestionPlanV1,
        "reply-evidence-bundle.v1.candidate.schema.json": ReplyEvidenceBundleV1,
        "engine-autoreply-v2-acceptance.v1.candidate.schema.json": (
            EngineAutoreplyV2AcceptanceV1
        ),
    }
    result: dict[str, dict[str, Any]] = {}
    for filename, model in models.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:ai-cs:candidate:{filename.removesuffix('.schema.json')}"
        schema["x-ai-cs-contract-status"] = "UNCOORDINATED_CANDIDATE"
        result[filename] = schema
    return result
