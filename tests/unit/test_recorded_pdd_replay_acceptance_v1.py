from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from channel_agent.providers import RecordedReplayProvider
from channel_engine.recorded_replay_acceptance import (
    ProductScopeIsolationStatus,
    RecordedReplayAcceptanceFixture,
    RecordedReplayDecision,
    ScopeEvidenceStatus,
    evaluate_recorded_replay,
    load_recorded_replay_acceptance,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "simulators"
    / "recorded-replay"
    / "fixtures"
    / "pdd-recorded-replay-20260814.v1.json"
)


def _evaluator_positive_control_decisions(
    fixture: RecordedReplayAcceptanceFixture,
):
    """Exercise scoring only; these values are never passed to Router/RAG."""

    return tuple(
        RecordedReplayDecision(
            external_message_id=reference.external_message_id,
            reply_content=reference.operator_answer,
            action="DIRECT_ANSWER",
            risk_level="LOW",
            quality_status="PASS",
            store_id=reference.store_id,
            product_ref=reference.product_ref,
            sku_ref=reference.sku_ref,
        )
        for reference in fixture.evaluation_references
    )


def test_recorded_replay_uses_existing_provider_wire_and_four_product_scopes() -> None:
    fixture = load_recorded_replay_acceptance(FIXTURE)
    provider_rows = RecordedReplayProvider(FIXTURE).poll(limit=100)

    assert len(fixture.observations) == 16
    assert len(provider_rows) == 16
    assert {item.provider_kind for item in provider_rows} == {"RECORDED_REPLAY"}
    assert {item.product["product_id"] for item in provider_rows} == {
        "970504176629",
        "972030445746",
        "982904528556",
        "984350540183",
    }
    assert all(item.product.get("sku_id") is None for item in provider_rows)
    assert all(not item.visible_history for item in fixture.decision_inputs())
    assert all(
        reference.scope_requirement.value == "PRODUCT_ONLY"
        for reference in fixture.evaluation_references
    )


def test_operator_reference_cannot_leak_into_ai_visible_history() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    answer = raw["evaluation_references"][0]["operator_answer"]
    raw["observations"][0]["visible_history"] = [
        {
            "message_id": "leaked-operator-answer",
            "sender": "OPERATOR",
            "source": "SYNTHETIC",
            "content": answer,
            "content_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "timestamp": "2026-08-14T14:27:50Z",
            "privacy_filtered": True,
        }
    ]

    with pytest.raises(ValidationError, match="evaluation reference leaked"):
        RecordedReplayAcceptanceFixture.model_validate_json(
            json.dumps(raw, ensure_ascii=False)
        )


def test_evaluator_positive_control_proves_product_only_sku_and_80_percent_math() -> None:
    fixture = load_recorded_replay_acceptance(FIXTURE)
    result = evaluate_recorded_replay(
        fixture, _evaluator_positive_control_decisions(fixture)
    )

    assert result.total_cases == 16
    assert result.accepted_cases == 16
    assert result.accuracy == 1.0
    assert result.passed_macro_groups == 6
    assert result.accuracy_gate_passed is True
    assert result.product_scope_isolation is ProductScopeIsolationStatus.PASS
    assert result.simulated_auto_send_ready is True
    assert all(item.scope_status is ProductScopeIsolationStatus.PASS for item in result.case_results)


def test_scope_evidence_tri_state_distinguishes_missing_evidence_from_real_leak() -> None:
    fixture = load_recorded_replay_acceptance(FIXTURE)
    decisions = list(_evaluator_positive_control_decisions(fixture))

    missing_evidence_reference = fixture.evaluation_references[0].model_copy(
        update={
            "scope_evidence": fixture.evaluation_references[0].scope_evidence.model_copy(
                update={"status": ScopeEvidenceStatus.NOT_VERIFIED}
            )
        }
    )
    missing_evidence_fixture = fixture.model_copy(
        update={
            "evaluation_references": (
                missing_evidence_reference,
                *fixture.evaluation_references[1:],
            )
        }
    )
    not_verified = evaluate_recorded_replay(
        missing_evidence_fixture, tuple(decisions)
    )
    assert (
        not_verified.product_scope_isolation
        is ProductScopeIsolationStatus.NOT_VERIFIED
    )
    assert not_verified.simulated_auto_send_ready is False

    decisions[0] = decisions[0].model_copy(update={"product_ref": "wrong-product"})
    blocked = evaluate_recorded_replay(fixture, tuple(decisions))
    assert blocked.product_scope_isolation is ProductScopeIsolationStatus.BLOCKED
    assert blocked.simulated_auto_send_ready is False
    assert "DECISION_SCOPE_MISMATCH" in blocked.case_results[0].reason_codes


def test_missing_ai_decisions_are_not_verified_and_never_auto_ready() -> None:
    fixture = load_recorded_replay_acceptance(FIXTURE)
    result = evaluate_recorded_replay(fixture, ())

    assert result.accepted_cases == 0
    assert result.accuracy_gate_passed is False
    assert result.product_scope_isolation is ProductScopeIsolationStatus.NOT_VERIFIED
    assert result.simulated_auto_send_ready is False
    assert all("DECISION_MISSING" in item.reason_codes for item in result.case_results)
