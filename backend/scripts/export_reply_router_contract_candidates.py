from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.reply_router.contracts import (
    ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS,
    EngineAutoreplyV2AcceptanceV1,
    ReplyEvidenceBundleV1,
    ReplyRulePublicationV1,
    ReplyRuleV1,
    ReplyTurnEnvelopeV1,
    canonical_sha256,
    reply_router_candidate_schemas,
    text_sha256,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "contracts" / "candidates" / "reply-router-v1"
SCHEMA_ROOT = CANDIDATE_ROOT / "schemas"
FIXTURE_ROOT = CANDIDATE_ROOT / "fixtures"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _build_rule() -> ReplyRuleV1:
    content: dict[str, Any] = {
        "schema_version": "reply-rule.v1",
        "rule_id": "RULE-PRODUCT-MATERIAL-001",
        "rule_version": 1,
        "scope": {
            "scope_kind": "PRODUCT",
            "tenant_id": "TENANT-SYNTHETIC",
            "platform": "pdd",
            "store_code": "STORE-SYNTHETIC",
            "product_id": "PRODUCT-SYNTHETIC",
            "sku_id": None,
        },
        "canonical_question": "这个积木是什么材质？",
        "aliases": ["什么材质", "积木材质"],
        "fixed_reply": "材质为ABS塑料。",
        "variable_names": ["material"],
        "action": "DIRECT_ANSWER",
        "risk_level": "LOW",
        "required_context_fields": ["product_id"],
        "prohibited_claims": ["绝对安全"],
        "allow_auto_candidate": True,
        "source_materials": [
            {
                "material_id": "KMT-SYNTHETIC-PRODUCT-001",
                "revision": 1,
                "content_sha256": "d" * 64,
                "governance_status": "REVIEWED_VALID",
                "scope": {
                    "scope_kind": "PRODUCT",
                    "tenant_id": "TENANT-SYNTHETIC",
                    "platform": "pdd",
                    "store_code": "STORE-SYNTHETIC",
                    "product_id": "PRODUCT-SYNTHETIC",
                    "sku_id": None,
                },
                "reviewed_by": "operator-synthetic",
                "reviewed_at": "2026-08-13T00:00:00Z",
            }
        ],
        "effective_from": "2026-08-13T00:00:00Z",
        "effective_to": None,
        "status": "PUBLISHED",
        "review": {
            "reviewed_by": "operator-synthetic",
            "reviewed_at": "2026-08-13T00:00:00Z",
            "review_note": "synthetic fixture approval",
        },
    }
    fingerprint_payload = {
        key: value
        for key, value in content.items()
        if key not in {"status", "review", "source_materials"}
    }
    content["content_fingerprint"] = canonical_sha256(fingerprint_payload)
    return ReplyRuleV1.model_validate_json(json.dumps(content, ensure_ascii=False))


def _build_publication(rule: ReplyRuleV1) -> ReplyRulePublicationV1:
    fingerprint_payload = {
        "tenant_id": "TENANT-SYNTHETIC",
        "platform": "pdd",
        "snapshot_revision": 1,
        "rules": [rule.model_dump(mode="json")],
    }
    payload = {
        "schema_version": "reply-rule-publication.v1",
        "publication_id": "reply-rule-publication-synthetic-001",
        "idempotency_key": "reply-rule-publication-synthetic-001",
        **fingerprint_payload,
        "snapshot_fingerprint": canonical_sha256(fingerprint_payload),
        "produced_by": "operator-synthetic",
        "produced_at": "2026-08-13T00:01:00Z",
    }
    return ReplyRulePublicationV1.model_validate_json(
        json.dumps(payload, ensure_ascii=False)
    )


def _turn_payload(question: str) -> dict[str, Any]:
    fragments = question.split("\n")
    messages: list[dict[str, Any]] = []
    cursor = 0
    for index, fragment in enumerate(fragments, start=1):
        end = cursor + len(fragment)
        messages.append(
            {
                "message_id": f"PDD-MSG-SYNTHETIC-{index:03d}",
                "content_sha256": text_sha256(fragment),
                "range_start": cursor,
                "range_end": end,
            }
        )
        cursor = end + 1
    return {
        "schema_version": "ai-cs-reply-turn.v1",
        "turn_id": "assistant-turn:synthetic-001",
        "aggregate_content_sha256": text_sha256(question),
        "index_unit": "UNICODE_CODE_POINT",
        "aggregation_separator": "\n",
        "messages": messages,
    }


def _build_bundle(
    question: str,
    proposed_content: str,
    rule: ReplyRuleV1,
    publication: ReplyRulePublicationV1,
) -> ReplyEvidenceBundleV1:
    question_parts = question.split("\n")
    reply_parts = ("材质为ABS塑料。", "适合6岁以上儿童。")
    assert proposed_content == "".join(reply_parts)
    question_second_start = len(question_parts[0]) + 1
    reply_second_start = len(reply_parts[0])
    scope = {
        "scope_kind": "PRODUCT",
        "tenant_id": "TENANT-SYNTHETIC",
        "platform": "pdd",
        "store_code": "STORE-SYNTHETIC",
        "product_id": "PRODUCT-SYNTHETIC",
        "sku_id": None,
    }
    segments = [
        {
            "segment_id": "SEGMENT-001",
            "ordinal": 1,
            "sub_question_id": "SUBQUESTION-001",
            "content_range": {
                "range_start": 0,
                "range_end": reply_second_start,
                "content_sha256": text_sha256(reply_parts[0]),
            },
            "action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "source_ids": ["SOURCE-RULE-001"],
        },
        {
            "segment_id": "SEGMENT-002",
            "ordinal": 2,
            "sub_question_id": "SUBQUESTION-002",
            "content_range": {
                "range_start": reply_second_start,
                "range_end": len(proposed_content),
                "content_sha256": text_sha256(reply_parts[1]),
            },
            "action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "source_ids": ["SOURCE-RAG-001"],
        },
    ]
    payload: dict[str, Any] = {
        "schema_version": "reply-evidence-bundle.v1",
        "reply_origin": "COMPOSITE",
        "scope": scope,
        "sub_question_plan": {
            "schema_version": "sub-question-plan.v1",
            "turn_id": "assistant-turn:synthetic-001",
            "aggregate_content_sha256": text_sha256(question),
            "split_status": "SPLIT_CONFIRMED",
            "sub_questions": [
                {
                    "sub_question_id": "SUBQUESTION-001",
                    "ordinal": 1,
                    "source_ranges": [
                        {
                            "message_id": "PDD-MSG-SYNTHETIC-001",
                            "aggregate_start": 0,
                            "aggregate_end": len(question_parts[0]),
                        }
                    ],
                    "source_content_sha256": text_sha256(question_parts[0]),
                    "intent": "PRODUCT_MATERIAL",
                    "route": "FIXED_RULE",
                    "depends_on": [],
                    "blocker_codes": [],
                },
                {
                    "sub_question_id": "SUBQUESTION-002",
                    "ordinal": 2,
                    "source_ranges": [
                        {
                            "message_id": "PDD-MSG-SYNTHETIC-002",
                            "aggregate_start": question_second_start,
                            "aggregate_end": len(question),
                        }
                    ],
                    "source_content_sha256": text_sha256(question_parts[1]),
                    "intent": "PRODUCT_AGE",
                    "route": "RAG",
                    "depends_on": [],
                    "blocker_codes": [],
                },
            ],
            "blocker_codes": [],
        },
        "segments": segments,
        "sources": [
            {
                "source_id": "SOURCE-RULE-001",
                "source_type": "FIXED_RULE",
                "scope": scope,
                "rule_id": "RULE-PRODUCT-MATERIAL-001",
                "rule_version": 1,
                "rule_content_fingerprint": rule.content_fingerprint,
                "rule_snapshot_revision": publication.snapshot_revision,
                "rule_snapshot_fingerprint": publication.snapshot_fingerprint,
                "rule_source_materials": [
                    item.model_dump(mode="json") for item in rule.source_materials
                ],
                "knowledge_reference": None,
                "knowledge_publication_fingerprint": None,
            },
            {
                "source_id": "SOURCE-RAG-001",
                "source_type": "RAG_KNOWLEDGE",
                "scope": scope,
                "rule_id": None,
                "rule_version": None,
                "rule_content_fingerprint": None,
                "rule_snapshot_revision": None,
                "rule_snapshot_fingerprint": None,
                "rule_source_materials": [],
                "knowledge_reference": "KNOWLEDGE-PRODUCT-AGE-001",
                "knowledge_publication_fingerprint": "a" * 64,
            },
        ],
        "facts": [
            {
                "fact_id": "FACT-001",
                "segment_id": "SEGMENT-001",
                "content_range": segments[0]["content_range"],
                "source_ids": ["SOURCE-RULE-001"],
            },
            {
                "fact_id": "FACT-002",
                "segment_id": "SEGMENT-002",
                "content_range": segments[1]["content_range"],
                "source_ids": ["SOURCE-RAG-001"],
            },
        ],
        "warnings": [],
        "missing_fields": [],
        "blocker_codes": [],
    }
    payload["bundle_sha256"] = canonical_sha256(payload)
    bundle = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(payload, ensure_ascii=False)
    )
    bundle.validate_proposed_content(proposed_content)
    return bundle


