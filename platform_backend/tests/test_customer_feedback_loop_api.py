from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_feedback.models import AIResponseFeedback
from app.customer_feedback_loop.models import AIInteractionEvent


def _event_payload(
    *,
    interaction_id: str = "interaction-001",
    action_type: str = "REJECTED",
    question: str = "客户 13800138000 问订单 123456789012 的适用年龄",
) -> dict[str, object]:
    return {
        "interaction_id": interaction_id,
        "store_code": "STORE-ONE",
        "store_name": "测试店铺",
        "product_id": "PRODUCT-ONE",
        "product_name": "测试积木",
        "sku_id": "SKU-ONE",
        "sku_name": "红色款",
        "action_type": action_type,
        "question_summary": question,
        "ai_answer_summary": "请联系 test@example.com，适用年龄是六到十二岁。",
        "final_answer_summary": (
            "人工修改后的安全回复" if action_type == "EDITED_ACCEPT" else None
        ),
        "created_by": "support-tester",
    }


def _record_event(
    client: TestClient,
    *,
    idempotency_key: str,
    interaction_id: str = "interaction-001",
    action_type: str = "REJECTED",
    question: str = "客户 13800138000 问订单 123456789012 的适用年龄",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/ai-interaction-events",
        json=_event_payload(
            interaction_id=interaction_id,
            action_type=action_type,
            question=question,
        ),
        headers={"Idempotency-Key": idempotency_key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_all_three_customer_actions_are_persisted_idempotently_without_full_pii(
    client: TestClient, session: Session
) -> None:
    direct = _record_event(
        client,
        idempotency_key="event-direct-001",
        interaction_id="interaction-direct",
        action_type="DIRECT_ACCEPT",
    )
    edited = _record_event(
        client,
        idempotency_key="event-edited-001",
        interaction_id="interaction-edited",
        action_type="EDITED_ACCEPT",
    )
    rejected = _record_event(
        client,
        idempotency_key="event-rejected-001",
        interaction_id="interaction-rejected",
        action_type="REJECTED",
    )

    assert direct["status"] == edited["status"] == rejected["status"] == "RECORDED"
    replay = _record_event(
        client,
        idempotency_key="event-rejected-001",
        interaction_id="interaction-rejected",
        action_type="REJECTED",
    )
    assert replay == rejected

    conflict = client.post(
        "/api/v1/ai-interaction-events",
        json=_event_payload(
            interaction_id="interaction-changed", action_type="REJECTED"
        ),
        headers={"Idempotency-Key": "event-rejected-001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "AI_INTERACTION_EVENT_IDEMPOTENCY_CONFLICT"

    events = client.get("/api/v1/admin/ai-feedback-loop/events")
    assert events.status_code == 200
    assert events.json()["total"] == 3
    assert {item["action_type"] for item in events.json()["items"]} == {
        "DIRECT_ACCEPT",
        "EDITED_ACCEPT",
        "REJECTED",
    }
    assert set(events.json()["items"][0]) == {
        "event_id",
        "interaction_id",
        "store_code",
        "store_name",
        "product_id",
        "product_name",
        "sku_id",
        "sku_name",
        "action_type",
        "occurred_at",
        "created_by",
    }

    stored = session.scalars(select(AIInteractionEvent)).all()
    assert len(stored) == 3
    rejected_row = next(row for row in stored if row.action_type == "REJECTED")
    assert "13800138000" not in rejected_row.question_summary
    assert "123456789012" not in rejected_row.question_summary
    assert "test@example.com" not in rejected_row.ai_answer_summary
    assert len(rejected_row.question_summary) <= 240


def test_rejected_event_is_visible_immediately_and_feedback_reason_classifies_it(
    client: TestClient, session: Session,
) -> None:
    _record_event(
        client,
        idempotency_key="event-feedback-link",
        interaction_id="interaction-feedback-link",
        action_type="REJECTED",
        question="这个商品缺少什么年龄信息？",
    )
    before = client.get("/api/v1/admin/ai-feedback-loop/issues")
    assert before.status_code == 200
    assert before.json()["total"] == 1
    assert before.json()["items"][0]["status"] == "NEW"
    assert before.json()["items"][0]["issue_type"] == "UNCLASSIFIED"

    feedback = client.post(
        "/api/v1/ai-response-feedback",
        json={
            "store_code": "STORE-ONE",
            "product_id": "PRODUCT-ONE",
            "sku_id": "SKU-ONE",
            "question": "这个商品缺少什么年龄信息？客户电话 13800138000",
            "ai_answer": "适用年龄是六到十二岁，请联系 test@example.com。",
            "feedback_type": "MISSING_INFO",
            "feedback_note": None,
            "final_answer": None,
            "created_by": "support-tester",
            "interaction_id": "interaction-feedback-link",
            "context": {
                "store_code": "STORE-ONE",
                "product_id": "PRODUCT-ONE",
                "sku_id": "SKU-ONE",
            },
        },
        headers={"Idempotency-Key": "feedback-link-001"},
    )
    assert feedback.status_code == 201, feedback.text
    stored_feedback = session.scalar(select(AIResponseFeedback))
    assert stored_feedback is not None
    assert "13800138000" not in stored_feedback.question
    assert "test@example.com" not in stored_feedback.ai_answer
    assert stored_feedback.redaction_version == "feedback-summary-v1"

    after = client.get("/api/v1/admin/ai-feedback-loop/issues")
    item = after.json()["items"][0]
    assert item["product_name"] == "测试积木"
    assert item["sku_name"] == "红色款"
    assert item["question_summary"] == "这个商品缺少什么年龄信息？"
    assert item["ai_answer_summary"]
    assert item["issue_type"] == "KNOWLEDGE_MISSING"
    assert item["occurrence_count"] == 1
    assert item["status"] == "NEW"


def test_issue_aggregation_knowledge_task_and_reverification_complete_the_manual_loop(
    client: TestClient,
) -> None:
    _record_event(
        client,
        idempotency_key="event-loop-001",
        interaction_id="interaction-loop-001",
        question="这个商品适合几岁？",
    )
    _record_event(
        client,
        idempotency_key="event-loop-002",
        interaction_id="interaction-loop-002",
        question="这个商品适合几岁？",
    )
    issue = client.get("/api/v1/admin/ai-feedback-loop/issues").json()["items"][0]
    assert issue["occurrence_count"] == 2
    problem_id = issue["problem_id"]

    unclassified = client.patch(
        f"/api/v1/admin/ai-feedback-loop/issues/{problem_id}/status",
        json={"status": "CONFIRMED", "operator": "operator-one"},
    )
    assert unclassified.status_code == 422
    assert unclassified.json()["error"]["code"] == "AI_PROBLEM_TYPE_REQUIRED"

    confirmed = client.patch(
        f"/api/v1/admin/ai-feedback-loop/issues/{problem_id}/status",
        json={
            "status": "CONFIRMED",
            "issue_type": "KNOWLEDGE_MISSING",
            "operator": "operator-one",
            "note": "确认缺少适用年龄主题。",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"

    task_response = client.post(
        f"/api/v1/admin/ai-feedback-loop/issues/{problem_id}/knowledge-tasks",
        json={
            "missing_topic": "适用年龄与低龄限制",
            "operator": "operator-one",
            "note": "由运营人工补充并走既有审核流程。",
        },
    )
    assert task_response.status_code == 201
    task = task_response.json()
    assert task["source_problem_id"] == problem_id
    assert task["product_id"] == "PRODUCT-ONE"
    assert task["sku_id"] == "SKU-ONE"
    assert task["status"] == "PENDING"
    task_id = task["task_id"]

    started = client.patch(
        f"/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/status",
        json={
            "status": "IN_PROGRESS",
            "operator": "operator-two",
            "note": "已开始补充。",
        },
    )
    assert started.status_code == 200
    completed = client.patch(
        f"/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/status",
        json={
            "status": "COMPLETED",
            "operator": "operator-two",
            "note": "已通过既有资料审核流程补充；未自动发布。",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"

    not_improved = client.post(
        f"/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/verifications",
        json={
            "result": "NOT_IMPROVED",
            "operator": "operator-three",
            "note": "重新提问后答案仍缺少低龄限制。",
        },
    )
    assert not_improved.status_code == 200
    assert not_improved.json()["status"] == "IN_PROGRESS"
    assert not_improved.json()["verification_result"] == "NOT_IMPROVED"

    recompleted = client.patch(
        f"/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/status",
        json={
            "status": "COMPLETED",
            "operator": "operator-two",
            "note": "补齐低龄限制后再次提交人工审核。",
        },
    )
    assert recompleted.status_code == 200
    improved = client.post(
        f"/api/v1/admin/ai-feedback-loop/knowledge-tasks/{task_id}/verifications",
        json={
            "result": "IMPROVED",
            "operator": "operator-three",
            "note": "重新提问后答案包含适用年龄和低龄限制。",
        },
    )
    assert improved.status_code == 200
    assert improved.json()["status"] == "VERIFIED"
    assert improved.json()["verification_result"] == "IMPROVED"

    final_issue = client.get("/api/v1/admin/ai-feedback-loop/issues").json()["items"][0]
    assert final_issue["status"] == "VERIFIED"
    assert final_issue["knowledge_task"]["status"] == "VERIFIED"
    assert final_issue["knowledge_task"]["missing_topic"] == "适用年龄与低龄限制"
