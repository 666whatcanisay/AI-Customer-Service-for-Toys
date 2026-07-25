from __future__ import annotations

import json
import urllib.error
from dataclasses import replace
from typing import Any

import pytest

from app.config.settings import Settings
from app.service.experience_evaluation import ExperienceEvaluationService
from app.service.quality_observation import (
    QualityObservationError,
    QualityObservationMetrics,
    QualityObservationService,
)


CASE_ID = "CASE-SYNTHETIC-QUALITY-001"
SOURCE_PHRASE = "synthetic private customer detail"
ADMIN_TEST_CONTEXT = {
    "tenant_id": "TENANT-PDD-SM-TEST",
    "platform": "pdd",
    "store_code": "PDD-SM",
    "product_id": "P-Q80",
    "sku_id": None,
}


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _settings() -> Settings:
    return replace(
        Settings.from_env(),
        llm_provider="ollama",
        llm_model="qwen3.5:9b",
        llm_base_url="http://ollama.test",
        platform_api_base_url="http://platform.test",
        llm_timeout_seconds=2,
        platform_api_timeout_seconds=2,
    )


def _snapshot() -> dict[str, Any]:
    return {
        "case_id": CASE_ID,
        "revision": 1,
        "export_revision": "C-EXP-001",
        "content_hash": "a" * 64,
        "question": SOURCE_PHRASE,
        "ai_answer": "The toy is suitable without any safety reminder.",
        "final_answer": "The toy is suitable only with adult supervision.",
        "context": {
            "store_code": "PDD-SM",
            "product_id": "P-Q80",
            "sku_id": None,
        },
    }


def _evaluation_output() -> dict[str, Any]:
    return {
        "message": {
            "content": json.dumps(
                {
                    "result": {
                        "outcome": "NEEDS_REVIEW",
                        "summary": "The final answer adds a safety condition.",
                        "dimensions": {"safety": "NEEDS_REVIEW"},
                    },
                    "suggestions": [],
                }
            )
        }
    }


def test_explicit_observation_uses_existing_evaluation_writeback_and_keeps_aggregate_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    writeback_payloads: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout):
        del timeout
        calls.append((request.method, request.full_url))
        if "cases/export" in request.full_url:
            return _Response({"items": [_snapshot()], "next_cursor": None})
        if request.full_url == "http://ollama.test/api/chat":
            body = json.loads(request.data.decode("utf-8"))
            if "quality classifier" in body["messages"][1]["content"]:
                return _Response({"message": {"content": '{"issues":["RISK_ISSUE"]}'}})
            return _Response(_evaluation_output())
        if "evaluation-results" in request.full_url:
            payload = json.loads(request.data.decode("utf-8"))
            writeback_payloads.append(payload)
            return _Response(
                {
                    "evaluation_status": "EVALUATED",
                    "case_id": CASE_ID,
                    "revision": 1,
                }
            )
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    metrics = QualityObservationMetrics()
    observer = QualityObservationService(_settings(), metrics)

    recorded = ExperienceEvaluationService(_settings()).run_with_quality_observation(
        CASE_ID, 1, observer
    )

    assert [method for method, _ in calls] == ["GET", "POST", "POST", "POST"]
    assert writeback_payloads[0]["result"]["outcome"] == "NEEDS_REVIEW"
    assert "issues" not in writeback_payloads[0]["result"]
    assert recorded["quality_observation"]["issues"] == ["RISK_ISSUE"]
    assert recorded["quality_observation"]["metrics"]["issue_counts"] == {
        "FACT_ERROR": 0,
        "MISSING_INFO": 0,
        "STYLE_ISSUE": 0,
        "RISK_ISSUE": 1,
    }
    assert (
        recorded["quality_observation"]["metrics"]["prompt_version"]
        == "pilot-quality-observation-v1"
    )
    assert recorded["quality_observation"]["metrics"]["model_version"] == "qwen3.5:9b"
    serialized = json.dumps(recorded)
    assert SOURCE_PHRASE not in serialized
    assert "adult supervision" not in serialized


