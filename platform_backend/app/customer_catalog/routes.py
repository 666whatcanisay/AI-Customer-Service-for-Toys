"""HTTP routes for the C-owned customer available catalog."""

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customer_catalog.schemas import (
    ActivationReceipt,
    ActivationReceiptListResponse,
    ActivationRequest,
    ActivationResponse,
    ActivatableEntityType,
    ProductCatalogResponse,
    CustomerProductAiKnowledgeStatus,
    SkuCatalogResponse,
    StoreCatalogResponse,
    BatchActivationRequest,
    BatchActivationResponse,
)
from app.customer_catalog.service import (
    CatalogActivationService,
    CustomerAvailableCatalogService,
)
from app.database import get_db
from app.errors import AppError
from app.iam.dependencies import Principal, get_current_principal
from app.test_catalog.models import TestProduct, TestStore


def _ensure_store_code_access(
    session: Session, principal: Principal, store_code: str
) -> None:
    if principal.all_store_access:
        return
    store_ids = set(session.scalars(
        select(TestStore.id).where(TestStore.store_code == store_code)
    ).all())
    if not store_ids.intersection(principal.store_ids):
        raise AppError(
            "AUTHORIZATION_DENIED",
            "This account is not bound to the requested Store.",
            status_code=403,
        )


def _ensure_product_access(
    session: Session, principal: Principal, product_id: str
) -> None:
    if principal.all_store_access:
        return
    product = session.get(TestProduct, product_id)
    if product is None:
        raise AppError("CUSTOMER_SERVICE_ENTITY_NOT_FOUND", "未找到客服可用商品", status_code=404)
    stores = session.scalars(select(TestStore).where(
        TestStore.package_id == product.package_id,
        TestStore.store_code == product.store_code,
    )).all()
    if not any(store.id in principal.store_ids for store in stores):
        raise AppError(
            "AUTHORIZATION_DENIED",
            "This account is not bound to the requested Store.",
            status_code=403,
        )


customer_router = APIRouter(
    prefix="/api/v1/customer-service/catalog", tags=["customer-service-catalog"]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/operations", tags=["customer-service-catalog-admin"]
)


@customer_router.get("/stores", response_model=StoreCatalogResponse)
def list_customer_service_stores(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> StoreCatalogResponse:
    allowed = None if principal.all_store_access else principal.store_ids
    return CustomerAvailableCatalogService(session).list_stores(allowed)


@customer_router.get("/products", response_model=ProductCatalogResponse)
def list_customer_service_products(
    store_code: str = Query(min_length=1, max_length=96),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> ProductCatalogResponse:
    _ensure_store_code_access(session, principal, store_code.strip())
    return CustomerAvailableCatalogService(session).list_products(store_code.strip())


@customer_router.get(
    "/products/{product_id}/ai-knowledge",
    response_model=CustomerProductAiKnowledgeStatus,
)
def get_customer_service_product_ai_knowledge(
    product_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> CustomerProductAiKnowledgeStatus:
    _ensure_product_access(session, principal, product_id)
    return CustomerAvailableCatalogService(session).get_product_ai_knowledge_status(
        product_id
    )


@customer_router.get(
    "/products/{product_id}/skus", response_model=SkuCatalogResponse
)
def list_customer_service_skus(
    product_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> SkuCatalogResponse:
    _ensure_product_access(session, principal, product_id)
    return CustomerAvailableCatalogService(session).list_skus(product_id)


@admin_router.put(
    "/stores/{store_ref}/customer-service-status",
    response_model=ActivationResponse,
)
def set_store_customer_service_status(
    store_ref: int,
    request: ActivationRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> ActivationResponse:
    result, replayed = CatalogActivationService(session).set_store_status(
        store_ref, request, idempotency_key
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@admin_router.post(
    "/products/customer-service-status:batch",
    response_model=BatchActivationResponse,
)
def enable_products_for_customer_service(
    request: BatchActivationRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> BatchActivationResponse:
    result, replayed = CatalogActivationService(session).enable_products_batch(
        request, idempotency_key
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@admin_router.put(
    "/products/{product_id}/customer-service-status",
    response_model=ActivationResponse,
)
def set_product_customer_service_status(
    product_id: str,
    request: ActivationRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> ActivationResponse:
    result, replayed = CatalogActivationService(session).set_product_status(
        product_id, request, idempotency_key
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@admin_router.get(
    "/activation-receipts/{activation_receipt_id}",
    response_model=ActivationReceipt,
)
def get_activation_receipt(
    activation_receipt_id: str,
    session: Session = Depends(get_db),
) -> ActivationReceipt:
    return CatalogActivationService(session).get_receipt(activation_receipt_id)


@admin_router.get(
    "/activation-receipts",
    response_model=ActivationReceiptListResponse,
)
def list_activation_receipts(
    entity_type: ActivatableEntityType,
    entity_ref: str = Query(min_length=1, max_length=128),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> ActivationReceiptListResponse:
    return CatalogActivationService(session).list_receipts(
        entity_type, entity_ref, page, size
    )
