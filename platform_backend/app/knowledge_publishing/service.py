from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.knowledge_publishing.ai_client import (
    AiKnowledgePublicationClient,
    AiKnowledgePublicationUnavailable,
)
from app.knowledge_publishing.canonical import build_canonical_product_knowledge
from app.knowledge_publishing.models import (
    ProductKnowledgePublication,
    ProductKnowledgePublicationIdempotency,
    ProductKnowledgePublicationReceipt,
)
from app.knowledge_publishing.projection import publication_summary
from app.knowledge_publishing.schemas import (
    AiKnowledgeStatus,
    AiKnowledgeSummary,
    EmbeddingStatus,
    ProductKnowledgeCheckCommand,
    ProductKnowledgePublicationReceiptList,
    ProductKnowledgePublicationReceiptSchema,
    ProductKnowledgePublicationResponse,
    ProductKnowledgePublishCommand,
)
from app.product_knowledge.service import ProductKnowledgeService
from app.test_catalog.models import TestProduct


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProductKnowledgePublishingService:
    def __init__(
        self,
        session: Session,
        ai_client: AiKnowledgePublicationClient | None = None,
    ) -> None:
        self.session = session
        self.ai_client = ai_client or AiKnowledgePublicationClient()

    def summary(self, product: TestProduct) -> AiKnowledgeSummary:
        return publication_summary(self.session, product)

    def publish(
        self,
        product_id: str,
        command: ProductKnowledgePublishCommand,
        idempotency_key: str | None,
    ) -> tuple[ProductKnowledgePublicationResponse, bool]:
        key = self._require_key(idempotency_key)
        fingerprint = self._request_fingerprint(product_id, command)
        replay = self.session.get(ProductKnowledgePublicationIdempotency, key)
        if replay is not None:
            if replay.request_fingerprint != fingerprint:
                raise AppError(
                    "AI_KNOWLEDGE_IDEMPOTENCY_CONFLICT",
                    "Idempotency-Key 已用于其他AI知识发布请求",
                    status_code=409,
                )
            return ProductKnowledgePublicationResponse.model_validate_json(
                replay.response_json
            ), True

        product = self.session.get(TestProduct, product_id)
        if product is None:
            raise AppError("AI_KNOWLEDGE_PRODUCT_NOT_FOUND", "未找到商品", status_code=404)
        detail = ProductKnowledgeService(self.session).detail(product_id)
        if detail is None or detail.data_status != "APPROVED":
            raise AppError(
                "AI_KNOWLEDGE_NOT_APPROVED",
                "只有已审核通过的商品知识可以发布",
                status_code=409,
            )
        canonical = build_canonical_product_knowledge(self.session, product)
        if canonical.data_source not in {"TEST", "INITIAL_IMPORT", "PILOT"}:
            raise AppError(
                "AI_KNOWLEDGE_SOURCE_UNCONFIRMED",
                "商品数据来源尚未确认，不能发布AI知识",
                status_code=409,
            )
        row = self.session.get(ProductKnowledgePublication, product_id)
        if (
            row is not None
            and row.status == AiKnowledgeStatus.PUBLISHED
            and row.indexed_fingerprint == canonical.fingerprint
            and row.chunk_count > 0
            and row.embedding_count == row.chunk_count
        ):
            response = ProductKnowledgePublicationResponse(
                changed=False,
                product_id=product_id,
                ai_knowledge=self._summary(
                    row,
                    status=AiKnowledgeStatus.PUBLISHED,
                    current_fingerprint=canonical.fingerprint,
                ),
            )
            self._save_idempotency(key, fingerprint, response)
            self.session.commit()
            return response, False

        now = _now()
        if row is None:
            row = ProductKnowledgePublication(
                product_id=product_id,
                status=AiKnowledgeStatus.GENERATING,
                current_fingerprint=canonical.fingerprint,
                chunk_count=0,
                embedding_count=0,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.status = AiKnowledgeStatus.GENERATING
            row.current_fingerprint = canonical.fingerprint
            row.last_error_code = None
            row.updated_at = now
        self.session.commit()

        try:
            result = self.ai_client.publish(
                {
                    "schema_version": "ai-product-knowledge-publication.v1",
                    "idempotency_key": key,
                    "tenant_id": canonical.tenant_id,
                    "platform": canonical.platform,
                    "store_code": canonical.store_code,
                    "product_id": canonical.product_id,
                    "product_name": canonical.product_name,
                    "data_source": canonical.data_source,
                    "knowledge_fingerprint": canonical.fingerprint,
                    "document": canonical.document,
                    "source_ids": list(canonical.source_ids),
                    "operator": command.operator,
                }
            )
            if (
                result.get("status") != "PUBLISHED"
                or result.get("knowledge_fingerprint") != canonical.fingerprint
                or int(result.get("chunk_count") or 0) < 1
                or int(result.get("embedding_count") or 0)
                != int(result.get("chunk_count") or 0)
            ):
                raise AiKnowledgePublicationUnavailable("A发布收据校验失败")
        except (AiKnowledgePublicationUnavailable, ValueError, TypeError) as exc:
            row = self.session.get(ProductKnowledgePublication, product_id)
            assert row is not None
            row.status = AiKnowledgeStatus.SYNC_FAILED
            row.current_fingerprint = canonical.fingerprint
            row.last_error_code = "AI_KNOWLEDGE_PUBLISH_FAILED"
            row.checked_at = _now()
            row.updated_at = row.checked_at
            self.session.commit()
            raise AppError(
                "AI_KNOWLEDGE_PUBLISH_FAILED",
                "AI知识同步失败，旧版本知识已保留，请稍后重试",
                status_code=502,
            ) from exc

        receipt = ProductKnowledgePublicationReceipt(
            publication_receipt_id=str(result["publication_receipt_id"]),
            product_id=product_id,
            knowledge_fingerprint=canonical.fingerprint,
            active_collection=str(result["active_collection"]),
            chunk_count=int(result["chunk_count"]),
            embedding_count=int(result["embedding_count"]),
            status=AiKnowledgeStatus.PUBLISHED,
            operator=command.operator,
            created_at=datetime.fromisoformat(str(result["published_at"])),
        )
        existing_receipt = self.session.get(
            ProductKnowledgePublicationReceipt, receipt.publication_receipt_id
        )
        if existing_receipt is None:
            self.session.add(receipt)
        row = self.session.get(ProductKnowledgePublication, product_id)
        assert row is not None
        row.status = AiKnowledgeStatus.PUBLISHED
        row.current_fingerprint = canonical.fingerprint
        row.indexed_fingerprint = canonical.fingerprint
        row.active_collection = receipt.active_collection
        row.chunk_count = receipt.chunk_count
        row.embedding_count = receipt.embedding_count
        row.last_error_code = None
        row.publication_receipt_id = receipt.publication_receipt_id
        row.published_at = receipt.created_at
        row.checked_at = receipt.created_at
        row.updated_at = _now()
        response = ProductKnowledgePublicationResponse(
            changed=True,
            product_id=product_id,
            ai_knowledge=self._summary(
                row,
                status=AiKnowledgeStatus.PUBLISHED,
                current_fingerprint=canonical.fingerprint,
            ),
            publication_receipt=self._receipt(receipt),
        )
        self._save_idempotency(key, fingerprint, response)
        self.session.commit()
        return response, False

    def check(
        self, product_id: str, command: ProductKnowledgeCheckCommand
    ) -> ProductKnowledgePublicationResponse:
        del command
        product = self.session.get(TestProduct, product_id)
        if product is None:
            raise AppError("AI_KNOWLEDGE_PRODUCT_NOT_FOUND", "未找到商品", status_code=404)
        canonical = build_canonical_product_knowledge(self.session, product)
        try:
            payload = self.ai_client.visibility(
                {
                    "items": [
                        {
                            "tenant_id": canonical.tenant_id,
                            "platform": canonical.platform,
                            "store_code": canonical.store_code,
                            "product_id": canonical.product_id,
                            "current_fingerprint": canonical.fingerprint,
                        }
                    ]
                }
            )
            evidence = payload["items"][0]
            status = AiKnowledgeStatus(str(evidence["status"]))
        except (AiKnowledgePublicationUnavailable, KeyError, IndexError, ValueError) as exc:
            raise AppError(
                "AI_KNOWLEDGE_VISIBILITY_UNAVAILABLE",
                "暂时无法检查AI知识发布状态",
                status_code=503,
            ) from exc

        row = self.session.get(ProductKnowledgePublication, product_id)
        if row is None:
            row = ProductKnowledgePublication(
                product_id=product_id,
                status=status,
                current_fingerprint=canonical.fingerprint,
                chunk_count=0,
                embedding_count=0,
            )
            self.session.add(row)
        if status == AiKnowledgeStatus.NOT_GENERATED and row.last_error_code:
            status = AiKnowledgeStatus.SYNC_FAILED
        row.status = status
        row.current_fingerprint = canonical.fingerprint
        row.indexed_fingerprint = evidence.get("indexed_fingerprint")
        row.active_collection = evidence.get("active_collection")
        row.chunk_count = int(evidence.get("chunk_count") or 0)
        row.embedding_count = int(evidence.get("embedding_count") or 0)
        row.checked_at = _now()
        row.updated_at = row.checked_at
        if status != AiKnowledgeStatus.SYNC_FAILED:
            row.last_error_code = None
        self.session.commit()
        return ProductKnowledgePublicationResponse(
            changed=False,
            product_id=product_id,
            ai_knowledge=self._summary(
                row, status=status, current_fingerprint=canonical.fingerprint
            ),
        )

    def list_receipts(self, product_id: str) -> ProductKnowledgePublicationReceiptList:
        rows = list(
            self.session.scalars(
                select(ProductKnowledgePublicationReceipt)
                .where(ProductKnowledgePublicationReceipt.product_id == product_id)
                .order_by(ProductKnowledgePublicationReceipt.created_at.desc())
            )
        )
        return ProductKnowledgePublicationReceiptList(
            items=[self._receipt(row) for row in rows], total=len(rows)
        )

    @staticmethod
    def _require_key(value: str | None) -> str:
        key = (value or "").strip()
        if not key or len(key) > 255:
            raise AppError(
                "AI_KNOWLEDGE_IDEMPOTENCY_REQUIRED",
                "必须提供有效的 Idempotency-Key",
                status_code=422,
            )
        return key

    @staticmethod
    def _request_fingerprint(product_id: str, command: ProductKnowledgePublishCommand) -> str:
        return hashlib.sha256(
            json.dumps(
                {"product_id": product_id, "command": command.model_dump()},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _save_idempotency(
        self,
        key: str,
        fingerprint: str,
        response: ProductKnowledgePublicationResponse,
    ) -> None:
        self.session.add(
            ProductKnowledgePublicationIdempotency(
                idempotency_key=key,
                request_fingerprint=fingerprint,
                response_json=response.model_dump_json(),
            )
        )

    @staticmethod
    def _receipt(
        row: ProductKnowledgePublicationReceipt,
    ) -> ProductKnowledgePublicationReceiptSchema:
        return ProductKnowledgePublicationReceiptSchema(
            publication_receipt_id=row.publication_receipt_id,
            product_id=row.product_id,
            knowledge_fingerprint=row.knowledge_fingerprint,
            active_collection=row.active_collection,
            chunk_count=row.chunk_count,
            embedding_count=row.embedding_count,
            status=AiKnowledgeStatus(row.status),
            operator=row.operator,
            created_at=row.created_at,
        )

    @staticmethod
    def _summary(
        row: ProductKnowledgePublication,
        *,
        status: AiKnowledgeStatus,
        current_fingerprint: str,
    ) -> AiKnowledgeSummary:
        embedding_status = {
            AiKnowledgeStatus.NOT_GENERATED: EmbeddingStatus.NOT_GENERATED,
            AiKnowledgeStatus.GENERATING: EmbeddingStatus.GENERATING,
            AiKnowledgeStatus.PUBLISHED: EmbeddingStatus.COMPLETE,
            AiKnowledgeStatus.NEED_RESYNC: EmbeddingStatus.COMPLETE,
            AiKnowledgeStatus.SYNC_FAILED: EmbeddingStatus.FAILED,
        }[status]
        return AiKnowledgeSummary(
            status=status,
            embedding_status=embedding_status,
            current_fingerprint=current_fingerprint,
            indexed_fingerprint=row.indexed_fingerprint,
            active_collection=row.active_collection,
            chunk_count=row.chunk_count,
            embedding_count=row.embedding_count,
            updated_at=row.checked_at or row.updated_at,
            published_at=row.published_at,
            last_error_code=row.last_error_code,
        )
