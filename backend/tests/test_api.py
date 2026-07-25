from __future__ import annotations

from pathlib import Path

from app.service.rag_service import MODEL_NOT_CONFIGURED_MESSAGE, REFUSAL_MESSAGE


ADMIN_TEST_CONTEXT = {
    "tenant_id": "TENANT-PDD-SM-TEST",
    "platform": "pdd",
    "store_code": "PDD-SM",
    "product_id": "P-Q80",
    "sku_id": None,
}


def test_health_check_returns_success(api_client):
    client, _ = api_client
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_status_reports_ready(api_client):
    client, _ = api_client
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_knowledge_statistics_is_available(api_client):
    client, _ = api_client
    response = client.get("/api/knowledge/statistics")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["document_count"] == 1
    assert data["chunk_count"] == 2
    assert data["collection_name"] == "test_documents"


def test_recommended_questions_are_available(api_client):
    client, _ = api_client
    response = client.get("/api/questions/recommended")
    assert response.status_code == 200
    assert len(response.json()["data"]["questions"]) >= 4


def test_retrieval_source_has_required_fields(api_client):
    client, _ = api_client
    response = client.post(
        "/api/retrieval/search",
        json={"query": "星云狐狸玩具的指示灯是紫色", "top_k": 1},
    )
    assert response.status_code == 200
    source = response.json()["data"]["sources"][0]
    assert {"source_name", "page", "chunk_id", "distance", "excerpt"} <= source.keys()
    assert source["source_name"] == "synthetic-toy-guide.pdf"


