from __future__ import annotations

import json
from pathlib import Path

from app.reply_readiness.schemas import (
    PddReplyReadinessInputV1,
    PddReplyReadinessPublishedDebugResultV1,
    PddReplyReadinessResultV1,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "contracts" / "candidates" / "pdd-reply-readiness-v1" / "fixtures"


def test_c_accepts_the_a_owned_candidate_wire_fixtures() -> None:
    input_payload = PddReplyReadinessInputV1.model_validate_json(
        (FIXTURE_ROOT / "pdd-reply-readiness-input.valid.json").read_text(encoding="utf-8")
    )
    result_payload = PddReplyReadinessResultV1.model_validate_json(
        (FIXTURE_ROOT / "pdd-reply-readiness-result.valid.json").read_text(encoding="utf-8")
    )
    assert input_payload.run_id == result_payload.run_id
    assert input_payload.question_set.fingerprint == result_payload.question_set_fingerprint
    assert input_payload.production_usable is False
    assert input_payload.allow_auto_send is False
    assert len(input_payload.knowledge_sources) == 1

    legacy_payload = PddReplyReadinessInputV1.model_validate_json(
        (FIXTURE_ROOT / "pdd-reply-readiness-input.legacy-single.valid.json").read_text(encoding="utf-8")
    )
    assert legacy_payload.knowledge_snapshot is not None
    assert legacy_payload.knowledge_sources == []

    debug_input = PddReplyReadinessInputV1.model_validate_json(
        (
            FIXTURE_ROOT / "pdd-reply-readiness-input.published-debug.valid.json"
        ).read_text(encoding="utf-8")
    )
    debug_result = PddReplyReadinessPublishedDebugResultV1.model_validate_json(
        (
            FIXTURE_ROOT / "pdd-reply-readiness-published-debug-result.valid.json"
        ).read_text(encoding="utf-8")
    )
    assert debug_input.run_id == debug_result.run_id
    assert debug_input.execution_mode == "PUBLISHED_ROUTER_DEBUG"
    assert debug_result.dependency_usage.reply_rule is True
    assert debug_result.dependency_usage.rag_collection is False


def test_candidate_result_hash_is_stable_in_c() -> None:
    raw = json.loads(
        (FIXTURE_ROOT / "pdd-reply-readiness-result.valid.json").read_text(encoding="utf-8")
    )
    parsed = PddReplyReadinessResultV1.model_validate(raw)
    assert parsed.result_sha256 == raw["result_sha256"]
