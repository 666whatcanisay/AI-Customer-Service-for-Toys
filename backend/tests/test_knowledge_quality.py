"""Unit boundaries for the explicit knowledge-quality analysis bridge.

The HTTP doubles below exercise only A's client/validation boundary.  They do
not represent a production success claim: a real C snapshot and local-model
smoke remain opt-in integration work after the C provider is deployed.
"""

from __future__ import annotations

import json
import urllib.error
from dataclasses import replace
from typing import Any

import pytest

from app.config.settings import Settings
from app.service.knowledge_quality import (
    KnowledgeQualityError,
    KnowledgeQualityService,
    _MAX_ANALYSIS_TEXT_CHARACTERS,
    _parse_model_output,
    _parse_snapshot,
)


MATERIAL_ID = "KMT-controlled-material"
CONTENT_HASH = "sha256:" + ("a" * 64)


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
        knowledge_quality_prompt_version="knowledge-quality.v1",
    )


def _snapshot() -> dict[str, Any]:
    return {
        "material_id": MATERIAL_ID,
        "revision": 1,
        "content_hash": CONTENT_HASH,
        "store_code": "PDD-SM",
        "product_id": "PRODUCT-ONE",
        "sku_id": "SKU-ONE",
        "material_type": "PRODUCT_SPEC",
        "analysis_text": "适用年龄已填写，安全提示清晰。\n但未说明包装清单。",
        "recognition_summary": {
            "readable": True,
            "detected_fields": ["适用年龄", "安全提示"],
            "missing_expected_fields": ["包装清单"],
        },
    }


