from __future__ import annotations

from pathlib import Path

from app.service.ai_capability import summarize_feedback_analysis_run


def test_control_center_snapshot_is_safe_and_explicit_about_unavailable_data(api_client):
    client, _ = api_client
    response = client.get("/api/admin/ai/control-center")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["schema_version"] == "ai-control-center.v1.1"
    assert data["customer_service"]["module_id"] == "ai_customer_service"
    assert data["prompt"]["prompt_version"]
    assert data["prompt"]["safe_preview"]
    assert data["evaluation"]["execution_mode"] == "EXPLICIT_MANUAL"
    assert data["badcase"] == {
        "status": "NOT_AVAILABLE",
        "reason": (
            "没有面向浏览器的去标识化 Badcase 聚合读接口；控制中心不会读取或推断原始反馈。"
        ),
        "categories": [
            {"category": "FACT_ERROR", "count": None},
            {"category": "MISSING_INFO", "count": None},
            {"category": "STYLE_ISSUE", "count": None},
            {"category": "RISK_ISSUE", "count": None},
        ],
        "raw_content_exposed": False,
    }
    assert data["feedback_analysis"]["raw_content_exposed"] is False
    assert data["feedback_analysis"]["latest_run"] is None
    openapi = client.get("/openapi.json").json()
    control_center = openapi["paths"]["/api/admin/ai/control-center"]["get"]
    assert control_center["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/AiControlCenterResponse"
    )
    serialized = response.text.lower()
    assert "customer question" not in serialized
    assert "feedback_id" not in serialized
    assert "platform_api_base_url" not in serialized


def test_control_center_returns_aggregate_feedback_evidence_without_identifiers(api_client):
    client, _ = api_client
    client.app.state.latest_feedback_analysis_summary = summarize_feedback_analysis_run(
        {
            "input_feedback_count": 2,
            "analyses": [
                {
                    "feedback_id": "FB-DO-NOT-EXPOSE",
                    "analysis_run_id": "AQR-DO-NOT-EXPOSE",
                    "model_version": "qwen3.5:9b",
                    "prompt_version": "ai-quality-feedback-v1",
                    "writeback_status": "ANALYZED",
                    "idempotency_verified": True,
                },
                {
                    "feedback_id": "FB-ALSO-NOT-EXPOSE",
                    "analysis_run_id": "AQR-ALSO-NOT-EXPOSE",
                    "model_version": "qwen3.5:9b",
                    "prompt_version": "ai-quality-feedback-v1",
                    "writeback_status": "ANALYZED",
                    "idempotency_verified": False,
                },
            ],
        }
    )

    response = client.get("/api/admin/ai/control-center")

    assert response.status_code == 200
    latest_run = response.json()["data"]["feedback_analysis"]["latest_run"]
    assert latest_run == {
        "completed_at": latest_run["completed_at"],
        "input_feedback_count": 2,
        "completed_analysis_count": 2,
        "analyzed_writeback_count": 2,
        "idempotency_verified_count": 1,
        "model_version": "qwen3.5:9b",
        "prompt_version": "ai-quality-feedback-v1",
    }
    serialized = response.text
    assert "FB-DO-NOT-EXPOSE" not in serialized
    assert "AQR-DO-NOT-EXPOSE" not in serialized


def test_control_center_projects_saved_evaluation_without_internal_report_path(api_client):
    client, vector_path = api_client
    report_path = (
        Path(vector_path).parent
        / "docs"
        / "rag"
        / "evaluations"
        / "live-control-center-evaluation"
        / "a-t03-evaluation.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        """{
  "evidence_mode": "live_c_api",
  "total": 2,
  "passed": 1,
  "check_pass_counts": {"action": 2, "source_ids": 1, "key_facts": 1, "required_fields": 2, "risk_level": 2, "scope": 2},
  "records": [{"case_id": "CASE-001", "passed": false}]
}""",
        encoding="utf-8",
    )

    response = client.get("/api/admin/ai/control-center")

    assert response.status_code == 200
    evaluation = response.json()["data"]["evaluation"]["evaluation"]
    assert evaluation["evaluation_id"] == "live-control-center-evaluation"
    assert evaluation["failed_case_ids"] == ["CASE-001"]
    assert "report_path" not in evaluation
    assert str(Path(vector_path).parent) not in response.text


def test_feedback_run_summary_drops_raw_and_per_feedback_values():
    summary = summarize_feedback_analysis_run(
        {
            "input_feedback_count": 1,
            "analyses": [
                {
                    "feedback_id": "FB-123",
                    "revision": 1,
                    "feedback_type": "RISK_ISSUE",
                    "analysis_run_id": "AQR-123",
                    "model_version": "qwen3.5:9b",
                    "prompt_version": "ai-quality-feedback-v1",
                    "writeback_status": "ANALYZED",
                    "idempotency_verified": True,
                    "analysis": {"summary": "must not be retained"},
                    "question": "must not be retained",
                    "ai_answer": "must not be retained",
                }
            ],
        }
    )

    assert set(summary) == {
        "completed_at",
        "input_feedback_count",
        "completed_analysis_count",
        "analyzed_writeback_count",
        "idempotency_verified_count",
        "model_version",
        "prompt_version",
    }
    assert summary["input_feedback_count"] == 1
    assert summary["analyzed_writeback_count"] == 1
    assert summary["idempotency_verified_count"] == 1
