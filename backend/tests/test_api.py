from __future__ import annotations

from pathlib import Path

from app.service.rag_service import MODEL_NOT_CONFIGURED_MESSAGE


def test_health_check_returns_success(api_client):
    client, _ = api_client
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["status"] == "ok"


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


def test_blank_question_is_rejected(api_client):
    client, _ = api_client
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422
    assert response.json()["success"] is False


def test_unrelated_question_uses_refusal_logic(api_client):
    client, _ = api_client
    response = client.post("/api/chat", json={"message": "火星发动机如何维修"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"] == "知识库中未找到相关内容"
    assert data["sources"] == []


def test_missing_key_keeps_service_alive_and_returns_sources(api_client):
    client, _ = api_client
    response = client.post(
        "/api/chat",
        json={"message": "党员必须履行学习理论、遵守纪律、联系群众等义务。"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["answer"] == MODEL_NOT_CONFIGURED_MESSAGE
    assert data["model_configured"] is False
    assert data["sources"]


def test_retrieval_source_contains_required_fields(api_client):
    client, _ = api_client
    response = client.post(
        "/api/retrieval/search",
        json={"query": "党员义务", "top_k": 1},
    )
    assert response.status_code == 200
    source = response.json()["data"]["sources"][0]
    assert {"file", "page", "distance", "content_preview"} <= source.keys()
    assert isinstance(source["distance"], float)


def test_tests_use_temporary_vector_database(api_client):
    _, vector_path = api_client
    path = Path(vector_path).resolve()
    assert "pytest" in str(path).lower()
    assert path.name == "vector_db"


def test_model_config_never_returns_api_key(api_client):
    client, _ = api_client
    response = client.get("/api/config/model")
    assert response.status_code == 200
    assert response.json()["data"]["configured"] is False
    assert "api_key" not in response.text.lower()
    assert "dashscope" not in response.text.lower()


def test_model_config_is_saved_to_temporary_env_and_applied(api_client):
    client, vector_path = api_client
    test_key = "sk-local-automated-test-only"
    response = client.put(
        "/api/config/model",
        json={
            "provider": "bailian",
            "model": "qwen-turbo",
            "api_key": test_key,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["configured"] is True
    assert test_key not in response.text

    env_text = (Path(vector_path).parent / ".env").read_text(encoding="utf-8")
    assert "LLM_PROVIDER=bailian" in env_text
    assert "LLM_MODEL=qwen-turbo" in env_text
    assert f"DASHSCOPE_API_KEY={test_key}" in env_text
    assert client.get("/api/status").json()["model_configured"] is True


def test_model_config_can_clear_key_without_echoing_it(api_client):
    client, vector_path = api_client
    client.put(
        "/api/config/model",
        json={"provider": "bailian", "model": "qwen-turbo", "api_key": "sk-test"},
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
    assert "sk-test" not in response.text
    env_text = (Path(vector_path).parent / ".env").read_text(encoding="utf-8")
    assert "DASHSCOPE_API_KEY=\n" in env_text