def test_chat_response_shape_without_cloud_key(api_client):
    client, _ = api_client
    response = client.post(
        "/api/chat", json={"message": "星云狐狸玩具的指示灯是紫色"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"] == MODEL_NOT_CONFIGURED_MESSAGE
    assert data["action"] == "ANSWER"
    assert data["sources"]
    assert {"answer", "action", "sources", "model", "latency_ms", "request_id"} <= data.keys()


def test_unrelated_question_is_controlled_refusal(api_client):
    client, _ = api_client
    response = client.post("/api/chat", json={"message": "火星发动机如何维修"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"] == REFUSAL_MESSAGE
    assert data["action"] == "REFUSE"
    assert data["sources"] == []


def test_blank_question_is_rejected(api_client):
    client, _ = api_client
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


def test_tests_use_temporary_vector_database(api_client):
    _, vector_path = api_client
    path = Path(vector_path).resolve()
    assert "pytest" in str(path).lower()
    assert path.name == "vector_db"


def test_model_config_never_returns_api_key(api_client):
    client, _ = api_client
    response = client.get("/api/config/model")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()
    assert "dashscope" not in response.text.lower()


def test_model_config_is_saved_to_temporary_env_and_applied(api_client):
    client, vector_path = api_client
    test_secret = "synthetic-local-test-secret"
    response = client.put(
        "/api/config/model",
        json={
            "provider": "bailian",
            "model": "qwen-turbo",
            "api_key": test_secret,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["configured"] is True
    assert test_secret not in response.text

    env_text = (Path(vector_path).parent / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=bailian" in env_text
    assert "LLM_MODEL=qwen-turbo" in env_text
    assert f"DASHSCOPE_API_KEY={test_secret}" in env_text
    assert client.get("/api/status").json()["model_configured"] is True


def test_model_config_can_clear_key_without_echoing_it(api_client):
    client, vector_path = api_client
    client.put(
        "/api/config/model",
        json={
            "provider": "bailian",
            "model": "qwen-turbo",
            "api_key": "synthetic-test-secret",
        },
    )
    response = client.put(
        "/api/config/model",
        json={
            "provider": "bailian",
            "model": "qwen-turbo",
            "clear_api_key": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["configured"] is False
    assert "synthetic-test-secret" not in response.text
    env_text = (Path(vector_path).parent / ".env").read_text(encoding="utf-8")
    assert "DASHSCOPE_API_KEY=\n" in env_text


def test_ai_admin_module_registry_and_planned_detail(api_client):
    client, _ = api_client
    response = client.get("/api/admin/ai/modules")

    assert response.status_code == 200
    modules = response.json()["data"]["modules"]
    assert [module["module_id"] for module in modules] == [
        "ai_customer_service",
        "aftersales_intent",
        "shipping_note_extractor",
        "appeal_writer",
        "risk_checker",
    ]
    assert modules[0]["status"] == "RUNNING"
    assert all(module["status"] == "PLANNED" for module in modules[1:])

    planned = client.get("/api/admin/ai/modules/aftersales_intent")
    assert planned.status_code == 200
    detail = planned.json()["data"]
    assert detail["status"] == "PLANNED"
    assert detail["model_provider"] is None
    assert detail["metrics_scope"] == "NOT_AVAILABLE"
    assert detail["call_count"] is None
    assert detail["supported_actions"] == []


def test_ai_admin_customer_service_metadata_and_prompt_are_safe(api_client):
    client, _ = api_client
    detail_response = client.get("/api/admin/ai/modules/ai_customer_service")
    prompt_response = client.get("/api/admin/ai/modules/ai_customer_service/prompt")

    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["ready"] is True
    assert detail["metrics_scope"] == "since_start"
    assert detail["call_count"] == 0
    assert detail["knowledge_count"] == 2
    assert detail["prompt_hash"]
    assert detail["supported_actions"] == [
        "answer_customer_question",
        "search_knowledge",
        "run_online_test",
    ]

    assert prompt_response.status_code == 200
    prompt = prompt_response.json()["data"]
    assert prompt["prompt_version"] == detail["prompt_version"]
    assert prompt["prompt_hash"] == detail["prompt_hash"]
    assert prompt["source_type"] == "code"
    assert prompt["safe_preview"]
    assert "api_key" not in prompt_response.text.lower()
    assert "dasHSCOPE".lower() not in prompt_response.text.lower()
    assert "verified facts:" not in prompt_response.text.lower()


def test_ai_admin_online_test_records_metrics_and_hides_diagnostics_by_default(api_client):
    client, _ = api_client
    response = client.post(
        "/api/admin/ai/modules/ai_customer_service/test",
        json={"question": "Q80 有多少颗？", "context": ADMIN_TEST_CONTEXT},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert {
        "answer",
        "action",
        "risk_level",
        "sources",
        "latency_ms",
        "model",
        "request_id",
    } <= data.keys()
    assert "diagnostics" not in data

    diagnostic_response = client.post(
        "/api/admin/ai/modules/ai_customer_service/test",
        json={
            "question": "Q80 有多少颗？",
            "context": ADMIN_TEST_CONTEXT,
            "include_diagnostics": True,
        },
    )
    assert diagnostic_response.status_code == 200
    diagnostics = diagnostic_response.json()["data"]["diagnostics"]
    assert set(diagnostics) == {"source_count", "warning_codes", "required_fields"}

    detail_response = client.get("/api/admin/ai/modules/ai_customer_service")
    metrics = detail_response.json()["data"]
    assert metrics["call_count"] == 2
    assert metrics["success_count"] == 2
    assert metrics["error_count"] == 0
    assert metrics["last_called_at"]
    assert "Q80 有多少颗" not in detail_response.text


def test_chat_errors_are_counted_without_storing_request_content(api_client):
    client, _ = api_client
    rag = client.app.state.rag_service
    original_search = rag.vector_store.search

    def fail_search(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("synthetic-admin-test-failure")

    rag.vector_store.search = fail_search
    try:
        response = client.post("/api/chat", json={"message": "private test question"})
    finally:
        rag.vector_store.search = original_search

    assert response.status_code == 200
    assert response.json()["data"]["action"] == "REFUSE"
    assert response.json()["data"]["warnings"] == ["RAG_RUNTIME_ERROR"]
    detail_response = client.get("/api/admin/ai/modules/ai_customer_service")
    metrics = detail_response.json()["data"]
    assert metrics["call_count"] == 1
    assert metrics["error_count"] == 1
    assert metrics["last_error_summary"] == "RuntimeError"
    assert "private test question" not in detail_response.text
    assert "synthetic-admin-test-failure" not in detail_response.text


def test_ai_admin_rejects_planned_module_test_with_stable_code(api_client):
    client, _ = api_client
    response = client.post(
        "/api/admin/ai/modules/aftersales_intent/test",
        json={"question": "test", "context": ADMIN_TEST_CONTEXT},
    )

    assert response.status_code == 409
    assert response.json()["data"]["code"] == "AI_MODULE_NOT_TESTABLE"


def test_ai_admin_returns_saved_latest_evaluation_without_absolute_path(api_client):
    client, vector_path = api_client
    report_path = (
        Path(vector_path).parent
        / "docs"
        / "rag"
        / "evaluations"
        / "live-evaluation"
        / "a-t03-evaluation.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        """{
  "evidence_mode": "live_c_api",
  "dataset_version": "V0.3.1",
  "total": 3,
  "passed": 2,
  "pass_rate": 0.6667,
  "check_pass_counts": {
    "action": 3,
    "source_ids": 2,
    "key_facts": 2,
    "required_fields": 3,
    "risk_level": 3,
    "scope": 3
  },
  "records": [
    {"case_id": "CASE-001", "passed": true},
    {"case_id": "CASE-002", "passed": false}
  ]
}""",
        encoding="utf-8",
    )

    response = client.get(
        "/api/admin/ai/modules/ai_customer_service/evaluations/latest"
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "AVAILABLE"
    evaluation = payload["evaluation"]
    assert evaluation["evaluation_id"] == "live-evaluation"
    assert evaluation["executed_at"] == "NOT_AVAILABLE"
    assert evaluation["dataset_version"] == "V0.3.1"
    assert evaluation["failed_case_ids"] == ["CASE-002"]
    assert evaluation["checks"]["source_ids"] == 2
    assert evaluation["report_path"] == "live-evaluation"
    assert str(Path(vector_path).parent) not in response.text


def test_ai_admin_returns_not_available_when_no_real_evaluation_is_saved(api_client):
    client, _ = api_client
    response = client.get(
        "/api/admin/ai/modules/ai_customer_service/evaluations/latest"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "module_id": "ai_customer_service",
        "status": "NOT_AVAILABLE",
        "evaluation": None,
    }
