from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from app.reply_readiness.contracts import (
    PddReplyReadinessInputV1,
    PddReplyReadinessItemResultV1,
    PddReplyReadinessPublishedDebugResultV1,
    PddReplyReadinessQuestionV1,
    PddReplyReadinessResultV1,
    canonical_sha256,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "contracts" / "candidates" / "pdd-reply-readiness-v1"
SCHEMA_ROOT = CANDIDATE_ROOT / "schemas"
FIXTURE_ROOT = CANDIDATE_ROOT / "fixtures"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _schema(model: type, contract_type: str) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema["x-ai-cs-contract-status"] = "UNCOORDINATED_CANDIDATE"
    schema["x-ai-cs-contract-type"] = contract_type
    return schema


def _input_wire(payload: PddReplyReadinessInputV1) -> dict[str, Any]:
    wire = payload.model_dump(mode="json", exclude_none=True)
    if not wire.get("knowledge_sources"):
        wire.pop("knowledge_sources", None)
    return wire


def _input() -> PddReplyReadinessInputV1:
    question = {
        "schema_version": "pdd-reply-readiness-question.v1",
        "question_id": "PDD-FINISHED-SIZE",
        "category": "PRODUCT_FACT",
        "canonical_question": "拼好后多大",
        "aliases": ["成品尺寸是多少"],
        "policy_risk_floor": "LOW",
        "expected_action": "DIRECT_ANSWER",
        "required_fact_keys": ["finished_size"],
        "requires_realtime_lookup": False,
        "prohibited_claims": [],
        "mandatory": True,
    }
    question_set_base = {
        "baseline_version": "pdd-common-questions.v1",
        "questions": [question],
    }
    payload = {
        "schema_version": "pdd-reply-readiness-input.v1",
        "run_id": "RRN-SYNTHETIC-CONTRACT-001",
        "test_data_mode": True,
        "production_usable": False,
        "allow_auto_send": False,
        "scope": {
            "tenant_id": "TENANT-SYNTHETIC",
            "platform": "pdd",
            "store_code": "STORE-SYNTHETIC",
            "product_id": "PRODUCT-SYNTHETIC",
            "sku_id": "SKU-SYNTHETIC",
        },
        "question_set": {
            "schema_version": "pdd-reply-readiness-question-set.v1",
            **question_set_base,
            "fingerprint": canonical_sha256(question_set_base),
        },
        "knowledge_sources": [
            {
                "material_id": "KMT-SYNTHETIC-001",
                "revision": 2,
                "content_hash": "sha256:" + "a" * 64,
                "material_status": "RECOGNIZED",
                "template_type": "PRODUCT_KNOWLEDGE",
                "store_code": "STORE-SYNTHETIC",
                "product_id": "PRODUCT-SYNTHETIC",
                "sku_id": "SKU-SYNTHETIC",
                "analysis_text": '{"数据记录":[{"成品尺寸":"40cm"}]}',
            }
        ],
        "reply_rule_snapshot_revision": 1,
        "reply_rule_snapshot_fingerprint": "b" * 64,
        "router_build_fingerprint": canonical_sha256(
            {"component": "ReplyRouter", "contract": "reply-router.v1"}
        ),
        "sandbox_vector_identity": "in-memory-replay:RRN-SYNTHETIC-CONTRACT-001",
    }
    return PddReplyReadinessInputV1.model_validate_json(
        json.dumps(payload, ensure_ascii=False)
    )


def _legacy_input(input_payload: PddReplyReadinessInputV1) -> PddReplyReadinessInputV1:
    payload = input_payload.model_dump(mode="json", exclude_none=True)
    sources = payload.pop("knowledge_sources")
    payload["knowledge_snapshot"] = sources[0]
    return PddReplyReadinessInputV1.model_validate_json(json.dumps(payload, ensure_ascii=False))


def _result(input_payload: PddReplyReadinessInputV1) -> PddReplyReadinessResultV1:
    answer = "亲，这款商品拼好后的成品尺寸是40cm。"
    item = PddReplyReadinessItemResultV1.model_validate_json(
        json.dumps(
            {
                "schema_version": "pdd-reply-readiness-item-result.v1",
                "question_id": "PDD-FINISHED-SIZE",
                "effective_risk": "LOW",
                "action": "DIRECT_ANSWER",
                "origin": "RAG",
                "answer_preview": answer,
                "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
                "missing_fact_keys": [],
                "blocker_codes": [],
                "prohibited_claim_hits": [],
                "citation_ids": ["rr:RRN-SYNTHETIC-CONTRACT-001:PDD-FINISHED-SIZE"],
                "evidence_bundle_sha256": "e" * 64,
            },
            ensure_ascii=False,
        )
    )
    base = {
        "schema_version": "pdd-reply-readiness-result.v1",
        "run_id": input_payload.run_id,
        "status": "COMPLETED",
        "question_set_fingerprint": input_payload.question_set.fingerprint,
        "items": [item.model_dump(mode="json")],
    }
    return PddReplyReadinessResultV1(
        schema_version="pdd-reply-readiness-result.v1",
        run_id=input_payload.run_id,
        status="COMPLETED",
        question_set_fingerprint=input_payload.question_set.fingerprint,
        items=[item],
        result_sha256=canonical_sha256(base),
    )


def _published_debug_input() -> PddReplyReadinessInputV1:
    question = {
        "schema_version": "pdd-reply-readiness-question.v1",
        "question_id": "DEBUG-SYNTHETIC-001",
        "category": "DEBUG",
        "canonical_question": "你好",
        "aliases": [],
        "policy_risk_floor": "LOW",
        "expected_action": "DIRECT_ANSWER",
        "required_fact_keys": [],
        "requires_realtime_lookup": False,
        "prohibited_claims": [],
        "mandatory": True,
    }
    question_set_base = {
        "baseline_version": "pdd-published-router-debug.v1",
        "questions": [question],
    }
    payload = {
        "schema_version": "pdd-reply-readiness-input.v1",
        "run_id": "DBG-SYNTHETIC-CONTRACT-001",
        "test_data_mode": True,
        "production_usable": False,
        "allow_auto_send": False,
        "execution_mode": "PUBLISHED_ROUTER_DEBUG",
        "scope": {
            "tenant_id": "TENANT-SYNTHETIC",
            "platform": "pdd",
            "store_code": "STORE-SYNTHETIC",
            "product_id": "PRODUCT-SYNTHETIC",
            "sku_id": None,
        },
        "question_set": {
            "schema_version": "pdd-reply-readiness-question-set.v1",
            **question_set_base,
            "fingerprint": canonical_sha256(question_set_base),
        },
        "router_build_fingerprint": canonical_sha256(
            {"component": "ReplyRouter", "contract": "reply-router.v1"}
        ),
        "publication_state": {
            "status": "NOT_GENERATED",
            "current_fingerprint": None,
            "indexed_fingerprint": None,
            "active_collection": None,
        },
        "verified_product": {
            "product_reference": "PRODUCT-SYNTHETIC",
            "product_name": "合成积木",
            "sku_reference": None,
            "sku_name": None,
            "attributes": {},
        },
    }
    return PddReplyReadinessInputV1.model_validate_json(
        json.dumps(payload, ensure_ascii=False)
    )


def _published_debug_result(
    input_payload: PddReplyReadinessInputV1,
) -> PddReplyReadinessPublishedDebugResultV1:
    answer = "您好，请问有什么可以帮您？"
    item = {
        "schema_version": "pdd-reply-readiness-item-result.v1",
        "question_id": input_payload.question_set.questions[0].question_id,
        "effective_risk": "LOW",
        "action": "DIRECT_ANSWER",
        "origin": "FIXED_RULE",
        "answer_preview": answer,
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
        "missing_fact_keys": [],
        "blocker_codes": [],
        "prohibited_claim_hits": [],
        "citation_ids": ["reply-rule:RULE-GREETING:v1"],
        "evidence_bundle_sha256": "e" * 64,
    }
    base = {
        "schema_version": "pdd-reply-readiness-published-debug-result.v1",
        "simulation_mode": "PUBLISHED_ROUTER_DEBUG",
        "run_id": input_payload.run_id,
        "status": "COMPLETED",
        "question_set_fingerprint": input_payload.question_set.fingerprint,
        "item": item,
        "failure_code": None,
        "quality_gate_status": "PASS",
        "rule_references": ["RULE-GREETING:v1"],
        "router_build_fingerprint": input_payload.router_build_fingerprint,
        "reply_rule_snapshot_fingerprint": "b" * 64,
        "rag_collection_identity": None,
        "knowledge_publication_fingerprint": None,
        "knowledge_publication_status": "UNAVAILABLE",
        "model_config_identity": "d" * 64,
        "evaluated_at": "2026-08-14T08:00:00Z",
        "dependency_usage": {
            "router": True,
            "reply_rule": True,
            "rag_collection": False,
            "knowledge": False,
            "model": False,
        },
        "diagnostic_changes": [],
        "drifted_dependencies": [],
        "production_usable": False,
        "allow_auto_send": False,
    }
    return PddReplyReadinessPublishedDebugResultV1.model_validate_json(
        json.dumps({**base, "result_sha256": canonical_sha256(base)}, ensure_ascii=False)
    )


def build_files() -> dict[Path, bytes]:
    input_payload = _input()
    legacy_input = _legacy_input(input_payload)
    result = _result(input_payload)
    debug_input = _published_debug_input()
    debug_result = _published_debug_result(debug_input)
    return {
        SCHEMA_ROOT / "pdd-reply-readiness-input.v1.candidate.schema.json": _json_bytes(_schema(PddReplyReadinessInputV1, "PddReplyReadinessInputV1")),
        SCHEMA_ROOT / "pdd-reply-readiness-question.v1.candidate.schema.json": _json_bytes(_schema(PddReplyReadinessQuestionV1, "PddReplyReadinessQuestionV1")),
        SCHEMA_ROOT / "pdd-reply-readiness-item-result.v1.candidate.schema.json": _json_bytes(_schema(PddReplyReadinessItemResultV1, "PddReplyReadinessItemResultV1")),
        SCHEMA_ROOT / "pdd-reply-readiness-result.v1.candidate.schema.json": _json_bytes(_schema(PddReplyReadinessResultV1, "PddReplyReadinessResultV1")),
        SCHEMA_ROOT / "pdd-reply-readiness-published-debug-result.v1.candidate.schema.json": _json_bytes(_schema(PddReplyReadinessPublishedDebugResultV1, "PddReplyReadinessPublishedDebugResultV1")),
        FIXTURE_ROOT / "pdd-reply-readiness-input.valid.json": _json_bytes(_input_wire(input_payload)),
        FIXTURE_ROOT / "pdd-reply-readiness-input.legacy-single.valid.json": _json_bytes(_input_wire(legacy_input)),
        FIXTURE_ROOT / "pdd-reply-readiness-result.valid.json": _json_bytes(result.model_dump(mode="json")),
        FIXTURE_ROOT / "pdd-reply-readiness-input.published-debug.valid.json": _json_bytes(_input_wire(debug_input)),
        FIXTURE_ROOT / "pdd-reply-readiness-published-debug-result.valid.json": _json_bytes(debug_result.model_dump(mode="json")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches: list[str] = []
    for path, content in build_files().items():
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                mismatches.append(str(path.relative_to(ROOT)))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    if mismatches:
        raise SystemExit("candidate drift: " + ", ".join(mismatches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
