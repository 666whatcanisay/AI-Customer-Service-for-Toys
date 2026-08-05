import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"
PRODUCTION_V1_SCHEMA_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)


def test_gateway_server_phase1_schema_is_strict_and_versioned() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    request = definitions["DecisionRequest"]
    response = definitions["DecisionResponse"]
    error = definitions["ErrorEnvelope"]
    health = definitions["GatewayHealth"]

    assert schema["$id"] == "urn:ai-cs:channel-engine:gateway-contract:v1"
    assert request["properties"]["contract_version"]["const"] == "1.0"
    assert request["additionalProperties"] is False
    assert {
        "request_id",
        "idempotency_key",
        "correlation_id",
        "conversation_id",
        "message_id",
        "customer_message",
        "requested_at",
    }.issubset(request["required"])
    assert "context" in request["properties"]
    assert response["properties"]["requires_approval"]["const"] is True
    assert response["properties"]["action"]["$ref"].endswith("DecisionAction")
    assert response["properties"]["risk_level"]["$ref"].endswith(
        "GatewayRiskLevel"
    )
    assert "risk_level" in response["required"]
    assert error["additionalProperties"] is False
    assert health["properties"]["contract_version"]["const"] == "1.0"
    assert {"status", "version", "capabilities", "timestamp"}.issubset(
        health["required"]
    )
    assert "error_code" in definitions["GatewayError"]["required"]
    assert "code" not in definitions["GatewayError"]["properties"]
    canonical = json.dumps(
        schema, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == PRODUCTION_V1_SCHEMA_SHA256
