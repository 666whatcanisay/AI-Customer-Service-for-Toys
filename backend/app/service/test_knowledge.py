from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.models.chat import FrozenChatContext
from app.service.vector_store import VectorStore


EXPECTED_TENANT_ID = "TENANT-PDD-SM-TEST"
EXPECTED_SCHEMA_VERSION = "V0.3.1"
ANSWER_ACTIONS = {
    "DIRECT_ANSWER",
    "CONTROLLED_ANSWER",
    "ASK_CLARIFY",
    "REQUIRE_LOOKUP",
    "TRANSFER_HUMAN",
    "REFUSE",
}
KNOWLEDGE_TYPES = {"PRODUCT_FACT", "SKU_FACT", "FAQ", "SAFETY_RULE"}
REQUIRED_KNOWLEDGE_TYPES = {
    "PRODUCT_FACT",
    "SKU_FACT",
    "FAQ",
    "SAFETY_RULE",
}
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
EXACT_SKU_DISTANCE_BONUS = 0.05


class TestKnowledgeValidationError(ValueError):
    pass


class PlatformIntegrationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TestKnowledgeItem:
    knowledge_id: str
    title: str
    content: str
    tenant_id: str
    platform: str
    store_code: str
    product_id: str
    sku_id: str
    knowledge_type: str
    answer_action: str
    risk_level: str
    source_ids: tuple[str, ...]
    package_id: str


@dataclass(frozen=True, slots=True)
class TestKnowledgePackage:
    package_id: str
    version: str
    schema_version: str
    tenant_id: str
    test_data_mode: bool
    production_usable: bool
    allow_auto_send: bool
    response_mode: str
    platform: str
    store_code: str
    items: tuple[TestKnowledgeItem, ...]


def _required_string(data: dict[str, Any], name: str) -> str:
    value = str(data.get(name) or "").strip()
    if not value:
        raise TestKnowledgeValidationError(f"missing required field: {name}")
    return value


