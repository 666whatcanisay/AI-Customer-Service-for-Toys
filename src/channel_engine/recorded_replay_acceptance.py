from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from channel_engine.provider import NormalizedChannelObservation


class RecordedReplayAcceptanceError(ValueError):
    pass


class ReplayModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ScopeRequirement(StrEnum):
    PRODUCT_ONLY = "PRODUCT_ONLY"
    SKU_REQUIRED = "SKU_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ScopeEvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"


class ProductScopeIsolationStatus(StrEnum):
    PASS = "PASS"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"


class ReplayScopeEvidence(ReplayModel):
    status: ScopeEvidenceStatus
    source_locator: str = Field(min_length=1, max_length=255)
    verification_method: str = Field(min_length=1, max_length=128)
    product_card_visible: bool
    sku_visible: bool


class ReplayEvaluationReference(ReplayModel):
    case_id: str = Field(pattern=r"^RPD-[0-9]{3}$")
    external_message_id: str = Field(min_length=1, max_length=255)
    macro_group: Literal[
        "SIZE", "IMAGE", "PACKAGING", "SHIPPING", "PARTICLE_COUNT", "SCALE"
    ]
    store_id: str = Field(min_length=1, max_length=160)
    product_ref: str = Field(min_length=1, max_length=255)
    sku_ref: str | None = Field(default=None, min_length=1, max_length=255)
    scope_requirement: ScopeRequirement
    scope_evidence: ReplayScopeEvidence
    operator_answer: str = Field(min_length=1, max_length=8_000, repr=False)
    expected_fact_groups: tuple[tuple[str, ...], ...] = Field(min_length=1)
    forbidden_cross_product_facts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_scope_requirement(self) -> ReplayEvaluationReference:
        if self.scope_requirement is ScopeRequirement.SKU_REQUIRED and self.sku_ref is None:
            raise ValueError("SKU_REQUIRED reference must identify the SKU")
        if self.scope_requirement is ScopeRequirement.PRODUCT_ONLY and self.product_ref == "":
            raise ValueError("PRODUCT_ONLY reference must identify the product")
        return self


