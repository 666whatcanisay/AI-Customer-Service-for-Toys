from __future__ import annotations

from pathlib import Path

from app.service.ai_capability import summarize_feedback_analysis_run


def test_root_explains_that_8000_is_an_api_not_the_operations_console(api_client):
    client, _ = api_client

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "title": "AI 能力中心服务接口",
        "service_type": "AI_SERVICE_API",
        "usage_note": "这是 AI 服务接口，不是运营后台。",
        "operations_console": "http://127.0.0.1:5174",
        "operations_console_note": "运营请前往 5174 的 AI 控制中心。",
        "product_overview": "/api/admin/ai/control-center/product-overview",
        "message": response.json()["message"],
        "docs": "/docs",
        "health": "/api/health",
    }


def test_product_overview_is_safe_read_only_ui_projection(api_client):
    client, _ = api_client
    client.app.state.initialization_error = "raw-initialization-detail-must-not-leak"

    response = client.get("/api/admin/ai/control-center/product-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "AI 控制中心产品数据投影"
    data = payload["data"]
    assert data["schema_version"] == "ai-control-center.product.v1"
    assert data["service"]["initialization_error_exposed"] is False
    assert data["model"]["availability_probed"] is False
    assert data["knowledge"]["last_sync_at"] is None
    assert data["knowledge"]["last_sync_status"] == "NOT_AVAILABLE"
    assert data["answer_usage"]["metrics_scope"] == "A_PROCESS_SINCE_START"
    assert data["answer_usage"]["reset_on_restart"] is True
    assert data["latest_evaluation"]["status"] == "NOT_AVAILABLE"
    assert data["latest_quality_analysis"]["status"] == "NOT_AVAILABLE"
    assert len(data["latest_quality_analysis"]["findings"]) == 5
    assert data["runtime"] == {
        "service_version": client.app.version,
        "runtime_commit_sha": None,
        "runtime_commit_sha_status": "NOT_AVAILABLE",
        "metrics_scope": "A_PROCESS_SINCE_START",
        "metrics_reset_on_restart": True,
    }
    assert data["raw_content_exposed"] is False
    assert data["model_call_performed"] is False
    assert data["business_write_performed"] is False
    serialized = response.text
    assert "raw-initialization-detail-must-not-leak" not in serialized
    assert "feedback_id" not in serialized.lower()
    assert "platform_api_base_url" not in serialized.lower()

    openapi = client.get("/openapi.json").json()
    projection = openapi["paths"]["/api/admin/ai/control-center/product-overview"]["get"]
    assert projection["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/AiControlCenterProductResponse")


def test_product_overview_projects_saved_evaluation_and_quality_without_case_data(api_client):
    client, vector_path = api_client
    report_path = (
        Path(vector_path).parent
        / "docs"
        / "rag"
        / "evaluations"
        / "live-product-evaluation"
        / "a-t03-evaluation.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        """{
  "evidence_mode": "live_c_api",
  "dataset_version": "V0.3.1",
  "executed_at": "2026-07-28T00:00:00+00:00",
  "total": 3,
  "passed": 2,
  "check_pass_counts": {"action": 3, "source_ids": 2, "key_facts": 2, "required_fields": 3, "risk_level": 3, "scope": 3},
  "records": [{
    "case_id": "CASE-MUST-NOT-LEAK",
    "passed": false,
    "failure_classes": ["metadata_loss"],
    "checks": {"source_ids": false, "key_facts": false},
    "expected_source_ids": ["SRC-MUST-NOT-LEAK"],
    "missing_source_ids": ["SRC-MUST-NOT-LEAK"],
    "expected_key_facts": ["customer content must not leak"]
  }]
}""",
        encoding="utf-8",
    )

    response = client.get("/api/admin/ai/control-center/product-overview")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["latest_evaluation"] == {
        "status": "AVAILABLE",
        "source": "SAVED_LIVE_C_API",
        "evaluation_id": "live-product-evaluation",
        "recorded_at": "2026-07-28T00:00:00+00:00",
        "recorded_at_status": "AVAILABLE",
        "dataset_version": "V0.3.1",
        "dataset_version_status": "AVAILABLE",
        "total_case_count": 3,
        "passed_case_count": 2,
        "failed_case_count": 1,
        "pass_rate_percent": 66.67,
        "summary": "最近真实评测：2/3 通过，通过率 66.67%。",
    }
    findings = {
        finding["category"]: finding
        for finding in data["latest_quality_analysis"]["findings"]
    }
    assert findings["DATA_PROBLEM"]["affected_case_count"] == 1
    assert findings["DATA_PROBLEM"]["evidence"] == "DIRECT_EVALUATOR_SIGNAL"
    assert findings["KNOWLEDGE_PROBLEM"]["affected_case_count"] == 1
    assert findings["KNOWLEDGE_PROBLEM"]["evidence"] == "DIRECT_EVALUATOR_SIGNAL"
    assert all(item["automatic_change_allowed"] is False for item in findings.values())
    assert "CASE-MUST-NOT-LEAK" not in response.text
    assert "SRC-MUST-NOT-LEAK" not in response.text
    assert "customer content must not leak" not in response.text


def test_product_overview_keeps_only_feedback_aggregates(api_client):
    client, _ = api_client
    client.app.state.latest_feedback_analysis_summary = summarize_feedback_analysis_run(
        {
            "input_feedback_count": 1,
            "analyses": [
                {
                    "feedback_id": "FB-MUST-NOT-LEAK",
                    "analysis_run_id": "AQR-MUST-NOT-LEAK",
                    "model_version": "qwen3.5:9b",
                    "prompt_version": "ai-quality-feedback-v1",
                    "writeback_status": "ANALYZED",
                    "idempotency_verified": True,
                    "analysis": {"summary": "must not leak"},
                }
            ],
        }
    )

    response = client.get("/api/admin/ai/control-center/product-overview")

    assert response.status_code == 200
    feedback = response.json()["data"]["feedback_analysis"]
    assert feedback["completed_analysis_count"] == 1
    assert feedback["raw_content_exposed"] is False
    assert "FB-MUST-NOT-LEAK" not in response.text
    assert "AQR-MUST-NOT-LEAK" not in response.text
    assert "must not leak" not in response.text
