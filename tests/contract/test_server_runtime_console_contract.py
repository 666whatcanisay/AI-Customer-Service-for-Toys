import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts" / "schemas" / "ai-cs-server-runtime-console.v1.schema.json"


def test_server_runtime_console_contract_is_strict_additive_projection() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    definitions = schema["$defs"]

    assert schema["$id"] == "urn:ai-cs:server-runtime-console:v1"
    assert schema["properties"]["schema_version"]["const"] == (
        "ai-cs.server-runtime-console.v1"
    )
    assert schema["additionalProperties"] is False
    assert definitions["ServerRuntimeSummary"]["additionalProperties"] is False
    assert definitions["GatewayRuntimeSummary"]["additionalProperties"] is False
    network_mode = definitions["ServerRuntimeSummary"]["properties"]["network_mode"]
    assert network_mode["enum"] == ["LOCAL", "LAN"]
    assert network_mode["default"] == "LOCAL"
    assert "network_mode" not in definitions["ServerRuntimeSummary"]["required"]
    gateway = definitions["GatewayRuntimeSummary"]["properties"]
    assert gateway["contract_version"]["const"] == "1.0"
    assert gateway["version"]["const"] == "ai-cs-gateway.v1"
    serialized = json.dumps(schema).lower()
    for forbidden in ("secret", "state_path", "client_id", "nonce", "request_id"):
        assert forbidden not in serialized
