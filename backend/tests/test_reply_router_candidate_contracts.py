from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.gateway.contract import DecisionRequest, DecisionResponse
from app.reply_router.contracts import (
    ReplyEvidenceBundleV1,
    ReplyRulePublicationV1,
    ReplyTurnEnvelopeV1,
    ReplyTurnParseStatus,
    canonical_sha256,
    parse_reply_turn_envelope,
    reply_router_candidate_schemas,
    text_sha256,
)
from scripts.export_reply_router_contract_candidates import (
    reply_router_candidate_fixtures,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "contracts" / "candidates" / "reply-router-v1"
SCHEMA_ROOT = CANDIDATE_ROOT / "schemas"
FIXTURE_ROOT = CANDIDATE_ROOT / "fixtures"
GATEWAY_SCHEMA = (
    ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"
)
RAW_GATEWAY_SHA256 = (
    "fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80"
)
CANONICAL_GATEWAY_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_gateway_v1_frozen_raw_and_canonical_hashes_are_unchanged() -> None:
    raw = GATEWAY_SCHEMA.read_bytes()
    parsed = json.loads(raw)
    canonical = json.dumps(
        parsed,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert hashlib.sha256(raw).hexdigest() == RAW_GATEWAY_SHA256
    assert hashlib.sha256(canonical).hexdigest() == CANONICAL_GATEWAY_SHA256


def test_checked_in_candidate_schemas_match_local_strict_models() -> None:
    expected = reply_router_candidate_schemas()
    for filename, schema in expected.items():
        checked_in = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(checked_in)
        assert checked_in == schema
        assert checked_in["x-ai-cs-contract-status"] == "UNCOORDINATED_CANDIDATE"


def test_checked_in_candidate_fixtures_are_deterministic() -> None:
    expected = reply_router_candidate_fixtures()
    checked_in = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in FIXTURE_ROOT.glob("*.json")
    }
    assert checked_in == expected


def test_valid_candidate_fixtures_conform_to_checked_in_schemas() -> None:
    publication = _fixture("reply-rule-publication.valid.json")
    evidence = _fixture("reply-evidence-bundle.valid.json")
    cases = {
        "ai-cs-reply-turn.v1.candidate.schema.json": _fixture(
            "reply-turn-envelope.valid.json"
        ),
        "reply-rule.v1.candidate.schema.json": publication["rules"][0],
        "reply-rule-publication.v1.candidate.schema.json": publication,
        "sub-question-plan.v1.candidate.schema.json": evidence[
            "sub_question_plan"
        ],
        "reply-evidence-bundle.v1.candidate.schema.json": evidence,
        "engine-autoreply-v2-acceptance.v1.candidate.schema.json": _fixture(
            "engine-autoreply-v2-acceptance.valid.json"
        ),
    }
    for schema_name, fixture in cases.items():
        schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(fixture)


def test_valid_reply_turn_envelope_preserves_message_boundaries() -> None:
    request = _fixture("gateway-decision-request.with-reply-turn.json")
    result = parse_reply_turn_envelope(request["context"], request["customer_message"])
    assert result.status is ReplyTurnParseStatus.VALID
    assert result.envelope is not None
    assert [item.message_id for item in result.envelope.messages] == [
        "PDD-MSG-SYNTHETIC-001",
        "PDD-MSG-SYNTHETIC-002",
    ]


@pytest.mark.parametrize(
    ("fixture_name", "blocker_code"),
    [
        ("reply-turn-envelope.tampered-hash.json", "REPLY_TURN_AGGREGATE_HASH_MISMATCH"),
        ("reply-turn-envelope.incomplete-range.json", "REPLY_TURN_RANGE_COVERAGE_MISMATCH"),
    ],
)
def test_reply_turn_content_mismatch_fails_closed(
    fixture_name: str, blocker_code: str
) -> None:
    request = _fixture("gateway-decision-request.with-reply-turn.json")
    request["context"]["ai_cs_reply_turn"] = _fixture(fixture_name)
    result = parse_reply_turn_envelope(request["context"], request["customer_message"])
    assert result.status is ReplyTurnParseStatus.MANUAL_REQUIRED
    assert result.envelope is None
    assert result.blocker_code == blocker_code


def test_reply_turn_missing_or_structurally_invalid_fails_closed() -> None:
    request = _fixture("gateway-decision-request.with-reply-turn.json")
    missing = parse_reply_turn_envelope({}, request["customer_message"])
    assert missing.status is ReplyTurnParseStatus.MANUAL_REQUIRED
    assert missing.blocker_code == "REPLY_TURN_ENVELOPE_MISSING"

    request["context"]["ai_cs_reply_turn"] = _fixture(
        "reply-turn-envelope.overlapping-range.json"
    )
    invalid = parse_reply_turn_envelope(
        request["context"], request["customer_message"]
    )
    assert invalid.status is ReplyTurnParseStatus.MANUAL_REQUIRED
    assert invalid.blocker_code == "REPLY_TURN_ENVELOPE_INVALID"


def test_candidate_models_forbid_unknown_fields() -> None:
    payload = _fixture("reply-turn-envelope.valid.json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        ReplyTurnEnvelopeV1.model_validate(payload)


def test_rule_publication_fixture_has_valid_content_and_snapshot_fingerprints() -> None:
    publication = ReplyRulePublicationV1.model_validate_json(
        (FIXTURE_ROOT / "reply-rule-publication.valid.json").read_text(encoding="utf-8")
    )
    assert publication.snapshot_fingerprint == publication.expected_snapshot_fingerprint()
    assert publication.rules[0].content_fingerprint == (
        publication.rules[0].expected_content_fingerprint()
    )


def test_evidence_bundle_hash_and_reply_ranges_are_valid() -> None:
    response_payload = _fixture("gateway-decision-response.with-reply-evidence.json")
    bundle = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(response_payload["metadata"]["reply_evidence_bundle"], ensure_ascii=False)
    )
    bundle.validate_proposed_content(response_payload["proposed_content"])
    assert bundle.bundle_sha256 == bundle.expected_bundle_sha256()


def test_tampered_evidence_bundle_fails_closed() -> None:
    payload = _fixture("reply-evidence-bundle.valid.json")
    payload["warnings"] = ["TAMPERED"]
    with pytest.raises(ValidationError, match="bundle hash"):
        ReplyEvidenceBundleV1.model_validate_json(json.dumps(payload, ensure_ascii=False))


def test_fixed_rule_evidence_requires_exact_source_revision_and_snapshot() -> None:
    missing = _fixture("reply-evidence-bundle.valid.json")
    missing["sources"][0]["rule_source_materials"] = []
    _rehash_evidence(missing)
    with pytest.raises(ValidationError, match="fixed-rule evidence identity"):
        ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(missing, ensure_ascii=False)
        )

    crossed = _fixture("reply-evidence-bundle.valid.json")
    crossed["sources"][0]["rule_source_materials"][0]["scope"][
        "product_id"
    ] = "PRODUCT-OTHER"
    _rehash_evidence(crossed)
    with pytest.raises(ValidationError, match="crossed its rule scope"):
        ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(crossed, ensure_ascii=False)
        )