def _valid_model_output() -> dict[str, Any]:
    return {
        "message": {
            "content": json.dumps(
                {
                    "summary": "资料可读，但仍需补充包装内容说明。",
                    "gaps": [
                        {
                            "gap_code": "MISSING_PACKAGE_CONTENTS",
                            "severity": "MEDIUM",
                            "title": "缺少包装清单",
                            "description": "资料没有明确列出包装内包含的物品。",
                            "recommended_action": "请运营补充与该商品范围一致的包装清单。",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        }
    }


def test_explicit_run_reads_only_approved_inputs_uses_qwen_and_writes_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        calls.append((request.get_method(), request.full_url, body))
        if request.full_url.startswith(
            "http://platform.test/api/v1/admin/knowledge-quality/analysis-inputs?"
        ):
            assert timeout == 5
            assert "material_status=APPROVED_FOR_ANALYSIS" in request.full_url
            return _Response({"items": [_snapshot()], "total": 1})
        if request.full_url == "http://ollama.test/api/chat":
            assert timeout == _settings().llm_timeout_seconds
            assert body is not None
            assert body["model"] == "qwen3.5:9b"
            assert body["stream"] is False
            assert body["think"] is False
            return _Response(_valid_model_output())
        if request.full_url == (
            "http://platform.test/api/v1/admin/knowledge-quality/analysis-results"
        ):
            assert timeout == 5
            assert body is not None
            assert body["material_id"] == MATERIAL_ID
            assert body["revision"] == 1
            assert body["content_hash"] == CONTENT_HASH
            assert body["model_version"] == "qwen3.5:9b"
            assert body["prompt_version"] == "knowledge-quality.v1"
            assert body["summary"] == "资料可读，但仍需补充包装内容说明。"
            assert body["gaps"][0]["gap_code"] == "MISSING_PACKAGE_CONTENTS"
            return _Response(
                {
                    "analysis_run_id": body["analysis_run_id"],
                    "overall_status": "ANALYZED",
                }
            )
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    recorded = KnowledgeQualityService(_settings()).run(1)

    assert recorded["input_material_count"] == 1
    analysis = recorded["analyses"][0]
    assert analysis["material_id"] == MATERIAL_ID
    assert analysis["revision"] == 1
    assert analysis["gap_count"] == 1
    assert analysis["writeback_status"] == "ANALYZED"
    assert "analysis_text" not in json.dumps(recorded, ensure_ascii=False)
    assert "包装清单" not in json.dumps(recorded, ensure_ascii=False)
    assert [method for method, _, _ in calls] == ["GET", "POST", "POST"]


def test_invalid_model_output_is_never_written_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_urlopen(request, timeout):
        del timeout
        calls.append(request.full_url)
        if "analysis-inputs" in request.full_url:
            return _Response({"items": [_snapshot()], "total": 1})
        if request.full_url == "http://ollama.test/api/chat":
            return _Response({"message": {"content": "not structured"}})
        raise AssertionError("writeback must not run for invalid output")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(KnowledgeQualityError) as error:
        KnowledgeQualityService(_settings()).run(1)

    assert error.value.code == "KNOWLEDGE_QUALITY_OUTPUT_INVALID"
    assert error.value.status_code == 422
    assert len(calls) == 2


def test_platform_input_failure_has_a_stable_safe_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        del request, timeout
        raise urllib.error.URLError("controlled platform failure")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(KnowledgeQualityError) as error:
        KnowledgeQualityService(_settings()).run(1)

    assert error.value.code == "KNOWLEDGE_QUALITY_INPUT_UNAVAILABLE"
    assert error.value.status_code == 503


def test_snapshot_accepts_bounded_normal_newlines_and_c_maximum() -> None:
    snapshot = _snapshot()
    snapshot["analysis_text"] = "第一行资料摘要。\r\n第二行资料摘要。"

    parsed = _parse_snapshot(snapshot)

    assert parsed.analysis_text == "第一行资料摘要。\n第二行资料摘要。"

    maximum_snapshot = _snapshot()
    maximum_snapshot["analysis_text"] = (
        ("资" * (_MAX_ANALYSIS_TEXT_CHARACTERS - 2)) + "\n料"
    )
    assert len(_parse_snapshot(maximum_snapshot).analysis_text) == _MAX_ANALYSIS_TEXT_CHARACTERS


@pytest.mark.parametrize("unsafe_text", ["第一行\r第二行", "第一行\x00第二行"])
def test_snapshot_rejects_unsafe_multiline_controls(unsafe_text: str) -> None:
    snapshot = _snapshot()
    snapshot["analysis_text"] = unsafe_text

    with pytest.raises(ValueError):
        _parse_snapshot(snapshot)


def test_writeback_requires_canonical_overall_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout):
        del timeout
        if "analysis-inputs" in request.full_url:
            return _Response({"items": [_snapshot()], "total": 1})
        if request.full_url == "http://ollama.test/api/chat":
            return _Response(_valid_model_output())
        if "analysis-results" in request.full_url:
            payload = json.loads(request.data.decode("utf-8"))
            # A top-level `status` is not the frozen assessment response field.
            return _Response({"analysis_run_id": payload["analysis_run_id"], "status": "ANALYZED"})
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(KnowledgeQualityError) as error:
        KnowledgeQualityService(_settings()).run(1)

    assert error.value.code == "KNOWLEDGE_QUALITY_WRITEBACK_FAILED"
    assert error.value.status_code == 502


def test_non_qwen_configuration_is_model_unavailable() -> None:
    with pytest.raises(KnowledgeQualityError) as error:
        KnowledgeQualityService(replace(_settings(), llm_model="qwen-turbo"))._call_ollama(
            "synthetic prompt"
        )

    assert error.value.code == "KNOWLEDGE_QUALITY_MODEL_UNAVAILABLE"
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps(
            {
                "summary": "English output is not accepted.",
                "gaps": [],
            }
        ),
        json.dumps(
            {
                "summary": "这是中文摘要。",
                "gaps": [{"gap_code": "BAD"}],
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "summary": "这是中文摘要。",
                "gaps": [],
                "unexpected": True,
            },
            ensure_ascii=False,
        ),
    ],
)
def test_model_output_rejects_noncanonical_or_non_chinese_results(raw: str) -> None:
    with pytest.raises(KnowledgeQualityError) as error:
        _parse_model_output(raw)

    assert error.value.code == "KNOWLEDGE_QUALITY_OUTPUT_INVALID"


def test_endpoint_returns_stable_error_without_source_text(api_client) -> None:
    client, _ = api_client
    source_text = "不应由接口回显的审核资料"

    class FailingService:
        def run(self, maximum: int):
            del maximum
            raise KnowledgeQualityError(
                "KNOWLEDGE_QUALITY_MODEL_UNAVAILABLE",
                503,
                "The configured local knowledge-quality model is unavailable.",
            )

    client.app.state.knowledge_quality_service = FailingService()
    response = client.post("/api/admin/ai/knowledge-quality/run", json={"maximum": 1})

    assert response.status_code == 503
    assert response.json()["success"] is False
    assert response.json()["data"] == {"code": "KNOWLEDGE_QUALITY_MODEL_UNAVAILABLE"}
    assert source_text not in response.text


def test_endpoint_rejects_unknown_fields_before_analysis(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/api/admin/ai/knowledge-quality/run",
        json={"maximum": 1, "automatic": True},
    )

    assert response.status_code == 422
