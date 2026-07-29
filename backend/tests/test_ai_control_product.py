from __future__ import annotations

from pathlib import Path


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
    assert data["answer_usage"]["status"] == "NOT_AVAILABLE"
    assert data["latest_quality_analysis"]["status"] == "NOT_AVAILABLE"
    assert len(data["latest_quality_analysis"]["findings"]) == 5
    assert data["runtime"]["runtime_commit_sha_status"] == "NOT_AVAILABLE"
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


def test_product_overview_projects_saved_evaluation_without_case_data(api_client):
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
  "records": [{
    "case_id": "CASE-MUST-NOT-LEAK",
    "passed": false,
    "expected_key_facts": ["customer content must not leak"]
  }]
}""",
        encoding="utf-8",
    )

    response = client.get("/api/admin/ai/control-center/product-overview")

    assert response.status_code == 200
    evaluation = response.json()["data"]["latest_evaluation"]
    assert evaluation["status"] == "AVAILABLE"
    assert evaluation["evaluation_id"] == "live-product-evaluation"
    assert evaluation["total_case_count"] == 3
    assert evaluation["passed_case_count"] == 2
    assert evaluation["failed_case_count"] == 1
    assert evaluation["pass_rate_percent"] == 66.67
    assert "CASE-MUST-NOT-LEAK" not in response.text
    assert "customer content must not leak" not in response.text
