"""Candidate contracts for the AI-CS reply router.

These types remain local to AI-CS until the cross-repository handoff is
coordinated with the Channel Engine consumer. The enabled AI-CS Gateway path
uses them only through the approval-required Router; Gateway V1 stays frozen.
"""

from .contracts import (
    EngineAutoreplyV2AcceptanceV1,
    ReplyEvidenceBundleV1,
    ReplyRulePublicationReceiptV1,
    ReplyRulePublicationV1,
    ReplyRuleV1,
    ReplyTurnEnvelopeV1,
    ReplyTurnParseResult,
    SubQuestionPlanV1,
    parse_reply_turn_envelope,
)
from .router import (
    ReplyQualityGateResultV1,
    ReplyQualityGateStatus,
    ReplyRouter,
)

__all__ = [
    "EngineAutoreplyV2AcceptanceV1",
    "ReplyEvidenceBundleV1",
    "ReplyRulePublicationReceiptV1",
    "ReplyRulePublicationV1",
    "ReplyRuleV1",
    "ReplyTurnEnvelopeV1",
    "ReplyTurnParseResult",
    "SubQuestionPlanV1",
    "parse_reply_turn_envelope",
    "ReplyRouter",
    "ReplyQualityGateResultV1",
    "ReplyQualityGateStatus",
]
