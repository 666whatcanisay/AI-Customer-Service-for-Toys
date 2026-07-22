from __future__ import annotations

from pathlib import Path

from app.service.rag_service import MODEL_NOT_CONFIGURED_MESSAGE, REFUSAL_MESSAGE


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
