"""C-admin routes for the product knowledge operations projection."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.product_knowledge.schemas import (
    KnowledgeGapListResponse,
    KnowledgeGapWorkflowStatus,
    ProductKnowledgeDetail,
    ProductKnowledgeListResponse,
    ProductKnowledgeOverview,
)
from app.product_knowledge.service import ProductKnowledgeService


router = APIRouter(prefix="/api/v1/admin/product-knowledge", tags=["product-knowledge"])


@router.get("/overview", response_model=ProductKnowledgeOverview)
def get_product_knowledge_overview(
    session: Session = Depends(get_db),
) -> ProductKnowledgeOverview:
    return ProductKnowledgeService(session).overview()


@router.get("/products", response_model=ProductKnowledgeListResponse)
def list_product_knowledge(
    store_code: str | None = Query(None),
    session: Session = Depends(get_db),
) -> ProductKnowledgeListResponse:
    return ProductKnowledgeService(session).list_products(store_code=store_code)


@router.get("/gaps", response_model=KnowledgeGapListResponse)
def list_product_knowledge_gaps(
    store_code: str | None = Query(None),
    priority: str | None = Query(None, pattern="^P[0-3]$"),
    workflow_status: KnowledgeGapWorkflowStatus | None = Query(None),
    session: Session = Depends(get_db),
) -> KnowledgeGapListResponse:
    return ProductKnowledgeService(session).list_gaps(
        store_code=store_code,
        priority=priority,
        workflow_status=workflow_status,
    )


@router.get("/products/{product_id}", response_model=ProductKnowledgeDetail)
def get_product_knowledge_detail(
    product_id: str,
    session: Session = Depends(get_db),
) -> ProductKnowledgeDetail:
    detail = ProductKnowledgeService(session).detail(product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到商品知识记录")
    return detail
