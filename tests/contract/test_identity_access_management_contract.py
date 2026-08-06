import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "identity-access-management.v1.schema.json"


def test_iam_contract_is_coordinated_0_13_0_and_valid_json_schema() -> None:
    version = json.loads((ROOT / "contracts" / "version.json").read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert version == {
        "contract_version": "0.13.0",
        "status": "coordinated",
        "updated_at": "2026-08-06",
    }
    Draft202012Validator.check_schema(schema)


def test_iam_contract_freezes_roles_permissions_and_secret_exclusion() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    definitions = schema["$defs"]

    assert definitions["RoleName"]["enum"] == [
        "ADMIN", "OPERATOR", "CUSTOMER_SERVICE"
    ]
    assert definitions["Permission"]["enum"] == [
        "workspace.access", "ai.reply", "feedback.submit", "customer_service.manage",
        "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
        "ai_quality.view", "store.view", "feedback.view", "user.manage",
    ]
    projection_fields = definitions["UserProjection"]["properties"]
    assert "password" not in projection_fields
    assert "password_hash" not in projection_fields
    assert "token_hash" not in projection_fields
    assert projection_fields["must_change_password"] == {"type": "boolean"}
    assert projection_fields["all_store_access"] == {"type": "boolean"}


def test_iam_contract_freezes_internal_initialization_and_store_selection_policy() -> None:
    definitions = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]
    assert definitions["UserCreateRequest"]["properties"]["username"]["minLength"] == 1
    assert definitions["UserCreateRequest"]["properties"]["password"]["minLength"] == 8
    assert definitions["ChangePasswordRequest"]["properties"]["new_password"]["minLength"] == 12
    assert definitions["SelfStoreBindingRequest"]["properties"]["store_ids"]["minItems"] == 1
    assert definitions["SelfStoreBindingRequest"]["properties"]["default_store_id"] == {
        "type": ["integer", "null"], "minimum": 1,
    }
    error_codes = definitions["ErrorEnvelope"]["properties"]["error"]["properties"]["code"]["enum"]
    assert "PASSWORD_CHANGE_REQUIRED" in error_codes
