from __future__ import annotations

import json
import urllib.error
from dataclasses import replace
from typing import Any

import pytest

from app.config.settings import Settings
from app.service.experience_evaluation import (
    ExperienceEvaluationError,
    ExperienceEvaluationService,
)


CASE_ID = "CEC-test-controlled-evaluation"
EXPORT_REVISION = "CEC-test-controlled-evaluation-r1-e1"
CONTENT_HASH = "sha256:controlled-test-content-hash"


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        del exc_type, exc_value, traceback
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def _settings() -> Settings:
    return replace(
        Settings.from_env(),
        platform_api_base_url="http://platform.test",
        platform_api_timeout_seconds=5,
        llm_provider="ollama",
        llm_model="qwen3.5:9b",
        llm_base_url="http://ollama.test",
        experience_evaluation_prompt_version="experience-evaluation-v1",
    )


def _snapshot() -> dict[str, Any]:
    return {
        "case_id": CASE_ID,
        "revision": 1,
        "export_revision": EXPORT_REVISION,
        "content_hash": CONTENT_HASH,
        "store_code": "STORE-ONE",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "question": "Is this suitable for a six-year-old?",
        "ai_answer": "The draft says ages six to twelve.",
        "final_answer": "It is suitable for ages six to twelve with adult supervision.",
        "context": {
            "store_code": "STORE-ONE",
            "product_id": "PRODUCT-ONE",
            "sku_id": "SKU-ONE",
        },
        "redaction_version": "v1",
    }


def _valid_model_output() -> dict[str, Any]:
    return {
        "message": {
            "content": json.dumps(
                {
                    "result": {
                        "outcome": "KEEP",
                        "summary": "The final answer preserves the verified age guidance.",
                        "dimensions": {
                            "faithfulness": "PASS",
                            "safety": "PASS",
                            "coaching_value": "PASS",
                        },
                    },
                    "suggestions": [
                        {
                            "category": "COACHING",
                            "description": "Keep the adult-supervision reminder.",
                        }
                    ],
                }
            )
        }
    }


def test_explicit_evaluation_reads_snapshot_uses_ollama_and_writes_exact_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        calls.append((request.get_method(), request.full_url, body))
        if request.full_url.startswith("http://platform.test/api/v1/admin/ai-optimization/cases/export"):
            assert timeout == 5
            return _Response({"items": [_snapshot()], "next_cursor": None})
        if request.full_url == "http://ollama.test/api/chat":
            assert timeout == _settings().llm_timeout_seconds
            assert body is not None
            assert body["model"] == "qwen3.5:9b"
            assert body["stream"] is False
            assert body["think"] is False
            return _Response(_valid_model_output())
        if request.full_url == "http://platform.test/api/v1/admin/ai-optimization/evaluation-results":
            assert timeout == 5
            assert body is not None
            assert body["case_id"] == CASE_ID
            assert body["revision"] == 1
            assert body["export_revision"] == EXPORT_REVISION
            assert body["content_hash"] == CONTENT_HASH
            assert body["model_version"] == "qwen3.5:9b"
            assert body["prompt_version"] == "experience-evaluation-v1"
            assert body["result"]["outcome"] == "KEEP"
            assert body["suggestions"][0]["category"] == "COACHING"
            return _Response(
                {
                    "evaluation_run_id": body["evaluation_run_id"],
                    "case_id": CASE_ID,
                    "revision": 1,
                    "export_revision": EXPORT_REVISION,
                    "evaluation_status": "EVALUATED",
                    "model_version": "qwen3.5:9b",
                    "prompt_version": "experience-evaluation-v1",
                    "result": body["result"],
                    "suggestions": body["suggestions"],
                }
            )
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    recorded = ExperienceEvaluationService(_settings()).run(CASE_ID, 1)

    assert recorded["evaluation_status"] == "EVALUATED"
    assert recorded["case_id"] == CASE_ID
    assert "suitable for a six-year-old" not in json.dumps(recorded)
    assert [method for method, _, _ in calls] == ["GET", "POST", "POST"]


