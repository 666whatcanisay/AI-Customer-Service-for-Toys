from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.knowledge_publication import (
    AiKnowledgePublicationStatus,
    ProductKnowledgePublishReceipt,
    ProductKnowledgePublishRequest,
    ProductKnowledgeVisibility,
    ProductKnowledgeVisibilityRequest,
)
from app.service.vector_store import VectorStore

_NON_FACT_PRODUCT_FIELDS = {
    "common_customer_questions",
    "recommended_answer_direction",
}
_ANSWER_ACTIONS = {
    "DIRECT_ANSWER",
    "CONTROLLED_ANSWER",
    "ASK_CLARIFY",
    "REQUIRE_LOOKUP",
    "TRANSFER_HUMAN",
    "REFUSE",
}
_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}


def _structured_units(document: str) -> list[dict[str, str]] | None:
    """Project every governed canonical section into independently scoped facts."""

    try:
        payload = json.loads(document)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "c-product-knowledge-document.v1"
    ):
        return None
    controls = payload.get("reviewed_answer_controls") or {}
    product = payload.get("product")
    if not isinstance(controls, dict) or not isinstance(product, dict):
        return None

    units: list[dict[str, str]] = []

    def add_unit(
        *,
        content: str,
        knowledge_type: str,
        sku_id: str = "",
        answer_action: str = "DIRECT_ANSWER",
        risk_level: str = "LOW",
        controlled_answer_kind: str = "",
    ) -> None:
        content = content.strip()
        if not content:
            return
        units.append(
            {
                "content": content,
                "knowledge_type": knowledge_type,
                "sku_id": sku_id.strip(),
                "answer_action": (
                    answer_action if answer_action in _ANSWER_ACTIONS else "CONTROLLED_ANSWER"
                ),
                "risk_level": risk_level if risk_level in _RISK_LEVELS else "MEDIUM",
                "controlled_answer_kind": controlled_answer_kind,
            }
        )

    for field_name, value in product.items():
        if field_name in _NON_FACT_PRODUCT_FIELDS or value in (None, "", []):
            continue
        serialized_value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        control = controls.get(field_name)
        controlled_kind = (
            control.get("controlled_answer_kind") if isinstance(control, dict) else None
        )
        is_reviewed_approximate = controlled_kind == "REVIEWED_APPROXIMATE_FACT"
        add_unit(
            content=f"{field_name}: {serialized_value}",
            knowledge_type="PRODUCT_FACT",
            answer_action=(
                "CONTROLLED_ANSWER" if is_reviewed_approximate else "DIRECT_ANSWER"
            ),
            risk_level="MEDIUM" if is_reviewed_approximate else "LOW",
            controlled_answer_kind=controlled_kind or "",
        )

    skus = payload.get("skus") or []
    if not isinstance(skus, list):
        return None
    for sku in skus:
        if not isinstance(sku, dict):
            return None
        sku_id = str(sku.get("sku_id") or "").strip()
        if not sku_id:
            continue
        for field_name, value in sku.items():
            if field_name == "sku_id" or value in (None, "", []):
                continue
            add_unit(
                content=(
                    f"sku_id: {sku_id}\n{field_name}: "
                    f"{json.dumps(value, ensure_ascii=False, sort_keys=True)}"
                ),
                knowledge_type="SKU_FACT",
                sku_id=sku_id,
            )

    faqs = payload.get("faqs") or []
    if not isinstance(faqs, list):
        return None
    for faq in faqs:
        if not isinstance(faq, dict):
            return None
        question = str(faq.get("question") or "").strip()
        reply = str(faq.get("recommended_reply") or "").strip()
        if not question or not reply:
            continue
        add_unit(
            content=f"question: {question}\nrecommended_reply: {reply}",
            knowledge_type="FAQ",
            sku_id=str(faq.get("sku_id") or ""),
            answer_action=str(faq.get("answer_action") or "CONTROLLED_ANSWER"),
            risk_level=str(faq.get("risk_level") or "MEDIUM"),
        )

    safety_rules = payload.get("safety_rules") or []
    if not isinstance(safety_rules, list):
        return None
    for rule in safety_rules:
        if not isinstance(rule, dict):
            return None
        scenario = str(rule.get("scenario") or "").strip()
        content = rule.get("content")
        if not scenario or not isinstance(content, dict):
            continue
        allowed_action = str(content.get("allowed_action") or "CONTROLLED_ANSWER")
        add_unit(
            content=(
                f"scenario: {scenario}\npolicy: "
                f"{json.dumps(content, ensure_ascii=False, sort_keys=True)}"
            ),
            knowledge_type="SAFETY_RULE",
            answer_action=allowed_action,
            risk_level=str(rule.get("risk_level") or "HIGH"),
        )
    return units or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _where(scope: ProductKnowledgeVisibilityRequest | ProductKnowledgePublishRequest):
    return {
        "$and": [
            {"tenant_id": {"$eq": scope.tenant_id}},
            {"platform": {"$eq": scope.platform}},
            {"store_code": {"$eq": scope.store_code}},
            {"product_id": {"$eq": scope.product_id}},
        ]
    }