def test_invalid_issue_classification_does_not_write_back_or_increment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_urlopen(request, timeout):
        del timeout
        calls.append(request.full_url)
        if "cases/export" in request.full_url:
            return _Response({"items": [_snapshot()], "next_cursor": None})
        if request.full_url == "http://ollama.test/api/chat":
            body = json.loads(request.data.decode("utf-8"))
            if "quality classifier" in body["messages"][1]["content"]:
                return _Response({"message": {"content": '{"issues":["UNKNOWN"]}'}})
            return _Response(_evaluation_output())
        raise AssertionError("C writeback must not happen for invalid observation output")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    metrics = QualityObservationMetrics()

    with pytest.raises(QualityObservationError) as error:
        ExperienceEvaluationService(_settings()).run_with_quality_observation(
            CASE_ID, 1, QualityObservationService(_settings(), metrics)
        )

    assert error.value.code == "PILOT_QUALITY_OBSERVATION_OUTPUT_INVALID"
    assert all("evaluation-results" not in call for call in calls)
    assert metrics.snapshot()["classified_case_count"] == 0


def test_quality_observation_api_counts_customer_actions_but_not_admin_tests(
    api_client,
) -> None:
    client, _ = api_client
    rag = client.app.state.rag_service
    actions = iter(["DIRECT_ANSWER", "CONTROLLED_ANSWER", "TRANSFER_HUMAN", "DIRECT_ANSWER"])

    def fake_query(question, context=None):
        del question, context
        return {
            "answer": "safe synthetic answer",
            "action": next(actions),
            "sources": [],
            "model": "synthetic",
            "latency_ms": 1.0,
            "request_id": "synthetic-request",
            "risk_level": "LOW",
            "warnings": [],
            "required_fields": [],
        }

    rag._query = fake_query
    for message in ("one", "two", "three"):
        response = client.post("/api/chat", json={"message": message})
        assert response.status_code == 200
    admin_response = client.post(
        "/api/admin/ai/modules/ai_customer_service/test",
        json={"question": "four", "context": ADMIN_TEST_CONTEXT},
    )
    assert admin_response.status_code == 200

    response = client.get("/api/admin/ai/quality-observation")
    assert response.status_code == 200
    metrics = response.json()["data"]["answer_metrics"]
    assert metrics == {
        "metrics_scope": "since_start",
        "ai_answer_count": 3,
        "direct_answer_count": 1,
        "controlled_answer_count": 1,
        "transfer_human_count": 1,
        "other_action_count": 0,
        "last_answer_at": metrics["last_answer_at"],
    }
    assert metrics["last_answer_at"]
    assert "one" not in response.text
    assert "safe synthetic answer" not in response.text


def test_quality_observation_run_endpoint_is_manual_and_returns_no_source_content(
    api_client,
) -> None:
    client, _ = api_client

    class StubEvaluationService:
        def run_with_quality_observation(self, case_id, revision, observer):
            assert case_id == CASE_ID
            assert revision == 1
            metrics = observer.metrics.record(["FACT_ERROR", "MISSING_INFO"], "qwen3.5:9b")
            return {
                "evaluation_status": "EVALUATED",
                "quality_observation": {
                    "issues": ["FACT_ERROR", "MISSING_INFO"],
                    "metrics": metrics,
                },
            }

    client.app.state.experience_evaluation_service = StubEvaluationService()
    response = client.post(
        "/api/admin/ai/quality-observation/run",
        json={"case_id": CASE_ID, "revision": 1},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["quality_observation"]["issues"] == ["FACT_ERROR", "MISSING_INFO"]
    assert data["quality_observation"]["metrics"]["classified_case_count"] == 1
    assert SOURCE_PHRASE not in response.text


def test_quality_observation_run_rejects_unknown_fields(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/admin/ai/quality-observation/run",
        json={"case_id": CASE_ID, "revision": 1, "automatic": True},
    )

    assert response.status_code == 422