def parse_test_knowledge_package(
    payload: dict[str, Any], expected_package_id: str | None = None
) -> TestKnowledgePackage:
    if not isinstance(payload, dict):
        raise TestKnowledgeValidationError("export payload must be an object")
    raw = payload

    package_id = _required_string(raw, "package_id")
    if expected_package_id and package_id != expected_package_id:
        raise TestKnowledgeValidationError("package_id does not match request")
    version = _required_string(raw, "version")
    schema_version = _required_string(raw, "schema_version")
    if version != EXPECTED_SCHEMA_VERSION:
        raise TestKnowledgeValidationError(
            f"version must be {EXPECTED_SCHEMA_VERSION}"
        )
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise TestKnowledgeValidationError(
            f"schema_version must be {EXPECTED_SCHEMA_VERSION}"
        )
    tenant_id = _required_string(raw, "tenant_id")
    if tenant_id != EXPECTED_TENANT_ID:
        raise TestKnowledgeValidationError(
            f"tenant_id must be {EXPECTED_TENANT_ID}"
        )
    if raw.get("test_data_mode") is not True:
        raise TestKnowledgeValidationError("test_data_mode must be true")
    if raw.get("production_usable") is not False:
        raise TestKnowledgeValidationError("production_usable must be false")
    if raw.get("allow_auto_send") is True:
        raise TestKnowledgeValidationError("allow_auto_send must not be true")
    if raw.get("allow_auto_send") is not False:
        raise TestKnowledgeValidationError("allow_auto_send must be false")
    if raw.get("response_mode") != "SUGGESTION_ONLY":
        raise TestKnowledgeValidationError(
            "response_mode must be SUGGESTION_ONLY"
        )
    if raw.get("platform") != "pdd" or raw.get("store_code") != "PDD-SM":
        raise TestKnowledgeValidationError("platform/store_code scope is invalid")

    item_payloads = raw.get("items")
    if not isinstance(item_payloads, list) or not item_payloads:
        raise TestKnowledgeValidationError("items must be a non-empty array")
    if raw.get("total") != len(item_payloads):
        raise TestKnowledgeValidationError("total must equal items length")

    items: list[TestKnowledgeItem] = []
    for item_payload in item_payloads:
        if not isinstance(item_payload, dict):
            raise TestKnowledgeValidationError("each item must be an object")
        if item_payload.get("allow_auto_send") is True:
            raise TestKnowledgeValidationError(
                "item allow_auto_send must not be true"
            )
        item_tenant = str(item_payload.get("tenant_id") or tenant_id).strip()
        if item_tenant != EXPECTED_TENANT_ID:
            raise TestKnowledgeValidationError("item tenant_id is invalid")
        if item_payload.get("test_data_mode") is not True:
            raise TestKnowledgeValidationError("item test_data_mode must be true")
        if item_payload.get("production_usable") is not False:
            raise TestKnowledgeValidationError(
                "item production_usable must be false"
            )
        if item_payload.get("platform") != "pdd":
            raise TestKnowledgeValidationError("item platform must be pdd")
        if item_payload.get("store_code") != "PDD-SM":
            raise TestKnowledgeValidationError("item store_code must be PDD-SM")

        knowledge_type = _required_string(item_payload, "knowledge_type")
        if knowledge_type not in KNOWLEDGE_TYPES:
            raise TestKnowledgeValidationError(
                f"unsupported knowledge_type: {knowledge_type}"
            )
        answer_action = _required_string(item_payload, "answer_action")
        if answer_action not in ANSWER_ACTIONS:
            raise TestKnowledgeValidationError(
                f"unsupported answer_action: {answer_action}"
            )
        risk_level = _required_string(item_payload, "risk_level")
        if risk_level not in RISK_LEVELS:
            raise TestKnowledgeValidationError(
                f"unsupported risk_level: {risk_level}"
            )
        source_ids = item_payload.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise TestKnowledgeValidationError("source_ids must be non-empty")
        if any(not isinstance(value, str) or not value.strip() for value in source_ids):
            raise TestKnowledgeValidationError(
                "source_ids must contain non-empty strings"
            )

        content = str(item_payload.get("content") or "").strip()
        if not content:
            raise TestKnowledgeValidationError("item content is required")

        items.append(
            TestKnowledgeItem(
                knowledge_id=str(item_payload.get("knowledge_id") or "").strip(),
                title=_required_string(item_payload, "title"),
                content=content,
                tenant_id=item_tenant,
                platform=_required_string(item_payload, "platform"),
                store_code=_required_string(item_payload, "store_code"),
                product_id=_required_string(item_payload, "product_id"),
                sku_id=str(item_payload.get("sku_id") or "").strip(),
                knowledge_type=knowledge_type,
                answer_action=answer_action,
                risk_level=risk_level,
                source_ids=tuple(str(value) for value in source_ids),
                package_id=package_id,
            )
        )
        if not items[-1].knowledge_id:
            raise TestKnowledgeValidationError("knowledge_id is required")

    missing_types = REQUIRED_KNOWLEDGE_TYPES - {
        item.knowledge_type for item in items
    }
    if missing_types:
        raise TestKnowledgeValidationError(
            "package missing required knowledge types: "
            + ", ".join(sorted(missing_types))
        )

    return TestKnowledgePackage(
        package_id=package_id,
        version=version,
        schema_version=schema_version,
        tenant_id=tenant_id,
        test_data_mode=True,
        production_usable=False,
        allow_auto_send=bool(raw.get("allow_auto_send", False)),
        response_mode="SUGGESTION_ONLY",
        platform="pdd",
        store_code="PDD-SM",
        items=tuple(items),
    )


class PlatformTestKnowledgeClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _get_json(self, path: str) -> dict[str, Any]:
        if not self.base_url:
            raise PlatformIntegrationUnavailable(
                "PLATFORM_API_BASE_URL is not configured"
            )
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PlatformIntegrationUnavailable(
                "C platform test-knowledge API is unavailable"
            ) from exc

    def fetch_package(self, package_id: str) -> TestKnowledgePackage:
        escaped = urllib.parse.quote(package_id, safe="")
        payload = self._get_json(
            f"/api/v1/test-knowledge-packages/{escaped}/rag-export"
        )
        return parse_test_knowledge_package(payload, expected_package_id=package_id)

    def fetch_evaluations(self, package_id: str) -> dict[str, Any]:
        escaped = urllib.parse.quote(package_id, safe="")
        return self._get_json(
            f"/api/v1/test-knowledge-packages/{escaped}/evaluations"
        )