class ProductKnowledgePublisher:
    """Incrementally publish one C-approved product document.

    New records are embedded and verified before old versions for the same
    product are removed.  A never decides whether the product is customer
    available; it only indexes the supplied scope.
    """

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def publish(
        self, request: ProductKnowledgePublishRequest
    ) -> ProductKnowledgePublishReceipt:
        structured_units = _structured_units(request.document)
        chunks = (
            [unit["content"] for unit in structured_units]
            if structured_units is not None
            else self.vector_store.chunk_text(request.document)
        )
        if not chunks:
            raise ValueError("商品知识文档没有可发布内容")

        receipt_id = (
            "RAG-"
            + hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()[:32]
        )
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str | int]] = []
        published_at = _now()
        source_ids = json.dumps(
            request.source_ids, ensure_ascii=False, separators=(",", ":")
        )
        for index, chunk in enumerate(chunks):
            unit = structured_units[index] if structured_units is not None else None
            chunk_id = hashlib.sha256(
                f"{request.product_id}\n{request.knowledge_fingerprint}\n{index}\n{chunk}".encode()
            ).hexdigest()
            ids.append(chunk_id)
            documents.append(f"{request.product_name}\n{chunk}")
            metadata: dict[str, str | int] = {
                "file": f"product-knowledge:{request.product_id}",
                "page": index,
                "chunk_id": chunk_id,
                "tenant_id": request.tenant_id,
                "platform": request.platform,
                "store_code": request.store_code,
                "product_id": request.product_id,
                "sku_id": unit["sku_id"] if unit else "",
                "knowledge_type": unit["knowledge_type"] if unit else "PRODUCT_FACT",
                "knowledge_id": f"PRODUCT-KNOWLEDGE-{request.product_id}-{index}",
                "title": request.product_name,
                "content": chunk,
                "answer_action": unit["answer_action"] if unit else "DIRECT_ANSWER",
                "risk_level": unit["risk_level"] if unit else "LOW",
                "source_ids": source_ids,
                "package_id": "C-PRODUCT-KNOWLEDGE",
                "knowledge_version": request.knowledge_fingerprint,
                "schema_version": request.schema_version,
                "data_source": request.data_source,
                "knowledge_fingerprint": request.knowledge_fingerprint,
                "publication_receipt_id": receipt_id,
                "published_at": published_at.isoformat(),
            }
            if unit and unit["controlled_answer_kind"]:
                metadata["controlled_answer_kind"] = unit["controlled_answer_kind"]
            metadatas.append(metadata)

        existing = self.vector_store.get_records(_where(request))
        old_ids = [
            record_id for record_id in existing.get("ids", []) if record_id not in ids
        ]

        self.vector_store.upsert_records(documents, metadatas, ids)
        verified = self.vector_store.get_records(
            _where(request), include_embeddings=True
        )
        verified_metadata = verified.get("metadatas") or []
        embeddings = verified.get("embeddings")
        new_indexes = [
            index
            for index, metadata in enumerate(verified_metadata)
            if metadata.get("knowledge_fingerprint") == request.knowledge_fingerprint
        ]
        embedded_indexes = (
            [index for index in new_indexes if embeddings[index] is not None]
            if embeddings is not None
            else []
        )
        if len(new_indexes) != len(ids) or len(embedded_indexes) != len(ids):
            raise RuntimeError("商品知识向量写入校验失败；旧版本已保留")

        self.vector_store.delete_records(old_ids)
        return ProductKnowledgePublishReceipt(
            publication_receipt_id=receipt_id,
            product_id=request.product_id,
            active_collection=self.vector_store.collection_name,
            knowledge_fingerprint=request.knowledge_fingerprint,
            chunk_count=len(ids),
            embedding_count=len(embedded_indexes),
            published_at=published_at,
        )

    def visibility(
        self, request: ProductKnowledgeVisibilityRequest
    ) -> ProductKnowledgeVisibility:
        records = self.vector_store.get_records(
            _where(request), include_embeddings=True
        )
        metadatas = records.get("metadatas") or []
        embeddings = records.get("embeddings")
        chunk_count = len(records.get("ids") or [])
        embedding_count = (
            sum(embedding is not None for embedding in embeddings)
            if embeddings is not None
            else 0
        )
        fingerprints = [
            str(metadata.get("knowledge_fingerprint") or "")
            for metadata in metadatas
            if metadata.get("knowledge_fingerprint")
        ]
        indexed_fingerprint = fingerprints[0] if len(set(fingerprints)) == 1 else None
        published_times = [
            str(metadata.get("published_at") or "")
            for metadata in metadatas
            if metadata.get("published_at")
        ]
        updated_at = None
        if published_times:
            try:
                updated_at = datetime.fromisoformat(max(published_times))
            except ValueError:
                updated_at = None

        if chunk_count == 0:
            status = AiKnowledgePublicationStatus.NOT_GENERATED
        elif embedding_count != chunk_count or indexed_fingerprint is None:
            status = AiKnowledgePublicationStatus.SYNC_FAILED
        elif (
            request.current_fingerprint
            and indexed_fingerprint != request.current_fingerprint
        ):
            status = AiKnowledgePublicationStatus.NEED_RESYNC
        else:
            status = AiKnowledgePublicationStatus.PUBLISHED
        return ProductKnowledgeVisibility(
            product_id=request.product_id,
            status=status,
            active_collection=self.vector_store.collection_name,
            chunk_count=chunk_count,
            embedding_count=embedding_count,
            indexed_fingerprint=indexed_fingerprint,
            current_fingerprint=request.current_fingerprint,
            updated_at=updated_at,
        )
