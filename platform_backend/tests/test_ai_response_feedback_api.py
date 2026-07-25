from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_feedback.models import AIResponseFeedback, AIResponseFeedbackAnalysis


def _seed_feedback(session: Session, **overrides: object) -> AIResponseFeedback:
    values: dict[str, object] = {
        "feedback_id": "ARF-20260725-000001",
        "revision": 1,
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "question": "What safety information is missing?",
        "ai_answer": "This toy is suitable for children aged six to twelve.",
        "final_answer": "It is for ages six to twelve with adult supervision and not for children under three.",
        "feedback_type": "MISSING_INFO",
        "feedback_note": None,
        "created_by": "support-tester",
        "status": "NEW",
        "analysis_status": "NEW",
        "redaction_version": "v1-reminder-only",
    }
    values.update(overrides)
    item = AIResponseFeedback(**values)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _confirm(client, feedback_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/v1/admin/ai-response-feedback/{feedback_id}/confirm",
        json={
            "confirmed_by": "operations-test-operator",
            "confirmation_reason": "Synthetic and de-identified test feedback confirmed for analysis.",
        },
    )
    assert response.status_code == 200
    return response.json()


def _analysis_payload(feedback_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "feedback_id": feedback_id,
        "revision": 1,
        "analysis_run_id": "AQR-test-001",
        "model_version": "synthetic-model-v1",
        "prompt_version": "ai-quality-feedback-v1",
        "analysis": {
            "summary": "The reply omitted a lower-age restriction.",
            "analysis_outcome": "NEEDS_REVIEW",
        },
        "suggestions": [
            {
                "category": "PROMPT_HYPOTHESIS",
                "description": "Include the lower-age safety restriction.",
                "evidence_summary": "Synthetic final-answer comparison.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_only_c_confirmed_feedback_has_a_versioned_export_snapshot(client, session: Session) -> None:
    new_feedback = _seed_feedback(session)
    second_feedback = _seed_feedback(session, feedback_id="ARF-20260725-000002")

    empty = client.get("/api/v1/admin/ai-quality/feedback-cases")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "next_cursor": None}

    confirmed = _confirm(client, new_feedback.feedback_id)
    assert confirmed["revision"] == 1
    assert confirmed["status"] == "ANALYZING"
    assert confirmed["analysis_status"] == "ANALYZING"
    assert confirmed["content_hash"].startswith("sha256:")

    exported = client.get("/api/v1/admin/ai-quality/feedback-cases")
    assert exported.status_code == 200
    assert [item["feedback_id"] for item in exported.json()["items"]] == [new_feedback.feedback_id]
    item = exported.json()["items"][0]
    assert item["revision"] == 1
    assert item["content_hash"] == confirmed["content_hash"]
    assert item["question"] == "What safety information is missing?"
    assert set(item) == {
        "feedback_id", "revision", "question", "ai_answer", "final_answer",
        "feedback_type", "content_hash", "created_at",
    }
    assert second_feedback.feedback_id not in str(exported.json())


def test_analysis_writeback_checks_revision_and_is_idempotent(client, session: Session) -> None:
    feedback = _seed_feedback(session)

    blocked = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(feedback.feedback_id),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_NOT_EXPORTABLE"

    confirmed = _confirm(client, feedback.feedback_id)

    stale = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(feedback.feedback_id, revision=2),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_REVISION_MISMATCH"

    malformed_analysis = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(feedback.feedback_id, analysis=[]),
    )
    assert malformed_analysis.status_code == 422
    assert malformed_analysis.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_ANALYSIS_OUTPUT_INVALID"

    recorded = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(feedback.feedback_id),
    )
    assert recorded.status_code == 201
    assert recorded.json()["status"] == "ANALYZED"
    assert recorded.json()["analysis_run_id"] == "AQR-test-001"
    stored = session.scalar(
        select(AIResponseFeedbackAnalysis).where(
            AIResponseFeedbackAnalysis.feedback_id == feedback.feedback_id
        )
    )
    assert stored is not None
    assert stored.content_hash == confirmed["content_hash"]

    retry = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(feedback.feedback_id),
    )
    assert retry.status_code == 200
    assert retry.json() == recorded.json()

    conflicting_retry = client.post(
        "/api/v1/admin/ai-quality/analysis-results",
        json=_analysis_payload(feedback.feedback_id, analysis={"summary": "Different evidence"}),
    )
    assert conflicting_retry.status_code == 409
    assert conflicting_retry.json()["error"]["code"] == "AI_RESPONSE_FEEDBACK_ANALYSIS_CONFLICT"

    no_longer_exported = client.get("/api/v1/admin/ai-quality/feedback-cases")
    assert no_longer_exported.status_code == 200
    assert no_longer_exported.json() == {"items": [], "next_cursor": None}
