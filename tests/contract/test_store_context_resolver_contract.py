import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "store-context-resolver.v1.schema.json"
GATEWAY_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"


def test_store_context_v1_schema_is_valid_and_gateway_schema_is_unchanged() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert hashlib.sha256(GATEWAY_SCHEMA_PATH.read_bytes()).hexdigest() == (
        "fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80"
    )


def test_store_context_contract_has_required_resolution_states_and_no_raw_text_audit() -> None:
    definitions = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]
    assert definitions["ResolutionStatus"]["enum"] == [
        "RESOLVED", "STORE_SELECTION_REQUIRED", "PRODUCT_CONFIRMATION_REQUIRED",
        "SKU_CONFIRMATION_REQUIRED", "UNKNOWN",
    ]
    audit_fields = definitions["ResolutionAudit"]["properties"]
    assert "conversation" not in audit_fields
    assert "conversation_hash" not in audit_fields
    assert "message" not in audit_fields
    assert "answer" not in audit_fields
