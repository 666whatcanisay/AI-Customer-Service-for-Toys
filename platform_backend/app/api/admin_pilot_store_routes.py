"""C-only trial-store setup and aggregate status APIs.

These routes deliberately expose only store configuration and aggregate status.
They never return raw import cells, customer-service content, identities, or
AI-efficiency events.
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.pilot_store_models import PilotStore
from app.admin.pilot_store_schemas import PilotStoreCreate, PilotStoreItem, PilotStoreListResponse
from app.admin.trial_governance import (
    TrialActor,
    TrialAuditReason,
    TrialRole,
    get_trial_reason,
    record_trial_audit_event,
    require_trial_roles,
)
from app.ai_feedback.models import AIResponseFeedback
from app.database import get_db
from app.errors import AppError
from app.experience_cases.models import CustomerExperienceCase
from app.ingestion.models import ImportBatch, StagedProductSku
from app.test_catalog.models import TestFaq, TestProduct, TestSafetyRule, TestSku


router = APIRouter(prefix="/api/v1/admin/pilot-stores", tags=["admin-pilot-stores"])


def _count(session: Session, statement: object) -> int:
    return int(session.scalar(statement) or 0)  # type: ignore[arg-type]


def _latest_import(session: Session, store_code: str) -> datetime | None:
    return session.scalar(
        select(func.max(ImportBatch.created_at)).where(ImportBatch.target_store_code == store_code)
    )


def _item(session: Session, store: PilotStore) -> PilotStoreItem:
    catalog_product_count = _count(
        session, select(func.count(TestProduct.product_id)).where(TestProduct.store_code == store.store_code)
    )
    catalog_sku_count = _count(
        session,
        select(func.count(TestSku.sku_id))
        .join(TestProduct, TestProduct.product_id == TestSku.product_id)
        .where(TestProduct.store_code == store.store_code),
    )
    staged_product_count = _count(
        session,
        select(func.count(func.distinct(StagedProductSku.product_code))).where(
            StagedProductSku.store_code == store.store_code
        ),
    )
    staged_sku_count = _count(
        session, select(func.count(StagedProductSku.id)).where(StagedProductSku.store_code == store.store_code)
    )
    faq_count = _count(session, select(func.count(TestFaq.faq_id)).where(TestFaq.store_code == store.store_code))
    safety_rule_count = _count(
        session, select(func.count(TestSafetyRule.rule_id)).where(TestSafetyRule.store_code == store.store_code)
    )
    experience_case_count = _count(
        session,
        select(func.count(CustomerExperienceCase.id)).where(CustomerExperienceCase.store_code == store.store_code),
    )
    ai_feedback_count = _count(
        session, select(func.count(AIResponseFeedback.id)).where(AIResponseFeedback.store_code == store.store_code)
    )
    product_count = catalog_product_count + staged_product_count
    knowledge_count = faq_count + safety_rule_count
    setup_status = (
        "NEEDS_PRODUCT_IMPORT"
        if product_count == 0
        else "NEEDS_KNOWLEDGE"
        if knowledge_count == 0
        else "OBSERVABLE"
    )
    return PilotStoreItem(
        store_code=store.store_code,
        store_name=store.store_name,
        platform=store.platform,
        created_at=store.created_at,
        setup_status=setup_status,
        catalog_product_count=catalog_product_count,
        catalog_sku_count=catalog_sku_count,
        staged_product_count=staged_product_count,
        staged_sku_count=staged_sku_count,
        faq_count=faq_count,
        safety_rule_count=safety_rule_count,
        experience_case_count=experience_case_count,
        ai_feedback_count=ai_feedback_count,
        latest_product_imported_at=_latest_import(session, store.store_code),
    )


@router.post("", response_model=PilotStoreItem, status_code=201)
def create_pilot_store(
    payload: PilotStoreCreate,
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> PilotStoreItem:
    """Create one trial-store setup record; this does not publish knowledge or enable AI."""
    store = PilotStore(**payload.model_dump())
    session.add(store)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise AppError(
            "PILOT_STORE_ALREADY_EXISTS", "A trial store already uses this store_code.", status_code=409
        ) from None
    record_trial_audit_event(
        session,
        actor=actor,
        action="PILOT_STORE_CREATE",
        resource_type="PILOT_STORE",
        resource_id=store.store_code,
        outcome="SUCCESS",
        reason=reason,
    )
    session.commit()
    session.refresh(store)
    return _item(session, store)


@router.get("", response_model=PilotStoreListResponse)
def list_pilot_stores(
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN, TrialRole.OPERATOR, TrialRole.SUPPORT)),
    session: Session = Depends(get_db),
) -> PilotStoreListResponse:
    stores = session.scalars(select(PilotStore).order_by(PilotStore.created_at.desc(), PilotStore.store_code)).all()
    return PilotStoreListResponse(items=[_item(session, store) for store in stores], total=len(stores))


def require_pilot_store(session: Session, store_code: str) -> PilotStore:
    """Shared read-only guard for target-bound imports."""
    store = session.scalar(select(PilotStore).where(PilotStore.store_code == store_code))
    if store is None:
        raise AppError("PILOT_STORE_NOT_FOUND", "The target trial store was not found.", status_code=404)
    return store