class RecordedReplayAcceptanceFixture(ReplayModel):
    schema_version: Literal["ai-cs.recorded-pdd-evaluation.v1"] = Field(
        alias="schema"
    )
    source_origin: Literal["RECORDED_PDD_20260814"]
    source_document_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    observations: tuple[NormalizedChannelObservation, ...] = Field(
        min_length=1, max_length=100
    )
    evaluation_references: tuple[ReplayEvaluationReference, ...] = Field(
        min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def validate_reference_isolation(self) -> RecordedReplayAcceptanceFixture:
        observations = {item.external_message_id: item for item in self.observations}
        references = {item.external_message_id: item for item in self.evaluation_references}
        if len(observations) != len(self.observations):
            raise ValueError("recorded replay observation message IDs must be unique")
        if len(references) != len(self.evaluation_references):
            raise ValueError("recorded replay reference message IDs must be unique")
        if observations.keys() != references.keys():
            raise ValueError("every observation must have exactly one evaluation reference")

        for message_id, observation in observations.items():
            reference = references[message_id]
            if observation.provider_kind != "RECORDED_REPLAY":
                raise ValueError("recorded fixture must use the existing RECORDED_REPLAY kind")
            if observation.store_id != reference.store_id:
                raise ValueError("evaluation reference crossed its store boundary")
            if observation.product.get("product_id") != reference.product_ref:
                raise ValueError("evaluation reference crossed its product boundary")
            if observation.product.get("sku_id") != reference.sku_ref:
                raise ValueError("evaluation reference crossed its SKU boundary")

            visible = [observation.content]
            visible.extend(item.content for item in observation.visible_history)
            normalized_reference = _normalize_text(reference.operator_answer)
            if any(
                normalized_reference
                and normalized_reference in _normalize_text(value)
                for value in visible
            ):
                raise ValueError(
                    "evaluation reference leaked into the AI-visible conversation"
                )
        return self

    def decision_inputs(self) -> tuple[NormalizedChannelObservation, ...]:
        """Return only AI-visible inputs; evaluation references never cross this port."""

        return self.observations


class RecordedReplayDecision(ReplayModel):
    external_message_id: str = Field(min_length=1, max_length=255)
    reply_content: str | None = Field(default=None, max_length=8_000, repr=False)
    action: Literal[
        "DIRECT_ANSWER",
        "CONTROLLED_ANSWER",
        "ASK_CLARIFY",
        "REQUIRE_LOOKUP",
        "TRANSFER_HUMAN",
        "REFUSE",
        "MANUAL",
    ]
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    quality_status: Literal["PASS", "BLOCKED"]
    store_id: str = Field(min_length=1, max_length=160)
    product_ref: str | None = Field(default=None, max_length=255)
    sku_ref: str | None = Field(default=None, max_length=255)


class RecordedReplayCaseResult(ReplayModel):
    case_id: str
    external_message_id: str
    macro_group: str
    answer_acceptable: bool
    scope_status: ProductScopeIsolationStatus
    auto_candidate: bool
    reason_codes: tuple[str, ...]


class RecordedReplayAcceptanceResult(ReplayModel):
    schema_version: Literal["ai-cs.recorded-pdd-acceptance-result.v1"] = Field(
        default="ai-cs.recorded-pdd-acceptance-result.v1",
        serialization_alias="schema",
    )
    source_origin: Literal["RECORDED_PDD_20260814"]
    total_cases: int
    accepted_cases: int
    accuracy: float
    passed_macro_groups: int
    total_macro_groups: int
    accuracy_gate_passed: bool
    product_scope_isolation: ProductScopeIsolationStatus
    simulated_auto_send_ready: bool
    case_results: tuple[RecordedReplayCaseResult, ...]


def load_recorded_replay_acceptance(
    path: str | Path,
) -> RecordedReplayAcceptanceFixture:
    try:
        return RecordedReplayAcceptanceFixture.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RecordedReplayAcceptanceError(
            "recorded PDD replay fixture failed validation"
        ) from exc


def evaluate_recorded_replay(
    fixture: RecordedReplayAcceptanceFixture,
    decisions: tuple[RecordedReplayDecision, ...],
    *,
    minimum_accepted_cases: int = 13,
    minimum_macro_groups: int = 5,
) -> RecordedReplayAcceptanceResult:
    decision_by_message = {item.external_message_id: item for item in decisions}
    if len(decision_by_message) != len(decisions):
        raise RecordedReplayAcceptanceError("decision message IDs must be unique")

    case_results: list[RecordedReplayCaseResult] = []
    group_results: dict[str, list[bool]] = defaultdict(list)
    for reference in fixture.evaluation_references:
        decision = decision_by_message.get(reference.external_message_id)
        reasons: list[str] = []
        if decision is None:
            answer_acceptable = False
            scope_status = ProductScopeIsolationStatus.NOT_VERIFIED
            reasons.extend(("DECISION_MISSING", "DECISION_SCOPE_NOT_VERIFIED"))
        else:
            normalized_reply = _normalize_text(decision.reply_content or "")
            expected = all(
                any(_normalize_text(candidate) in normalized_reply for candidate in group)
                for group in reference.expected_fact_groups
            )
            forbidden = any(
                _normalize_text(item) in normalized_reply
                for item in reference.forbidden_cross_product_facts
            )
            answer_acceptable = (
                decision.action in {"DIRECT_ANSWER", "CONTROLLED_ANSWER"}
                and decision.quality_status == "PASS"
                and expected
                and not forbidden
            )
            if not expected:
                reasons.append("EXPECTED_FACT_MISSING")
            if forbidden:
                reasons.append("CROSS_PRODUCT_FACT_DETECTED")
            if decision.quality_status != "PASS":
                reasons.append("QUALITY_NOT_PASS")
            if decision.action not in {"DIRECT_ANSWER", "CONTROLLED_ANSWER"}:
                reasons.append("ACTION_NOT_ANSWER")

            if (
                decision.store_id != reference.store_id
                or (
                    decision.product_ref is not None
                    and decision.product_ref != reference.product_ref
                )
                or (
                    decision.sku_ref is not None
                    and decision.sku_ref != reference.sku_ref
                )
            ):
                scope_status = ProductScopeIsolationStatus.BLOCKED
                reasons.append("DECISION_SCOPE_MISMATCH")
            elif reference.scope_evidence.status is ScopeEvidenceStatus.NOT_VERIFIED:
                scope_status = ProductScopeIsolationStatus.NOT_VERIFIED
                reasons.append("SOURCE_SCOPE_NOT_VERIFIED")
            elif decision.product_ref is None:
                scope_status = ProductScopeIsolationStatus.NOT_VERIFIED
                reasons.append("DECISION_PRODUCT_SCOPE_MISSING")
            elif (
                reference.scope_requirement is ScopeRequirement.SKU_REQUIRED
                and decision.sku_ref is None
            ):
                scope_status = ProductScopeIsolationStatus.NOT_VERIFIED
                reasons.append("DECISION_SKU_SCOPE_MISSING")
            elif reference.scope_requirement is ScopeRequirement.UNKNOWN:
                scope_status = ProductScopeIsolationStatus.NOT_VERIFIED
                reasons.append("SCOPE_REQUIREMENT_UNKNOWN")
            else:
                scope_status = ProductScopeIsolationStatus.PASS

        auto_candidate = bool(
            decision is not None
            and answer_acceptable
            and scope_status is ProductScopeIsolationStatus.PASS
            and decision.action == "DIRECT_ANSWER"
            and decision.risk_level == "LOW"
            and decision.quality_status == "PASS"
        )
        if not reasons:
            reasons.append("CASE_PASS")
        group_results[reference.macro_group].append(answer_acceptable)
        case_results.append(
            RecordedReplayCaseResult(
                case_id=reference.case_id,
                external_message_id=reference.external_message_id,
                macro_group=reference.macro_group,
                answer_acceptable=answer_acceptable,
                scope_status=scope_status,
                auto_candidate=auto_candidate,
                reason_codes=tuple(sorted(set(reasons))),
            )
        )

    accepted_cases = sum(item.answer_acceptable for item in case_results)
    passed_macro_groups = sum(
        sum(items) >= math.ceil(len(items) * 0.8) for items in group_results.values()
    )
    scope_values = {item.scope_status for item in case_results}
    product_scope = (
        ProductScopeIsolationStatus.BLOCKED
        if ProductScopeIsolationStatus.BLOCKED in scope_values
        else ProductScopeIsolationStatus.NOT_VERIFIED
        if ProductScopeIsolationStatus.NOT_VERIFIED in scope_values
        else ProductScopeIsolationStatus.PASS
    )
    accuracy_gate = (
        accepted_cases >= minimum_accepted_cases
        and passed_macro_groups >= minimum_macro_groups
    )
    return RecordedReplayAcceptanceResult(
        source_origin=fixture.source_origin,
        total_cases=len(case_results),
        accepted_cases=accepted_cases,
        accuracy=(accepted_cases / len(case_results)) if case_results else 0.0,
        passed_macro_groups=passed_macro_groups,
        total_macro_groups=len(group_results),
        accuracy_gate_passed=accuracy_gate,
        product_scope_isolation=product_scope,
        simulated_auto_send_ready=bool(
            accuracy_gate
            and product_scope is ProductScopeIsolationStatus.PASS
            and any(item.auto_candidate for item in case_results)
        ),
        case_results=tuple(case_results),
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


__all__ = [
    "ProductScopeIsolationStatus",
    "RecordedReplayAcceptanceError",
    "RecordedReplayAcceptanceFixture",
    "RecordedReplayAcceptanceResult",
    "RecordedReplayDecision",
    "ScopeEvidenceStatus",
    "ScopeRequirement",
    "evaluate_recorded_replay",
    "load_recorded_replay_acceptance",
]