def reply_router_candidate_fixtures() -> dict[str, Any]:
    question = "这个积木是什么材质？\n适合几岁？"
    proposed_content = "材质为ABS塑料。适合6岁以上儿童。"
    turn = _turn_payload(question)
    ReplyTurnEnvelopeV1.model_validate_json(
        json.dumps(turn, ensure_ascii=False)
    ).validate_customer_message(question)
    rule = _build_rule()
    publication = _build_publication(rule)
    bundle = _build_bundle(question, proposed_content, rule, publication)

    tampered = json.loads(json.dumps(turn))
    tampered["aggregate_content_sha256"] = "0" * 64
    overlapping = json.loads(json.dumps(turn))
    overlapping["messages"][1]["range_start"] -= 1
    incomplete = json.loads(json.dumps(turn))
    incomplete["messages"][-1]["range_end"] -= 1

    request = {
        "contract_version": "1.0",
        "request_id": "request-synthetic-001",
        "idempotency_key": "idempotency-synthetic-001",
        "correlation_id": "correlation-synthetic-001",
        "conversation_id": "conversation-synthetic-001",
        "message_id": "assistant-input-synthetic-001",
        "customer_message": question,
        "context": {
            "ai_cs_scope": {
                "tenant_id": "TENANT-SYNTHETIC",
                "platform": "pdd",
                "store_code": "STORE-SYNTHETIC",
                "product_id": "PRODUCT-SYNTHETIC",
                "sku_id": None,
            },
            "ai_cs_reply_turn": turn,
        },
        "requested_at": "2026-08-13T00:02:00Z",
    }
    response = {
        "contract_version": "1.0",
        "request_id": request["request_id"],
        "idempotency_key": request["idempotency_key"],
        "correlation_id": request["correlation_id"],
        "decision_id": "decision-synthetic-001",
        "action": "SUGGEST_REPLY",
        "proposed_content": proposed_content,
        "requires_approval": True,
        "risk_level": "LOW",
        "gateway_version": "ai-cs-gateway.v1",
        "metadata": {
            "ai_cs_action": "DIRECT_ANSWER",
            "risk_level": "LOW",
            "warnings": [],
            "required_fields": [],
            "source_count": 2,
            "reply_evidence_bundle": bundle.model_dump(mode="json"),
        },
        "decided_at": "2026-08-13T00:02:01Z",
    }
    engine_acceptance = EngineAutoreplyV2AcceptanceV1.model_validate_json(
        json.dumps(
            {
                "schema_version": "engine-autoreply-v2-acceptance.v1",
                "engine_commit": "b" * 40,
                "candidate_manifest_sha256": "c" * 64,
                "gateway_wire": "1.0",
                "gateway_raw_sha256": (
                    "fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80"
                ),
                "gateway_canonical_sha256": (
                    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
                ),
                "contract_status": "UNCOORDINATED_CANDIDATE",
                "checks": {
                    name: {
                        "status": "PASS",
                        "evidence_codes": [f"{name.upper()}_PASS"],
                    }
                    for name in ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS
                },
                "side_effects": {
                    "engine_source_modified": False,
                    "runtime_started": False,
                    "pdd_connected": False,
                    "real_send_attempted": False,
                },
                "contains_secret_material": False,
                "contains_customer_data": False,
                "final_status": "PASS",
            },
            ensure_ascii=False,
        )
    )
    return {
        "reply-turn-envelope.valid.json": turn,
        "reply-turn-envelope.tampered-hash.json": tampered,
        "reply-turn-envelope.overlapping-range.json": overlapping,
        "reply-turn-envelope.incomplete-range.json": incomplete,
        "reply-turn-context.missing.json": {},
        "reply-rule-publication.valid.json": publication.model_dump(mode="json"),
        "reply-evidence-bundle.valid.json": bundle.model_dump(mode="json"),
        "gateway-decision-request.with-reply-turn.json": request,
        "gateway-decision-response.with-reply-evidence.json": response,
        "engine-autoreply-v2-acceptance.valid.json": engine_acceptance.model_dump(
            mode="json"
        ),
    }


def _expected_files() -> dict[Path, bytes]:
    expected: dict[Path, bytes] = {}
    for filename, schema in reply_router_candidate_schemas().items():
        expected[SCHEMA_ROOT / filename] = _json_bytes(schema)
    for filename, fixture in reply_router_candidate_fixtures().items():
        expected[FIXTURE_ROOT / filename] = _json_bytes(fixture)
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in candidate schemas or fixtures drift",
    )
    args = parser.parse_args()
    expected = _expected_files()
    if args.check:
        drift = [
            str(path.relative_to(ROOT))
            for path, content in expected.items()
            if not path.exists() or path.read_bytes() != content
        ]
        if drift:
            print("candidate contract drift:")
            for path in drift:
                print(f"- {path}")
            return 1
        return 0

    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