class TestKnowledgeIndex:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def sync(self, package: TestKnowledgePackage) -> dict[str, Any]:
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        for item in package.items:
            record_id = hashlib.sha256(
                f"{package.schema_version}\n{item.package_id}\n"
                f"{item.knowledge_id}\n{item.content}".encode("utf-8")
            ).hexdigest()
            documents.append(item.content)
            ids.append(record_id)
            metadatas.append(
                {
                    "file": f"test-package:{item.package_id}",
                    "page": 0,
                    "chunk_id": record_id,
                    "tenant_id": item.tenant_id,
                    "platform": item.platform,
                    "store_code": item.store_code,
                    "product_id": item.product_id,
                    "sku_id": item.sku_id,
                    "knowledge_type": item.knowledge_type,
                    "answer_action": item.answer_action,
                    "risk_level": item.risk_level,
                    "source_ids": json.dumps(
                        item.source_ids, ensure_ascii=False, separators=(",", ":")
                    ),
                    "package_id": item.package_id,
                    "knowledge_version": package.version,
                    "schema_version": package.schema_version,
                    "test_data_mode": "true",
                    "production_usable": "false",
                }
            )
        self.vector_store.upsert_records(documents, metadatas, ids)
        return {
            "package_id": package.package_id,
            "schema_version": package.schema_version,
            "synced_items": len(documents),
            "collection_name": self.vector_store.collection_name,
            "collection_count": self.vector_store.collection.count(),
            "test_data_mode": True,
            "production_usable": False,
        }

    @staticmethod
    def _where(context: FrozenChatContext, sku_id: str) -> dict[str, Any]:
        return {
            "$and": [
                {"tenant_id": {"$eq": context.tenant_id}},
                {"platform": {"$eq": context.platform}},
                {"store_code": {"$eq": context.store_code}},
                {"product_id": {"$eq": context.product_id}},
                {"sku_id": {"$eq": sku_id}},
                {"test_data_mode": {"$eq": "true"}},
                {"production_usable": {"$eq": "false"}},
            ]
        }

    def search(
        self, query: str, context: FrozenChatContext, top_k: int
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        scope_skus = [context.sku_id, ""] if context.sku_id else [""]
        for scope_rank, sku_id in enumerate(scope_skus):
            scoped = self.vector_store.search(
                query,
                top_k=top_k,
                where=self._where(context, sku_id or ""),
            )
            for result in scoped:
                if result["chunk_id"] in seen:
                    continue
                seen.add(result["chunk_id"])
                metadata = result.get("metadata", {})
                result.update(
                    {
                        "tenant_id": metadata.get("tenant_id", ""),
                        "platform": metadata.get("platform", ""),
                        "store_code": metadata.get("store_code", ""),
                        "product_id": metadata.get("product_id", ""),
                        "sku_id": metadata.get("sku_id", ""),
                        "knowledge_type": metadata.get("knowledge_type", ""),
                        "answer_action": metadata.get("answer_action", "REFUSE"),
                        "risk_level": metadata.get("risk_level", "HIGH"),
                        "source_ids": json.loads(metadata.get("source_ids", "[]")),
                        "package_id": metadata.get("package_id", ""),
                        "knowledge_version": metadata.get(
                            "knowledge_version", EXPECTED_SCHEMA_VERSION
                        ),
                        "_scope_rank": scope_rank,
                    }
                )
                results.append(result)
        results.sort(
            key=lambda item: float(item["distance"])
            - (EXACT_SKU_DISTANCE_BONUS if item["_scope_rank"] == 0 and context.sku_id else 0)
        )
        return results[:top_k]
