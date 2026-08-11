"""C Admin routes for store and product business-information maintenance."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.iam.dependencies import Principal, require_operations_access
from app.operation_management.schemas import (
    ProductBasicInfoUpdateRequest,
    ProductCreateRequest,
    ProductOperationItem,
    StoreCreateRequest,
    StoreOperationItem,
    StoreOperationListResponse,
    StoreUpdateRequest,
)
from app.operation_management.service import OperationManagementService
from app.product_knowledge.schemas import ProductKnowledgeDetail
from app.store_platform_bindings.schemas import (
    StorePlatformBindingCreateRequest,
    StorePlatformBindingListResponse,
    StorePlatformBindingProjection,
    StorePlatformBindingRevokeRequest,
)
from app.store_platform_bindings.service import StorePlatformBindingService


router = APIRouter(prefix="/api/v1/admin/operations", tags=["operation-management"])


@router.get("/stores", response_model=StoreOperationListResponse)
def list_operation_stores(
    session: Session = Depends(get_db),
) -> StoreOperationListResponse:
    return OperationManagementService(session).list_stores()


@router.post("/stores", response_model=StoreOperationItem, status_code=201)
def create_operation_store(
    request: StoreCreateRequest,
    session: Session = Depends(get_db),
) -> StoreOperationItem:
    return OperationManagementService(session).create_store(request)


@router.get("/stores/{store_ref}", response_model=StoreOperationItem)
def get_operation_store(
    store_ref: int,
    session: Session = Depends(get_db),
) -> StoreOperationItem:
    return OperationManagementService(session).get_store(store_ref)


@router.patch("/stores/{store_ref}", response_model=StoreOperationItem)
def update_operation_store(
    store_ref: int,
    request: StoreUpdateRequest,
    session: Session = Depends(get_db),
) -> StoreOperationItem:
    return OperationManagementService(session).update_store(store_ref, request)


@router.get(
    "/stores/{store_ref}/platform-bindings",
    response_model=StorePlatformBindingListResponse,
)
def list_store_platform_bindings(
    store_ref: int,
    include_revoked: bool = Query(default=True),
    _: Principal = Depends(require_operations_access),
    session: Session = Depends(get_db),
) -> StorePlatformBindingListResponse:
    return StorePlatformBindingService(session).list_for_store(
        store_ref,
        include_revoked=include_revoked,
    )


@router.post(
    "/stores/{store_ref}/platform-bindings",
    response_model=StorePlatformBindingProjection,
    status_code=201,
)
def create_store_platform_binding(
    store_ref: int,
    request: StorePlatformBindingCreateRequest,
    principal: Principal = Depends(require_operations_access),
    session: Session = Depends(get_db),
) -> StorePlatformBindingProjection:
    return StorePlatformBindingService(session).create(
        store_ref,
        request,
        verified_by=principal.user_id,
    )


@router.post(
    "/stores/{store_ref}/platform-bindings/{binding_id}/revoke",
    response_model=StorePlatformBindingProjection,
)
def revoke_store_platform_binding(
    store_ref: int,
    binding_id: str,
    request: StorePlatformBindingRevokeRequest,
    principal: Principal = Depends(require_operations_access),
    session: Session = Depends(get_db),
) -> StorePlatformBindingProjection:
    return StorePlatformBindingService(session).revoke(
        store_ref,
        binding_id,
        request,
        revoked_by=principal.user_id,
    )


@router.post(
    "/stores/{store_ref}/products",
    response_model=ProductOperationItem,
    status_code=201,
)
def create_operation_product(
    store_ref: int,
    request: ProductCreateRequest,
    session: Session = Depends(get_db),
) -> ProductOperationItem:
    return OperationManagementService(session).create_product(store_ref, request)


@router.patch(
    "/products/{product_id}/basic-info",
    response_model=ProductKnowledgeDetail,
)
def update_product_basic_info(
    product_id: str,
    request: ProductBasicInfoUpdateRequest,
    session: Session = Depends(get_db),
) -> ProductKnowledgeDetail:
    return OperationManagementService(session).update_product_basic_info(
        product_id,
        request,
    )
