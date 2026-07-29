"""C Admin routes for store and product business-information maintenance."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
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