def _rehash_evidence(payload: dict) -> None:
    payload["bundle_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "bundle_sha256"}
    )


def test_evidence_bundle_rejects_unknown_version_and_cross_tenant_source() -> None:
    unknown = _fixture("reply-evidence-bundle.valid.json")
    unknown["schema_version"] = "reply-evidence-bundle.v999"
    _rehash_evidence(unknown)
    with pytest.raises(ValidationError):
        ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(unknown, ensure_ascii=False)
        )

    crossed = _fixture("reply-evidence-bundle.valid.json")
    crossed["sources"][0]["scope"]["tenant_id"] = "TENANT-OTHER"
    _rehash_evidence(crossed)
    with pytest.raises(
        ValidationError,
        match="crossed its (?:rule|frozen) scope",
    ):
        ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(crossed, ensure_ascii=False)
        )


def test_evidence_facts_must_cover_all_non_whitespace_reply_content() -> None:
    response = _fixture("gateway-decision-response.with-reply-evidence.json")
    payload = response["metadata"]["reply_evidence_bundle"]
    payload["facts"][0]["content_range"]["range_end"] = 8
    payload["facts"][0]["content_range"]["content_sha256"] = text_sha256(
        response["proposed_content"][:8]
    )
    _rehash_evidence(payload)
    bundle = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(payload, ensure_ascii=False)
    )
    with pytest.raises(ValueError, match="cover all proposed content"):
        bundle.validate_proposed_content(response["proposed_content"])


def test_evidence_fact_cannot_borrow_another_segments_source() -> None:
    payload = _fixture("reply-evidence-bundle.valid.json")
    payload["facts"][0]["source_ids"] = payload["segments"][1]["source_ids"]
    _rehash_evidence(payload)
    with pytest.raises(ValidationError, match="belong to its segment"):
        ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(payload, ensure_ascii=False)
        )


def test_evidence_bundle_enforces_canonical_size_limit() -> None:
    payload = _fixture("reply-evidence-bundle.valid.json")
    payload["warnings"] = ["W" * 512] * 32
    payload["missing_fields"] = ["M" * 512] * 32
    payload["blocker_codes"] = ["B" * 512] * 32
    _rehash_evidence(payload)
    with pytest.raises(ValidationError, match="size limit"):
        ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(payload, ensure_ascii=False)
        )


def test_evidence_bundle_requires_exact_sub_question_coverage() -> None:
    payload = _fixture("reply-evidence-bundle.valid.json")
    payload["segments"][1]["sub_question_id"] = "SUBQUESTION-001"
    payload["bundle_sha256"] = ReplyEvidenceBundleV1.model_validate_json(
        (FIXTURE_ROOT / "reply-evidence-bundle.valid.json").read_text(encoding="utf-8")
    ).bundle_sha256
    with pytest.raises(ValidationError, match="exactly once"):
        ReplyEvidenceBundleV1.model_validate_json(json.dumps(payload, ensure_ascii=False))


def test_gateway_v1_accepts_candidate_request_and_response_extensions() -> None:
    request_text = (
        FIXTURE_ROOT / "gateway-decision-request.with-reply-turn.json"
    ).read_text(encoding="utf-8")
    response_text = (
        FIXTURE_ROOT / "gateway-decision-response.with-reply-evidence.json"
    ).read_text(encoding="utf-8")
    request = DecisionRequest.model_validate_json(request_text)
    response = DecisionResponse.model_validate_json(response_text)
    assert "ai_cs_reply_turn" in request.context
    assert "reply_evidence_bundle" in response.metadata
    assert response.requires_approval is True


def test_gateway_evidence_metadata_does_not_duplicate_customer_or_source_text() -> None:
    request = _fixture("gateway-decision-request.with-reply-turn.json")
    response = _fixture("gateway-decision-response.with-reply-evidence.json")
    evidence_text = json.dumps(
        response["metadata"]["reply_evidence_bundle"], ensure_ascii=False
    )
    for customer_fragment in request["customer_message"].split("\n"):
        assert customer_fragment not in evidence_text
    assert "canonical_question" not in evidence_text
    assert "fixed_reply" not in evidence_text
