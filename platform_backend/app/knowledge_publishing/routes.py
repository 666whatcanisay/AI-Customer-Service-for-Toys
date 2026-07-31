from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.knowledge_publishing.schemas import (
    ProductKnowledgeCheckCommand,
    ProductKnowledgePublicationReceiptList,
    ProductKnowledgePublicationResponse,
    ProductKnowledgePublishCommand,
)
from app.knowledge_publishing.service import ProductKnowledgePublishingService


router = APIRouter(
    prefix="/api/v1/admin/product-knowledge", tags=["product-knowledge-publishing"]
)


@router.post(
    "/products/{product_id}/ai-publications",
    response_model=ProductKnowledgePublicationResponse,
)
def publish_product_knowledge(
    product_id: str,
    command: ProductKnowledgePublishCommand,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> ProductKnowledgePublicationResponse:
    result, replayed = ProductKnowledgePublishingService(session).publish(
        product_id, command, idempotency_key
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.post(
    "/products/{product_id}/ai-publication-checks",
    response_model=ProductKnowledgePublicationResponse,
)
def check_product_knowledge_publication(
    product_id: str,
    command: ProductKnowledgeCheckCommand,
    session: Session = Depends(get_db),
) -> ProductKnowledgePublicationResponse:
    return ProductKnowledgePublishingService(session).check(product_id, command)


@router.get(
    "/products/{product_id}/ai-publication-receipts",
    response_model=ProductKnowledgePublicationReceiptList,
)
def list_product_knowledge_publication_receipts(
    product_id: str,
    session: Session = Depends(get_db),
) -> ProductKnowledgePublicationReceiptList:
    return ProductKnowledgePublishingService(session).list_receipts(product_id)
