from sqlalchemy.orm import Session

from app.knowledge_publishing.canonical import build_canonical_product_knowledge
from app.knowledge_publishing.models import ProductKnowledgePublication
from app.knowledge_publishing.schemas import (
    AiKnowledgeStatus,
    AiKnowledgeSummary,
    EmbeddingStatus,
)
from app.test_catalog.models import TestProduct


def publication_summary(session: Session, product: TestProduct) -> AiKnowledgeSummary:
    canonical = build_canonical_product_knowledge(session, product)
    row = session.get(ProductKnowledgePublication, product.product_id)
    if row is None:
        return AiKnowledgeSummary(
            status=AiKnowledgeStatus.NOT_GENERATED,
            embedding_status=EmbeddingStatus.NOT_GENERATED,
            current_fingerprint=canonical.fingerprint,
            chunk_count=0,
            embedding_count=0,
        )
    status = AiKnowledgeStatus(row.status)
    if (
        status == AiKnowledgeStatus.PUBLISHED
        and row.indexed_fingerprint != canonical.fingerprint
    ):
        status = AiKnowledgeStatus.NEED_RESYNC
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
        current_fingerprint=canonical.fingerprint,
        indexed_fingerprint=row.indexed_fingerprint,
        active_collection=row.active_collection,
        chunk_count=row.chunk_count,
        embedding_count=row.embedding_count,
        updated_at=row.checked_at or row.updated_at,
        published_at=row.published_at,
        last_error_code=row.last_error_code,
    )
