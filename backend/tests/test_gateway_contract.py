from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.gateway.auth import canonical_signing_text
from app.gateway.contract import (
    DecisionRequest,
    DecisionResponse,
    ErrorEnvelope,
    GatewayHealth,
    gateway_contract_schema,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (
    ROOT
    / "contracts"
    / "schemas"
    / "channel-engine-gateway-server.v1.schema.json"
)


def test_checked_in_gateway_schema_matches_runtime_models() -> None:
    checked_in = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert checked_in == gateway_contract_schema()
    assert set(checked_in["$defs"]) >= {
        "DecisionRequest",
        "DecisionResponse",
        "ErrorEnvelope",
        "GatewayHealth",
    }
    assert checked_in["$defs"]["DecisionRequest"]["additionalProperties"] is False
    assert (
        checked_in["$defs"]["DecisionResponse"]["properties"]["requires_approval"][
            "const"
        ]
        is True
    )
    assert "risk_level" in checked_in["$defs"]["DecisionResponse"]["required"]
    assert {"status", "version", "capabilities", "timestamp"}.issubset(
        checked_in["$defs"]["GatewayHealth"]["required"]
    )
    assert "error_code" in checked_in["$defs"]["GatewayError"]["required"]


def test_production_v1_hmac_known_vector() -> None:
    body = b'{"contract_version":"1.0"}'
    content_sha256 = hashlib.sha256(body).hexdigest()
    signing_text = canonical_signing_text(
        method="POST",
        path="/gateway/v1/decisions",
        contract_version="1.0",
        client_id="agent-01",
        key_id="key-01",
        timestamp="2026-08-05T00:00:00Z",
        nonce="bm9uY2UtZm9yLXRlc3QtMDAx",
        request_id="req-001",
        correlation_id="corr-001",
        idempotency_key="idem-001",
        content_sha256=content_sha256,
    )
    signature = base64.urlsafe_b64encode(
        hmac.new(
            b"0123456789abcdef0123456789abcdef",
            signing_text,
            hashlib.sha256,
        ).digest()
    ).decode("ascii").rstrip("=")

    assert content_sha256 == (
        "84786626e94027a1c329b242d5c4c35eb285e80bd77cebb15c81fdb729c03227"
    )
    assert signature == "FYWXv1salDMEWFLncJVmokCssvS0fdTEbhyxOAuC9uc"


@pytest.mark.parametrize(
    "model",
    [DecisionRequest, DecisionResponse, ErrorEnvelope, GatewayHealth],
)
def test_gateway_models_are_strict_and_forbid_unknown_fields(model) -> None:
    assert model.model_config["strict"] is True
    assert model.model_config["extra"] == "forbid"


def test_gateway_decision_request_rejects_legacy_aliases() -> None:
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(
            {
                "schema_version": "1.0",
                "request_id": "request-1",
                "idempotency_key": "key-1",
                "correlation_id": "correlation-1",
                "conversation_id": "conversation-1",
                "message_id": "message-1",
                "message": "legacy alias is forbidden",
                "requested_at": "2026-08-04T02:00:00Z",
            }
        )
