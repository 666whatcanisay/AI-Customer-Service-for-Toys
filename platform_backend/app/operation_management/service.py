"""No-migration C operation services over the existing pilot catalog.

The service deliberately keeps generated tenant/store identities server-side.
Knowledge edits return to review and never publish to A or RAG.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.operation_management.schemas import (
    ProductBasicInfoUpdateRequest,
    ProductCreateRequest,
    ProductOperationItem,
    StoreCreateRequest,
    StoreOperationItem,
    StoreOperationListResponse,
    StoreOperationStatus,
    StoreUpdateRequest,
)
from app.product_knowledge.schemas import ProductKnowledgeDetail
from app.product_knowledge.service import ProductKnowledgeService
from app.test_catalog.models import (
    TestEvaluationCase,
    TestFaq,
    TestKnowledgePackage,
    TestProduct,
    TestSafetyRule,
    TestStore,
)


PLATFORM_NAMES = {
    "pinduoduo": "拼多多",
    "taobao": "淘宝",
    "tmall": "天猫",
    "jd": "京东",
    "douyin": "抖音",
    "offline": "线下",
    "other": "其他平台",
}
OPERATION_SOURCE = "C_ADMIN_UI"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dict(value: str | None) -> dict:
    if not value:
        return {}
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _dump(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _record_operation(raw: dict, action: str) -> dict:
    history = raw.get("_c_operation_history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "action": action,
            "occurred_at": _now().isoformat(),
            "source": OPERATION_SOURCE,
        }
    )
    raw["_c_operation_history"] = history[-50:]
    return raw


class OperationManagementService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_stores(self) -> StoreOperationListResponse:
        rows = self.session.execute(
            select(TestStore, TestKnowledgePackage.imported_at)
            .join(
                TestKnowledgePackage,
                TestKnowledgePackage.package_id == TestStore.package_id,
            )
            .order_by(TestKnowledgePackage.imported_at.desc(), TestStore.id.desc())
        ).all()
        items = [self._store_item(store, created_at) for store, created_at in rows]
        return StoreOperationListResponse(items=items, total=len(items))

    def get_store(self, store_ref: int) -> StoreOperationItem:
        store = self.session.get(TestStore, store_ref)
        if store is None:
            raise AppError("OPERATION_STORE_NOT_FOUND", "未找到店铺", status_code=404)
        package = self.session.get(TestKnowledgePackage, store.package_id)
        if package is None:
            raise AppError("OPERATION_STORE_SCOPE_INVALID", "店铺业务范围不完整", status_code=409)
        return self._store_item(store, package.imported_at)

    def create_store(self, request: StoreCreateRequest) -> StoreOperationItem:
        self._ensure_name_available(request.store_name, request.platform.value)
        unique = uuid4().hex
        package_id = f"C-STORE-{unique}"
        store_code = f"c-store-{unique[:16]}"
        tenant_id = f"c-tenant-{unique}"
        created_at = _now()
        fingerprint = hashlib.sha256(
            f"{package_id}|{tenant_id}|{store_code}|{created_at.isoformat()}".encode("utf-8")
        ).hexdigest()
        package = TestKnowledgePackage(
            package_id=package_id,
            package_name=f"{request.store_name} · 运营建档",
            version="1.0",
            schema_version="c-operation-store.v1",
            tenant_id=tenant_id,
            platform=request.platform.value,
            store_code=store_code,
            response_mode="HUMAN_CONFIRM_REQUIRED",
            test_data_mode=True,
            production_usable=False,
            allow_auto_send=False,
            import_status="MANUAL_CREATED",
            original_filename="运营中心创建店铺",
            zip_sha256=fingerprint,
            counts_json=_dump({"stores": 1, "products": 0, "skus": 0}),
            imported_by=OPERATION_SOURCE,
            imported_at=created_at,
        )
        raw = _record_operation({"remarks": request.remarks}, "STORE_CREATED")
        store = TestStore(
            package_id=package_id,
            tenant_id=tenant_id,
            platform=request.platform.value,
            store_code=store_code,
            store_name=request.store_name,
            trial_enabled=True,
            knowledge_scope="PRODUCT_KNOWLEDGE",
            response_mode="HUMAN_CONFIRM_REQUIRED",
            allow_auto_send=False,
            test_data_mode=True,
            production_usable=False,
            data_source="PILOT",
            customer_service_status="DISABLED",
            raw_data_json=_dump(raw),
        )
        self.session.add_all([package, store])
        self.session.commit()
        self.session.refresh(store)
        return self._store_item(store, created_at)

    def update_store(self, store_ref: int, request: StoreUpdateRequest) -> StoreOperationItem:
        store = self.session.get(TestStore, store_ref)
        if store is None:
            raise AppError("OPERATION_STORE_NOT_FOUND", "未找到店铺", status_code=404)
        package = self.session.get(TestKnowledgePackage, store.package_id)
        if package is None:
            raise AppError("OPERATION_STORE_SCOPE_INVALID", "店铺业务范围不完整", status_code=409)
        self._ensure_name_available(
            request.store_name,
            request.platform.value,
            excluding_store_ref=store_ref,
        )
        previous_platform = store.platform
        store.store_name = request.store_name
        store.platform = request.platform.value
        store.trial_enabled = request.status == StoreOperationStatus.ACTIVE
        raw = _json_dict(store.raw_data_json)
        raw["remarks"] = request.remarks
        store.raw_data_json = _dump(_record_operation(raw, "STORE_UPDATED"))
        package.platform = request.platform.value
        if previous_platform != request.platform.value:
            self._update_platform_copies(store, request.platform.value)
        self.session.commit()
        return self._store_item(store, package.imported_at)

    def create_product(
        self,
        store_ref: int,
        request: ProductCreateRequest,
    ) -> ProductOperationItem:
        store = self.session.get(TestStore, store_ref)
        if store is None:
            raise AppError("OPERATION_STORE_NOT_FOUND", "未找到店铺", status_code=404)
        if not store.trial_enabled:
            raise AppError(
                "OPERATION_STORE_INACTIVE",
                "停用店铺不能新增商品",
                status_code=409,
            )
        package = self.session.get(TestKnowledgePackage, store.package_id)
        if package is None:
            raise AppError("OPERATION_STORE_SCOPE_INVALID", "店铺业务范围不完整", status_code=409)
        self._ensure_product_name_available(store, request.product_name)

        created_at = _now()
        product_id = f"C-PRODUCT-{uuid4().hex}"
        raw = _record_operation(
            {
                "product_summary": request.product_summary,
                "created_at": created_at.isoformat(),
                "creation_source": OPERATION_SOURCE,
            },
            "PRODUCT_CREATED",
        )
        product = TestProduct(
            product_id=product_id,
            package_id=store.package_id,
            tenant_id=store.tenant_id,
            platform=store.platform,
            store_code=store.store_code,
            product_name_official=request.product_name,
            product_name_display=request.product_name,
            sales_status="OFF_SALE",
            age_min=None,
            age_max=None,
            safety_summary=None,
            review_status="REVIEWING",
            publishable=False,
            customer_service_status="DISABLED",
            source_ids_json="[]",
            raw_data_json=_dump(raw),
        )
        self.session.add(product)
        self.session.flush()
        package_counts = _json_dict(package.counts_json)
        package_counts["products"] = int(
            self.session.scalar(
                select(func.count(TestProduct.product_id)).where(
                    TestProduct.package_id == store.package_id,
                )
            )
            or 0
        )
        package.counts_json = _dump(package_counts)
        self.session.commit()
        return ProductOperationItem(
            product_ref=product.product_id,
            store_ref=store.id,
            store_name=store.store_name,
            product_name=product.product_name_display,
            product_summary=request.product_summary,
            data_status="PENDING_REVIEW",
            data_status_name="待审核",
            sku_count=0,
            created_at=created_at,
            data_source=store.data_source or "UNKNOWN",
            customer_service_status=product.customer_service_status,
        )

    def update_product_basic_info(
        self,
        product_id: str,
        request: ProductBasicInfoUpdateRequest,
    ) -> ProductKnowledgeDetail:
        product = self.session.get(TestProduct, product_id)
        if product is None:
            raise AppError("OPERATION_PRODUCT_NOT_FOUND", "未找到商品", status_code=404)
        store = self.session.scalar(
            select(TestStore).where(
                TestStore.package_id == product.package_id,
                TestStore.store_code == product.store_code,
            )
        )
        if store is None:
            raise AppError("OPERATION_PRODUCT_SCOPE_INVALID", "商品所属店铺不完整", status_code=409)

        product_raw = _json_dict(product.raw_data_json)
        existing_summary = str(product_raw.get("product_summary") or "")
        knowledge_changed = (
            product.product_name_display != request.product_display_name
            or existing_summary != request.product_summary
        )
        if knowledge_changed:
            product.product_name_display = request.product_display_name
            product_raw["product_summary"] = request.product_summary
            product.raw_data_json = _dump(
                _record_operation(product_raw, "PRODUCT_BASIC_INFO_UPDATED")
            )
            # A C-side knowledge edit is visible for review, but is never
            # treated as an automatic approval/publication event.
            product.review_status = "REVIEWING"
            product.publishable = False

        store.store_name = request.store_display_name
        store_raw = _json_dict(store.raw_data_json)
        store_raw["remarks"] = request.store_remarks
        store.raw_data_json = _dump(
            _record_operation(store_raw, "STORE_DISPLAY_INFO_UPDATED")
        )
        self.session.commit()

        detail = ProductKnowledgeService(self.session).detail(product_id)
        if detail is None:
            raise AppError("OPERATION_PRODUCT_NOT_FOUND", "未找到商品", status_code=404)
        return detail

    def _store_item(self, store: TestStore, created_at: datetime) -> StoreOperationItem:
        raw = _json_dict(store.raw_data_json)
        status = (
            StoreOperationStatus.ACTIVE
            if store.trial_enabled
            else StoreOperationStatus.INACTIVE
        )
        product_count = int(
            self.session.scalar(
                select(func.count(TestProduct.product_id)).where(
                    TestProduct.package_id == store.package_id,
                    TestProduct.store_code == store.store_code,
                )
            )
            or 0
        )
        return StoreOperationItem(
            store_ref=store.id,
            store_name=store.store_name,
            platform_name=PLATFORM_NAMES.get(store.platform.lower(), "其他平台"),
            status=status,
            status_name="正常" if status == StoreOperationStatus.ACTIVE else "停用",
            product_count=product_count,
            created_at=created_at,
            remarks=str(raw.get("remarks") or ""),
            data_source=store.data_source or "UNKNOWN",
            customer_service_status=store.customer_service_status,
            customer_service_status_updated_at=store.customer_service_status_updated_at,
            customer_service_status_updated_by=store.customer_service_status_updated_by,
        )

    def _ensure_name_available(
        self,
        store_name: str,
        platform: str,
        *,
        excluding_store_ref: int | None = None,
    ) -> None:
        statement = select(TestStore.id).where(
            func.lower(TestStore.store_name) == store_name.casefold(),
            TestStore.platform == platform,
        )
        if excluding_store_ref is not None:
            statement = statement.where(TestStore.id != excluding_store_ref)
        if self.session.scalar(statement) is not None:
            raise AppError(
                "OPERATION_STORE_DUPLICATE",
                "同一平台已存在同名店铺",
                status_code=409,
            )

    def _ensure_product_name_available(
        self,
        store: TestStore,
        product_name: str,
    ) -> None:
        existing = self.session.scalar(
            select(TestProduct.product_id).where(
                TestProduct.package_id == store.package_id,
                TestProduct.store_code == store.store_code,
                func.lower(TestProduct.product_name_display) == product_name.casefold(),
            )
        )
        if existing is not None:
            raise AppError(
                "OPERATION_PRODUCT_DUPLICATE",
                "该店铺已存在同名商品",
                status_code=409,
            )

    def _update_platform_copies(self, store: TestStore, platform: str) -> None:
        conditions = (
            TestProduct.package_id == store.package_id,
            TestProduct.store_code == store.store_code,
        )
        for product in self.session.scalars(select(TestProduct).where(*conditions)):
            product.platform = platform
        for faq in self.session.scalars(
            select(TestFaq).where(
                TestFaq.package_id == store.package_id,
                TestFaq.store_code == store.store_code,
            )
        ):
            faq.platform = platform
        for rule in self.session.scalars(
            select(TestSafetyRule).where(
                TestSafetyRule.package_id == store.package_id,
                TestSafetyRule.store_code == store.store_code,
            )
        ):
            rule.platform = platform
        for case in self.session.scalars(
            select(TestEvaluationCase).where(
                TestEvaluationCase.package_id == store.package_id,
                TestEvaluationCase.store_code == store.store_code,
            )
        ):
            case.platform = platform