def test_invalid_model_output_is_not_written_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(request, timeout):
        del timeout
        calls.append(request.full_url)
        if "cases/export" in request.full_url:
            return _Response({"items": [_snapshot()], "next_cursor": None})
        if request.full_url == "http://ollama.test/api/chat":
            return _Response({"message": {"content": "not structured evaluation"}})
        raise AssertionError("writeback must not run for invalid model output")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ExperienceEvaluationError) as error:
        ExperienceEvaluationService(_settings()).run(CASE_ID, 1)

    assert error.value.code == "EXPERIENCE_EVALUATION_OUTPUT_INVALID"
    assert error.value.status_code == 422
    assert calls == [
        "http://platform.test/api/v1/admin/ai-optimization/cases/export?size=100",
        "http://ollama.test/api/chat",
    ]


def test_flat_qwen_result_shape_is_normalized_before_writeback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writeback_payloads: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout):
        del timeout
        if "cases/export" in request.full_url:
            return _Response({"items": [_snapshot()], "next_cursor": None})
        if request.full_url == "http://ollama.test/api/chat":
            return _Response(
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "result": "NEEDS_REVIEW",
                                "summary": "The human answer adds a safety reminder.",
                                "dimensions": {
                                    "faithfulness": "PASS",
                                    "safety": "NEEDS_REVIEW",
                                },
                                "suggestions": [],
                            }
                        )
                    }
                }
            )
        if "evaluation-results" in request.full_url:
            payload = json.loads(request.data.decode("utf-8"))
            writeback_payloads.append(payload)
            return _Response({"evaluation_status": "EVALUATED"})
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    ExperienceEvaluationService(_settings()).run(CASE_ID, 1)

    assert writeback_payloads[0]["result"] == {
        "outcome": "NEEDS_REVIEW",
        "summary": "The human answer adds a safety reminder.",
        "dimensions": {
            "faithfulness": "PASS",
            "safety": "NEEDS_REVIEW",
        },
    }


def test_missing_approved_snapshot_is_export_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        del timeout
        assert "cases/export" in request.full_url
        return _Response({"items": [], "next_cursor": None})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ExperienceEvaluationError) as error:
        ExperienceEvaluationService(_settings()).run(CASE_ID, 1)

    assert error.value.code == "EXPERIENCE_EVALUATION_EXPORT_UNAVAILABLE"
    assert error.value.status_code == 503


def test_non_ollama_configuration_is_model_unavailable() -> None:
    settings = replace(_settings(), llm_provider="bailian")

    with pytest.raises(ExperienceEvaluationError) as error:
        ExperienceEvaluationService(settings)._call_ollama("synthetic evaluation prompt")

    assert error.value.code == "EXPERIENCE_EVALUATION_MODEL_UNAVAILABLE"
    assert error.value.status_code == 503


def test_platform_writeback_failure_has_stable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        del timeout
        if "cases/export" in request.full_url:
            return _Response({"items": [_snapshot()], "next_cursor": None})
        if request.full_url == "http://ollama.test/api/chat":
            return _Response(_valid_model_output())
        if "evaluation-results" in request.full_url:
            raise urllib.error.URLError("controlled test writeback failure")
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(ExperienceEvaluationError) as error:
        ExperienceEvaluationService(_settings()).run(CASE_ID, 1)

    assert error.value.code == "EXPERIENCE_EVALUATION_WRITEBACK_FAILED"
    assert error.value.status_code == 502


def test_endpoint_returns_frozen_error_code_without_model_or_source_content(api_client) -> None:
    client, _ = api_client

    class FailingService:
        def run(self, case_id: str, revision: int):
            del case_id, revision
            raise ExperienceEvaluationError(
                "EXPERIENCE_EVALUATION_MODEL_UNAVAILABLE",
                503,
                "The configured local evaluation model is unavailable.",
            )

    client.app.state.experience_evaluation_service = FailingService()
    response = client.post(
        "/api/admin/ai/experience-evaluations/run",
        json={"case_id": CASE_ID, "revision": 1},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] == {"code": "EXPERIENCE_EVALUATION_MODEL_UNAVAILABLE"}
    assert "suitable for a six-year-old" not in response.text


def test_endpoint_rejects_unknown_fields_before_evaluation(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/admin/ai/experience-evaluations/run",
        json={"case_id": CASE_ID, "revision": 1, "automatic": True},
    )

    assert response.status_code == 422
