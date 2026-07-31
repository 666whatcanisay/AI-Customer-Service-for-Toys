"""HTTP routes for the C-owned customer available catalog."""

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.customer_catalog.schemas import (
    ActivationReceipt,
    ActivationReceiptListResponse,
    ActivationRequest,
    ActivationResponse,
    ActivatableEntityType,
    ProductCatalogResponse,
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


customer_router = APIRouter(
    prefix="/api/v1/customer-service/catalog", tags=["customer-service-catalog"]
)
admin_router = APIRouter(
    prefix="/api/v1/admin/operations", tags=["customer-service-catalog-admin"]
)


@customer_router.get("/stores", response_model=StoreCatalogResponse)
def list_customer_service_stores(
    session: Session = Depends(get_db),
) -> StoreCatalogResponse:
    return CustomerAvailableCatalogService(session).list_stores()


@customer_router.get("/products", response_model=ProductCatalogResponse)
def list_customer_service_products(
    store_code: str = Query(min_length=1, max_length=96),
    session: Session = Depends(get_db),
) -> ProductCatalogResponse:
    return CustomerAvailableCatalogService(session).list_products(store_code.strip())


@customer_router.get(
    "/products/{product_id}/skus", response_model=SkuCatalogResponse
)
def list_customer_service_skus(
    product_id: str,
    session: Session = Depends(get_db),
) -> SkuCatalogResponse:
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
