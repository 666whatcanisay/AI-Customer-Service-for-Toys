import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "customer-desktop-workflow.v1.schema.json"
GATEWAY_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"


def test_customer_desktop_workflow_schema_and_version_are_coordinated() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    version = json.loads((ROOT / "contracts" / "version.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert version == {
        "contract_version": "0.13.0",
        "status": "coordinated",
        "updated_at": "2026-08-06",
    }
    assert hashlib.sha256(GATEWAY_SCHEMA_PATH.read_bytes()).hexdigest() == (
        "fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80"
    )


def test_device_projection_and_audit_exclude_secrets_and_customer_content() -> None:
    definitions = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]
    projected = definitions["DesktopAgent"]["properties"]
    audit = definitions["AuditEvent"]["properties"]
    for forbidden in (
        "password", "password_hash", "session_token", "token", "operator_session_reference",
        "binding_code", "customer_message", "conversation", "ai_answer", "knowledge_content",
    ):
        assert forbidden not in projected
        assert forbidden not in audit
    assert definitions["AssociationState"]["enum"] == [
        "READY", "BINDING_REQUIRED", "ACTIVATION_REQUIRED", "STORE_MISMATCH",
        "MULTIPLE_MATCHES", "DISABLED",
    ]


def test_binding_grant_remains_narrow_and_activation_is_not_exposed() -> None:
    definitions = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]
    request = definitions["BindingGrantRequest"]
    assert request["required"] == ["agent_id", "device_id", "store_id"]
    assert "user_id" not in request["properties"]
    assert "store_references" not in request["properties"]
    assert "activate" not in request["properties"]
