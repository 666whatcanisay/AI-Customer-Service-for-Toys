from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.reply_readiness.contracts import (
    PddReplyReadinessInputV1,
    PddReplyReadinessPublishedDebugResultV1,
    PddReplyReadinessResultV1,
)
from scripts.export_reply_readiness_contract_candidates import build_files


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "contracts" / "candidates" / "pdd-reply-readiness-v1"
SCHEMA_ROOT = CANDIDATE_ROOT / "schemas"
FIXTURE_ROOT = CANDIDATE_ROOT / "fixtures"
GATEWAY_SCHEMA = ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"
FROZEN_GATEWAY_SHA256 = "fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_candidate_export_is_deterministic_and_valid_json_schema() -> None:
    for path, expected in build_files().items():
        assert path.read_bytes() == expected
    for path in SCHEMA_ROOT.glob("*.json"):
        schema = _json(path)
        Draft202012Validator.check_schema(schema)
        assert schema["x-ai-cs-contract-status"] == "UNCOORDINATED_CANDIDATE"


def test_candidate_fixtures_validate_against_schema_and_strict_models() -> None:
    input_payload = _json(FIXTURE_ROOT / "pdd-reply-readiness-input.valid.json")
    legacy_input_payload = _json(FIXTURE_ROOT / "pdd-reply-readiness-input.legacy-single.valid.json")
    result_payload = _json(FIXTURE_ROOT / "pdd-reply-readiness-result.valid.json")
    debug_input_payload = _json(
        FIXTURE_ROOT / "pdd-reply-readiness-input.published-debug.valid.json"
    )
    debug_result_payload = _json(
        FIXTURE_ROOT / "pdd-reply-readiness-published-debug-result.valid.json"
    )
    Draft202012Validator(
        _json(SCHEMA_ROOT / "pdd-reply-readiness-input.v1.candidate.schema.json")
    ).validate(input_payload)
    Draft202012Validator(
        _json(SCHEMA_ROOT / "pdd-reply-readiness-result.v1.candidate.schema.json")
    ).validate(result_payload)
    PddReplyReadinessInputV1.model_validate_json(json.dumps(input_payload, ensure_ascii=False))
    legacy = PddReplyReadinessInputV1.model_validate_json(json.dumps(legacy_input_payload, ensure_ascii=False))
    assert legacy.knowledge_snapshot is not None
    assert legacy.knowledge_sources == []
    PddReplyReadinessResultV1.model_validate_json(json.dumps(result_payload, ensure_ascii=False))
    debug_input = PddReplyReadinessInputV1.model_validate_json(
        json.dumps(debug_input_payload, ensure_ascii=False)
    )
    assert debug_input.execution_mode == "PUBLISHED_ROUTER_DEBUG"
    Draft202012Validator(
        _json(
            SCHEMA_ROOT
            / "pdd-reply-readiness-published-debug-result.v1.candidate.schema.json"
        )
    ).validate(debug_result_payload)
    PddReplyReadinessPublishedDebugResultV1.model_validate_json(
        json.dumps(debug_result_payload, ensure_ascii=False)
    )

    input_payload["allow_auto_send"] = True
    with pytest.raises(ValidationError):
        PddReplyReadinessInputV1.model_validate_json(json.dumps(input_payload, ensure_ascii=False))


def test_candidate_rejects_simultaneous_legacy_and_multi_source_shapes() -> None:
    input_payload = _json(FIXTURE_ROOT / "pdd-reply-readiness-input.valid.json")
    input_payload["knowledge_snapshot"] = input_payload["knowledge_sources"][0]
    with pytest.raises(ValidationError, match="mutually exclusive"):
        PddReplyReadinessInputV1.model_validate_json(json.dumps(input_payload, ensure_ascii=False))


def test_candidate_rejects_question_set_or_answer_hash_tampering() -> None:
    input_payload = _json(FIXTURE_ROOT / "pdd-reply-readiness-input.valid.json")
    input_payload["question_set"]["questions"][0]["canonical_question"] = "被篡改的问题"
    with pytest.raises(ValidationError, match="question set fingerprint"):
        PddReplyReadinessInputV1.model_validate_json(json.dumps(input_payload, ensure_ascii=False))

    result_payload = _json(FIXTURE_ROOT / "pdd-reply-readiness-result.valid.json")
    result_payload["items"][0]["answer_preview"] = "被篡改的回答"
    with pytest.raises(ValidationError, match="answer hash"):
        PddReplyReadinessResultV1.model_validate_json(json.dumps(result_payload, ensure_ascii=False))


def test_formal_contract_and_gateway_remain_frozen() -> None:
    version = _json(ROOT / "contracts" / "version.json")
    assert version["contract_version"] == "0.14.0"
    assert version["status"] == "coordinated"
    assert hashlib.sha256(GATEWAY_SCHEMA.read_bytes()).hexdigest() == FROZEN_GATEWAY_SHA256
