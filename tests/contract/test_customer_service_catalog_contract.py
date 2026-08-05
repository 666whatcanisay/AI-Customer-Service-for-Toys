import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_contract_version_and_all_customer_catalog_schemas_are_json() -> None:
    version = json.loads((ROOT / "contracts" / "version.json").read_text(encoding="utf-8"))
    assert version["contract_version"] == "0.7.0"
    for name in (
        "customer-service-catalog.v1.schema.json",
        "customer-service-catalog-activation-request.v1.schema.json",
        "customer-service-catalog-activation-response.v1.schema.json",
        "customer-service-catalog-activation-receipt.v1.schema.json",
        "customer-service-catalog-batch-activation.v1.schema.json",
        "ai-product-knowledge-publication.v1.schema.json",
        "ai-product-knowledge-visibility.v1.schema.json",
        "customer-product-ai-knowledge-status.v1.schema.json",
    ):
        schema = _load(name)
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["additionalProperties"] is False


def test_customer_ai_knowledge_status_freezes_receipt_and_chunk_evidence() -> None:
    schema = _load("customer-product-ai-knowledge-status.v1.schema.json")
    assert schema["properties"]["schema_version"]["const"] == (
        "customer-product-ai-knowledge-status.v1"
    )
    assert schema["properties"]["status"]["enum"] == [
        "NOT_GENERATED", "GENERATING", "PUBLISHED", "SYNC_FAILED", "NEED_RESYNC"
    ]
    assert {
        "publication_receipt_id", "chunk_count", "embedding_count"
    }.issubset(schema["required"])

    publication = _load("ai-product-knowledge-publication.v1.schema.json")
    assert publication["$defs"]["request"]["properties"]["data_source"]["enum"] == [
        "TEST", "INITIAL_IMPORT", "PILOT"
    ]


def test_catalog_schema_requires_final_projection_envelope_and_enabled_items() -> None:
    schema = _load("customer-service-catalog.v1.schema.json")
    assert set(schema["required"]) == {
        "schema_version", "result_status", "items", "total", "warnings"
    }
    assert schema["properties"]["schema_version"]["const"] == (
        "pilot-business-catalog.v1.1"
    )
    assert schema["$defs"]["enabledStatus"] == {"const": "ENABLED"}
    assert schema["$defs"]["dataSource"]["enum"] == [
        "TEST", "INITIAL_IMPORT", "PILOT"
    ]
    for entity in ("store", "product", "sku"):
        properties = schema["$defs"][entity]["properties"]
        assert "customer_service_status" in properties
        assert "test_data_mode" not in properties
        assert "production_usable" not in properties
        assert "publishable" not in properties


def test_activation_contract_freezes_manual_control_and_receipt_boundaries() -> None:
    request = _load("customer-service-catalog-activation-request.v1.schema.json")
    receipt = _load("customer-service-catalog-activation-receipt.v1.schema.json")
    response = _load("customer-service-catalog-activation-response.v1.schema.json")

    assert request["properties"]["customer_service_status"]["enum"] == [
        "ENABLED", "DISABLED"
    ]
    assert set(request["required"]) == {
        "customer_service_status", "confirmed_by", "confirmation_note"
    }
    assert receipt["properties"]["entity_type"]["enum"] == ["STORE", "PRODUCT"]
    assert receipt["properties"]["activation_source"]["enum"] == [
        "LEGACY_INITIALIZATION", "OPERATOR"
    ]
    assert receipt["properties"]["data_source"]["enum"] == [
        "TEST", "INITIAL_IMPORT", "PILOT"
    ]
    assert response["$defs"]["entity"]["properties"]["data_source"]["enum"] == [
        "TEST", "INITIAL_IMPORT", "PILOT"
    ]
    assert "SKU" not in receipt["properties"]["entity_type"]["enum"]
    assert "activation_receipt" in response["required"]


def test_020_contract_assets_remain_present() -> None:
    for name in (
        "ai-interaction-event-create.v1.schema.json",
        "ai-interaction-event-receipt.v1.schema.json",
        "assistant-request.schema.json",
        "assistant-response.schema.json",
        "feedback.schema.json",
        "knowledge-publish.schema.json",
    ):
        assert (SCHEMAS / name).is_file()
