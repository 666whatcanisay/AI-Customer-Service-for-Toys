"""Projection and operator-controlled activation owned by C."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.customer_catalog.schemas import (
    ActivationEntity,
    ActivationReceipt,
    ActivationReceiptListResponse,
    ActivationRequest,
    ActivationResponse,
    ActivationSource,
    ActivatableEntityType,
    CatalogEntityType,
    CatalogResultStatus,
    CatalogWarning,
    CustomerCatalogProduct,
    CustomerProductAiKnowledgeStatus,
    CustomerCatalogSku,
    CustomerCatalogStore,
    CustomerServiceStatus,
    DataSource,
    ProductCatalogResponse,
    SkuCatalogResponse,
    StoreCatalogResponse,
    BatchActivationItem,
    BatchActivationItemStatus,
    BatchActivationRequest,
    BatchActivationResponse,
    BatchActivationResultStatus,
)
from app.errors import AppError
from app.knowledge_publishing.models import (
    ProductKnowledgePublication,
    ProductKnowledgePublicationReceipt,
)
from app.knowledge_publishing.projection import publication_summary
from app.knowledge_publishing.schemas import AiKnowledgeStatus, EmbeddingStatus
from app.test_catalog.models import (
    CatalogActivationIdempotency,
    CatalogActivationReceipt,
    TestProduct,
    TestSku,
    TestStore,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: object) -> str:
    return str(value or "").strip()


class _Warnings:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, CatalogEntityType, str], int] = defaultdict(int)

    def add(self, code: str, entity_type: CatalogEntityType, message: str) -> None:
        self._counts[(code, entity_type, message)] += 1

    def items(self) -> list[CatalogWarning]:
        return [
            CatalogWarning(code=code, entity_type=entity_type, count=count, message=message)
            for (code, entity_type, message), count in sorted(
                self._counts.items(), key=lambda item: (item[0][1], item[0][0])
            )
        ]


class CustomerAvailableCatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_stores(self) -> StoreCatalogResponse:
        warnings = _Warnings()
        items: list[CustomerCatalogStore] = []
        for store in self.session.scalars(select(TestStore).order_by(TestStore.store_code)):
            projected = self._project_store(store, warnings)
            if projected is not None:
                items.append(projected)
        warning_items = warnings.items()
        return StoreCatalogResponse(
            result_status=(
                CatalogResultStatus.PARTIAL if warning_items else CatalogResultStatus.COMPLETE
            ),
            items=items,
            total=len(items),
            warnings=warning_items,
        )

    def list_products(self, store_code: str) -> ProductCatalogResponse:
        warnings = _Warnings()
        store = self._effective_store(store_code, warnings)
        if store is None:
            warning_items = warnings.items()
            return ProductCatalogResponse(
                result_status=(
                    CatalogResultStatus.PARTIAL
                    if warning_items
                    else CatalogResultStatus.COMPLETE
                ),
                items=[],
                total=0,
                warnings=warning_items,
            )
        source = DataSource(store.data_source)
        products = self.session.scalars(
            select(TestProduct)
            .where(
                TestProduct.package_id == store.package_id,
                TestProduct.store_code == store.store_code,
            )
            .order_by(TestProduct.product_id)
        )
        items: list[CustomerCatalogProduct] = []
        for product in products:
            projected = self._project_product(product, source, warnings)
            if projected is not None:
                items.append(projected)
        warning_items = warnings.items()
        return ProductCatalogResponse(
            result_status=(
                CatalogResultStatus.PARTIAL if warning_items else CatalogResultStatus.COMPLETE
            ),
            items=items,
            total=len(items),
            warnings=warning_items,
        )

    def get_product_ai_knowledge_status(
        self, product_id: str
    ) -> CustomerProductAiKnowledgeStatus:
        """Return C-owned publication evidence for an available B product."""

        warnings = _Warnings()
        product = self.session.get(TestProduct, product_id)
        if product is None:
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_NOT_FOUND",
                "未找到客服可用商品",
                status_code=404,
            )
        store = self.session.scalar(
            select(TestStore).where(
                TestStore.package_id == product.package_id,
                TestStore.store_code == product.store_code,
            )
        )
        if (
            store is None
            or self._project_store(store, warnings) is None
            or self._project_product(product, DataSource(store.data_source), warnings)
            is None
        ):
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_NOT_FOUND",
                "未找到客服可用商品",
                status_code=404,
            )

        summary = publication_summary(self.session, product)
        ledger = self.session.get(ProductKnowledgePublication, product.product_id)
        receipt = (
            self.session.get(
                ProductKnowledgePublicationReceipt, ledger.publication_receipt_id
            )
            if ledger is not None and ledger.publication_receipt_id
            else None
        )
        status = summary.status
        embedding_status = summary.embedding_status
        if status == AiKnowledgeStatus.PUBLISHED and (
            receipt is None
            or summary.chunk_count < 1
            or summary.embedding_count != summary.chunk_count
            or embedding_status != EmbeddingStatus.COMPLETE
        ):
            # C owns the final readiness projection. B must never infer a usable
            # publication from a status string without receipt and chunk proof.
            status = AiKnowledgeStatus.SYNC_FAILED
            embedding_status = EmbeddingStatus.FAILED

        return CustomerProductAiKnowledgeStatus(
            product_id=product.product_id,
            status=status,
            embedding_status=embedding_status,
            publication_receipt_id=(
                receipt.publication_receipt_id if receipt is not None else None
            ),
            active_collection=summary.active_collection,
            chunk_count=summary.chunk_count,
            embedding_count=summary.embedding_count,
            indexed_fingerprint=summary.indexed_fingerprint,
            published_at=summary.published_at,
            last_checked_at=summary.updated_at or _now(),
        )

    def list_skus(self, product_id: str) -> SkuCatalogResponse:
        warnings = _Warnings()
        product = self.session.get(TestProduct, product_id)
        if product is None:
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_NOT_FOUND",
                "未找到客服可用商品",
                status_code=404,
            )
        store = self.session.scalar(
            select(TestStore).where(
                TestStore.package_id == product.package_id,
                TestStore.store_code == product.store_code,
            )
        )
        if (
            store is None
            or self._project_store(store, warnings) is None
            or product.customer_service_status != CustomerServiceStatus.ENABLED
            or self._project_product(product, DataSource(store.data_source), warnings) is None
        ):
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_NOT_FOUND",
                "未找到客服可用商品",
                status_code=404,
            )
        source = DataSource(store.data_source)
        items: list[CustomerCatalogSku] = []
        for sku in self.session.scalars(
            select(TestSku)
            .where(
                TestSku.package_id == product.package_id,
                TestSku.product_id == product.product_id,
            )
            .order_by(TestSku.sku_id)
        ):
            projected = self._project_sku(sku, product, source, warnings)
            if projected is not None:
                items.append(projected)
        warning_items = warnings.items()
        return SkuCatalogResponse(
            result_status=(
                CatalogResultStatus.PARTIAL if warning_items else CatalogResultStatus.COMPLETE
            ),
            items=items,
            total=len(items),
            warnings=warning_items,
        )

    def _effective_store(self, store_code: str, warnings: _Warnings) -> TestStore | None:
        candidates = list(
            self.session.scalars(
                select(TestStore).where(TestStore.store_code == store_code).order_by(TestStore.id)
            )
        )
        effective = [
            store for store in candidates if self._project_store(store, warnings) is not None
        ]
        if len(effective) > 1:
            warnings.add(
                "CUSTOMER_SERVICE_STORE_SCOPE_AMBIGUOUS",
                CatalogEntityType.STORE,
                "同一店铺标识存在多个可用范围，已隔离该店铺。",
            )
            return None
        return effective[0] if effective else None

    @staticmethod
    def _project_store(
        store: TestStore, warnings: _Warnings
    ) -> CustomerCatalogStore | None:
        if store.customer_service_status == CustomerServiceStatus.DISABLED:
            return None
        if store.customer_service_status != CustomerServiceStatus.ENABLED:
            warnings.add(
                "CUSTOMER_SERVICE_STATUS_UNKNOWN",
                CatalogEntityType.STORE,
                "店铺客服状态无法识别，已隔离该记录。",
            )
            return None
        if store.data_source not in {DataSource.TEST, DataSource.PILOT}:
            warnings.add(
                "CUSTOMER_SERVICE_SOURCE_UNKNOWN",
                CatalogEntityType.STORE,
                "店铺数据来源无法确认，已隔离该记录。",
            )
            return None
        if not store.trial_enabled:
            warnings.add(
                "CUSTOMER_SERVICE_STORE_INACTIVE",
                CatalogEntityType.STORE,
                "店铺业务状态异常，已隔离该记录。",
            )
            return None
        if not all(
            _text(value)
            for value in (store.tenant_id, store.platform, store.store_code, store.store_name)
        ):
            warnings.add(
                "CUSTOMER_SERVICE_ENTITY_INVALID",
                CatalogEntityType.STORE,
                "店铺身份、平台或名称不完整，已隔离该记录。",
            )
            return None
        return CustomerCatalogStore(
            tenant_id=_text(store.tenant_id),
            platform=_text(store.platform),
            store_code=_text(store.store_code),
            store_name=_text(store.store_name),
            data_source=DataSource(store.data_source),
            allow_auto_send=False,
        )

    @staticmethod
    def _project_product(
        product: TestProduct, source: DataSource, warnings: _Warnings
    ) -> CustomerCatalogProduct | None:
        if product.customer_service_status == CustomerServiceStatus.DISABLED:
            return None
        if product.customer_service_status != CustomerServiceStatus.ENABLED:
            warnings.add(
                "CUSTOMER_SERVICE_STATUS_UNKNOWN",
                CatalogEntityType.PRODUCT,
                "商品客服状态无法识别，已隔离该记录。",
            )
            return None
        official_name = _text(product.product_name_official)
        display_name = _text(product.product_name_display)
        if not _text(product.product_id) or not _text(product.store_code) or not (
            official_name or display_name
        ):
            warnings.add(
                "CUSTOMER_SERVICE_ENTITY_INVALID",
                CatalogEntityType.PRODUCT,
                "商品身份、父级或名称不完整，已隔离该记录。",
            )
            return None
        official_name = official_name or display_name
        display_name = display_name or official_name
        return CustomerCatalogProduct(
            product_id=_text(product.product_id),
            platform=_text(product.platform) or "unknown",
            store_code=_text(product.store_code),
            product_name_official=official_name,
            product_name_display=display_name,
            sales_status=_text(product.sales_status) or "UNKNOWN",
            knowledge_status=_text(product.review_status) or "UNKNOWN",
            age_min=product.age_min,
            age_max=product.age_max,
            safety_summary=product.safety_summary,
            data_source=source,
        )

    @staticmethod
    def _project_sku(
        sku: TestSku,
        product: TestProduct,
        source: DataSource,
        warnings: _Warnings,
    ) -> CustomerCatalogSku | None:
        official_name = _text(sku.sku_name_official)
        display_name = _text(sku.sku_name_display)
        if (
            not _text(sku.sku_id)
            or not _text(sku.sku_code)
            or sku.product_id != product.product_id
            or not _text(sku.relation_type)
            or not (official_name or display_name)
        ):
            warnings.add(
                "CUSTOMER_SERVICE_ENTITY_INVALID",
                CatalogEntityType.SKU,
                "SKU身份、父级、名称或关系不完整，已隔离该记录。",
            )
            return None
        try:
            component_refs = json.loads(sku.component_sku_refs_json)
        except (TypeError, ValueError):
            component_refs = None
        if not isinstance(component_refs, list) or not all(
            isinstance(value, str) and value.strip() for value in component_refs
        ):
            warnings.add(
                "CUSTOMER_SERVICE_ENTITY_INVALID",
                CatalogEntityType.SKU,
                "SKU组合关系格式无效，已隔离该记录。",
            )
            return None
        return CustomerCatalogSku(
            sku_id=_text(sku.sku_id),
            product_id=_text(sku.product_id),
            sku_code=_text(sku.sku_code),
            sku_name_official=official_name or display_name,
            sku_name_display=display_name or official_name,
            relation_type=_text(sku.relation_type),
            canonical_sku_id=_text(sku.canonical_sku_id) or None,
            reference_sku_id=_text(sku.reference_sku_id) or None,
            component_sku_refs=[value.strip() for value in component_refs],
            data_source=source,
        )


class CatalogActivationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def set_store_status(
        self,
        store_ref: int,
        request: ActivationRequest,
        idempotency_key: str | None,
    ) -> tuple[ActivationResponse, bool]:
        key = self._require_key(idempotency_key)
        fingerprint = self._fingerprint("STORE", str(store_ref), request)
        replay = self._replay(key, fingerprint)
        if replay is not None:
            return replay, True
        store = self.session.get(TestStore, store_ref)
        if store is None:
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_NOT_FOUND", "未找到店铺", status_code=404
            )
        source = self._store_source(store)
        if request.customer_service_status == CustomerServiceStatus.ENABLED:
            self._validate_store_for_enable(store)
        response = self._apply(
            entity_type=ActivatableEntityType.STORE,
            entity_ref=str(store.id),
            data_source=source,
            current_status=store.customer_service_status,
            current_updated_at=store.customer_service_status_updated_at,
            current_updated_by=store.customer_service_status_updated_by,
            request=request,
            assign=lambda status, at, by: self._assign_store(store, status, at, by),
        )
        self._save_idempotency(key, fingerprint, response)
        self.session.commit()
        return response, False

    def set_product_status(
        self,
        product_id: str,
        request: ActivationRequest,
        idempotency_key: str | None,
    ) -> tuple[ActivationResponse, bool]:
        key = self._require_key(idempotency_key)
        fingerprint = self._fingerprint("PRODUCT", product_id, request)
        replay = self._replay(key, fingerprint)
        if replay is not None:
            return replay, True
        product = self.session.get(TestProduct, product_id)
        if product is None:
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_NOT_FOUND", "未找到商品", status_code=404
            )
        store = self.session.scalar(
            select(TestStore).where(
                TestStore.package_id == product.package_id,
                TestStore.store_code == product.store_code,
            )
        )
        if store is None:
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_INVALID",
                "商品所属店铺不完整",
                status_code=409,
            )
        source = self._store_source(store)
        if request.customer_service_status == CustomerServiceStatus.ENABLED:
            if product.review_status != "APPROVED":
                raise AppError(
                    "CUSTOMER_SERVICE_PRODUCT_NOT_APPROVED",
                    "只有已审核通过的商品可以启用客服使用",
                    status_code=409,
                )
            if store.customer_service_status != CustomerServiceStatus.ENABLED:
                raise AppError(
                    "CUSTOMER_SERVICE_STORE_NOT_ENABLED",
                    "请先启用商品所属店铺",
                    status_code=409,
                )
            self._validate_store_for_enable(store)
            if not _text(product.product_id) or not (
                _text(product.product_name_display) or _text(product.product_name_official)
            ):
                raise AppError(
                    "CUSTOMER_SERVICE_ENTITY_INVALID",
                    "商品名称或身份不完整，不能启用",
                    status_code=409,
                )
        response = self._apply(
            entity_type=ActivatableEntityType.PRODUCT,
            entity_ref=product.product_id,
            data_source=source,
            current_status=product.customer_service_status,
            current_updated_at=product.customer_service_status_updated_at,
            current_updated_by=product.customer_service_status_updated_by,
            request=request,
            assign=lambda status, at, by: self._assign_product(product, status, at, by),
        )
        self._save_idempotency(key, fingerprint, response)
        self.session.commit()
        return response, False

    def enable_products_batch(
        self,
        request: BatchActivationRequest,
        idempotency_key: str | None,
    ) -> tuple[BatchActivationResponse, bool]:
        key = self._require_key(idempotency_key)
        request_payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(
                request_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        batch_key = "BATCH-" + hashlib.sha256(key.encode("utf-8")).hexdigest()
        existing = self.session.get(CatalogActivationIdempotency, batch_key)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise AppError(
                    "ACTIVATION_IDEMPOTENCY_CONFLICT",
                    "Idempotency-Key 已用于其他批量启用请求",
                    status_code=409,
                )
            return BatchActivationResponse.model_validate_json(
                existing.response_json
            ), True

        items: list[BatchActivationItem] = []
        for product_id in request.product_ids:
            product = self.session.get(TestProduct, product_id)
            if product is None:
                items.append(
                    BatchActivationItem(
                        product_id=product_id,
                        status=BatchActivationItemStatus.FAILED,
                        error_code="CUSTOMER_SERVICE_ENTITY_NOT_FOUND",
                        message="未找到商品",
                    )
                )
                continue
            if product.review_status != "APPROVED":
                items.append(
                    BatchActivationItem(
                        product_id=product_id,
                        status=BatchActivationItemStatus.FAILED,
                        error_code="CUSTOMER_SERVICE_PRODUCT_NOT_APPROVED",
                        message="只有已审核通过的商品可以启用客服使用",
                    )
                )
                continue
            item_key = "ITEM-" + hashlib.sha256(
                f"{key}\n{product_id}".encode("utf-8")
            ).hexdigest()
            try:
                result, _ = self.set_product_status(
                    product_id,
                    ActivationRequest(
                        customer_service_status=CustomerServiceStatus.ENABLED,
                        confirmed_by=request.confirmed_by,
                        confirmation_note=request.confirmation_note,
                    ),
                    item_key,
                )
                items.append(
                    BatchActivationItem(
                        product_id=product_id,
                        status=(
                            BatchActivationItemStatus.CHANGED
                            if result.changed
                            else BatchActivationItemStatus.UNCHANGED
                        ),
                        activation_receipt=result.activation_receipt,
                        message=(
                            "已启用客服使用"
                            if result.changed
                            else "商品已经处于客服启用状态"
                        ),
                    )
                )
            except AppError as exc:
                self.session.rollback()
                items.append(
                    BatchActivationItem(
                        product_id=product_id,
                        status=BatchActivationItemStatus.FAILED,
                        error_code=exc.code,
                        message=exc.message,
                    )
                )

        changed_count = sum(item.status == BatchActivationItemStatus.CHANGED for item in items)
        unchanged_count = sum(
            item.status == BatchActivationItemStatus.UNCHANGED for item in items
        )
        failed_count = sum(item.status == BatchActivationItemStatus.FAILED for item in items)
        response = BatchActivationResponse(
            result_status=(
                BatchActivationResultStatus.FAILED
                if failed_count == len(items)
                else BatchActivationResultStatus.PARTIAL
                if failed_count
                else BatchActivationResultStatus.COMPLETE
            ),
            items=items,
            changed_count=changed_count,
            unchanged_count=unchanged_count,
            failed_count=failed_count,
            server_time=_now(),
        )
        self.session.add(
            CatalogActivationIdempotency(
                idempotency_key=batch_key,
                request_fingerprint=fingerprint,
                response_json=response.model_dump_json(),
            )
        )
        self.session.commit()
        return response, False

    def get_receipt(self, receipt_id: str) -> ActivationReceipt:
        row = self.session.get(CatalogActivationReceipt, receipt_id)
        if row is None:
            raise AppError(
                "ACTIVATION_RECEIPT_NOT_FOUND",
                "未找到客服状态变更收据",
                status_code=404,
            )
        return self._receipt_schema(row)

    def list_receipts(
        self,
        entity_type: ActivatableEntityType,
        entity_ref: str,
        page: int,
        size: int,
    ) -> ActivationReceiptListResponse:
        conditions = (
            CatalogActivationReceipt.entity_type == entity_type,
            CatalogActivationReceipt.entity_ref == entity_ref,
        )
        total = int(
            self.session.scalar(
                select(func.count()).select_from(CatalogActivationReceipt).where(*conditions)
            )
            or 0
        )
        rows = self.session.scalars(
            select(CatalogActivationReceipt)
            .where(*conditions)
            .order_by(CatalogActivationReceipt.confirmed_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return ActivationReceiptListResponse(
            items=[self._receipt_schema(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    @staticmethod
    def _require_key(value: str | None) -> str:
        key = _text(value)
        if not key or len(key) > 255:
            raise AppError(
                "CUSTOMER_SERVICE_STATUS_INVALID",
                "必须提供有效的 Idempotency-Key",
                status_code=422,
            )
        return key

    @staticmethod
    def _fingerprint(
        entity_type: str, entity_ref: str, request: ActivationRequest
    ) -> str:
        payload = {
            "entity_type": entity_type,
            "entity_ref": entity_ref,
            "request": request.model_dump(mode="json"),
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()

    def _replay(self, key: str, fingerprint: str) -> ActivationResponse | None:
        existing = self.session.get(CatalogActivationIdempotency, key)
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                "ACTIVATION_IDEMPOTENCY_CONFLICT",
                "Idempotency-Key 已用于其他客服状态请求",
                status_code=409,
            )
        return ActivationResponse.model_validate_json(existing.response_json)

    def _apply(
        self,
        *,
        entity_type: ActivatableEntityType,
        entity_ref: str,
        data_source: DataSource,
        current_status: str,
        current_updated_at: datetime | None,
        current_updated_by: str | None,
        request: ActivationRequest,
        assign,
    ) -> ActivationResponse:
        now = _now()
        if current_status == request.customer_service_status:
            return ActivationResponse(
                changed=False,
                entity=ActivationEntity(
                    entity_type=entity_type,
                    entity_ref=entity_ref,
                    data_source=data_source,
                    customer_service_status=request.customer_service_status,
                    customer_service_status_updated_at=current_updated_at,
                    customer_service_status_updated_by=current_updated_by,
                ),
                activation_receipt=None,
                server_time=now,
            )
        if current_status not in {
            CustomerServiceStatus.ENABLED,
            CustomerServiceStatus.DISABLED,
        }:
            raise AppError(
                "CUSTOMER_SERVICE_STATUS_INVALID",
                "当前客服状态无法识别",
                status_code=409,
            )
        assign(request.customer_service_status.value, now, request.confirmed_by)
        receipt_row = CatalogActivationReceipt(
            activation_receipt_id=f"ACT-{uuid4().hex}",
            entity_type=entity_type.value,
            entity_ref=entity_ref,
            data_source=data_source.value,
            previous_status=str(current_status),
            customer_service_status=request.customer_service_status.value,
            activation_source=ActivationSource.OPERATOR.value,
            confirmed_by=request.confirmed_by,
            confirmation_note=request.confirmation_note,
            confirmed_at=now,
        )
        self.session.add(receipt_row)
        receipt = self._receipt_schema(receipt_row)
        return ActivationResponse(
            changed=True,
            entity=ActivationEntity(
                entity_type=entity_type,
                entity_ref=entity_ref,
                data_source=data_source,
                customer_service_status=request.customer_service_status,
                customer_service_status_updated_at=now,
                customer_service_status_updated_by=request.confirmed_by,
            ),
            activation_receipt=receipt,
            server_time=now,
        )

    @staticmethod
    def _assign_store(store: TestStore, status: str, at: datetime, by: str) -> None:
        store.customer_service_status = status
        store.customer_service_status_updated_at = at
        store.customer_service_status_updated_by = by

    @staticmethod
    def _assign_product(product: TestProduct, status: str, at: datetime, by: str) -> None:
        product.customer_service_status = status
        product.customer_service_status_updated_at = at
        product.customer_service_status_updated_by = by

    @staticmethod
    def _store_source(store: TestStore) -> DataSource:
        if store.data_source not in {DataSource.TEST, DataSource.PILOT}:
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_QUARANTINED",
                "数据来源无法确认，不能变更客服状态",
                status_code=409,
            )
        return DataSource(store.data_source)

    @staticmethod
    def _validate_store_for_enable(store: TestStore) -> None:
        if not store.trial_enabled or not all(
            _text(value) for value in (store.store_code, store.store_name, store.platform)
        ):
            raise AppError(
                "CUSTOMER_SERVICE_ENTITY_INVALID",
                "店铺名称、平台或业务状态不满足启用条件",
                status_code=409,
            )

    def _save_idempotency(
        self, key: str, fingerprint: str, response: ActivationResponse
    ) -> None:
        self.session.add(
            CatalogActivationIdempotency(
                idempotency_key=key,
                request_fingerprint=fingerprint,
                response_json=response.model_dump_json(),
                created_at=_now(),
            )
        )

    @staticmethod
    def _receipt_schema(row: CatalogActivationReceipt) -> ActivationReceipt:
        return ActivationReceipt(
            activation_receipt_id=row.activation_receipt_id,
            entity_type=ActivatableEntityType(row.entity_type),
            entity_ref=row.entity_ref,
            data_source=DataSource(row.data_source),
            previous_status=(
                CustomerServiceStatus(row.previous_status) if row.previous_status else None
            ),
            customer_service_status=CustomerServiceStatus(row.customer_service_status),
            activation_source=ActivationSource(row.activation_source),
            confirmed_by=row.confirmed_by,
            confirmation_note=row.confirmation_note,
            confirmed_at=row.confirmed_at,
        )
