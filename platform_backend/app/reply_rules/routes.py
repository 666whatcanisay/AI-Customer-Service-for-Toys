from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.iam.dependencies import Principal, require_permission
from app.reply_rules.schemas import (
    ReplyRuleCreate,
    ReplyRuleDraftUpdate,
    ReplyRuleEventListResponse,
    ReplyRuleListResponse,
    ReplyRuleProjection,
    ReplyRuleReview,
    ReplyRuleRevisionCreate,
    ReplyRuleSnapshotPublicationResponse,
    ReplyRuleSnapshotPublishCommand,
    ReplyRuleSnapshotReceiptListResponse,
    ReplyRuleStatus,
    ReplyRuleTransition,
    ReplyRuleWithdrawalCommand,
)
from app.reply_rules.publication import ReplyRulePublicationService
from app.reply_rules.service import ReplyRuleService


router = APIRouter(prefix="/api/v1/admin/reply-rules", tags=["reply-rules"])
_require_knowledge_manage = require_permission("knowledge.manage")


def _service(session: Session, principal: Principal) -> ReplyRuleService:
    return ReplyRuleService(session, principal.user_id)


def _publication_service(
    session: Session, principal: Principal
) -> ReplyRulePublicationService:
    return ReplyRulePublicationService(session, principal.user_id)


@router.post("", response_model=ReplyRuleProjection, status_code=201)
def create_reply_rule(
    payload: ReplyRuleCreate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleProjection:
    return _service(session, principal).create(payload)


@router.get("", response_model=ReplyRuleListResponse)
def list_reply_rules(
    status: ReplyRuleStatus | None = Query(default=None),
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=96),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleListResponse:
    return _service(session, principal).list(
        status=status,
        store_code=store_code,
        product_id=product_id,
        page=page,
        size=size,
    )


@router.post("/publications", response_model=ReplyRuleSnapshotPublicationResponse)
def publish_reply_rule_snapshot(
    payload: ReplyRuleSnapshotPublishCommand,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleSnapshotPublicationResponse:
    result, replayed = _publication_service(session, principal).publish(
        payload, idempotency_key
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.get(
    "/publication-receipts", response_model=ReplyRuleSnapshotReceiptListResponse
)
def list_reply_rule_publication_receipts(
    tenant_id: str = Query(min_length=1, max_length=96),
    platform: str = Query(min_length=1, max_length=32),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleSnapshotReceiptListResponse:
    return _publication_service(session, principal).list_receipts(
        tenant_id.strip(), platform.strip()
    )


@router.get("/{rule_id}/versions/{rule_version}", response_model=ReplyRuleProjection)
def get_reply_rule(
    rule_id: str,
    rule_version: int,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleProjection:
    return _service(session, principal).get(rule_id, rule_version)


@router.put("/{rule_id}/versions/{rule_version}", response_model=ReplyRuleProjection)
def update_reply_rule_draft(
    rule_id: str,
    rule_version: int,
    payload: ReplyRuleDraftUpdate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleProjection:
    return _service(session, principal).update_draft(rule_id, rule_version, payload)


@router.post(
    "/{rule_id}/versions/{rule_version}/submit-review",
    response_model=ReplyRuleProjection,
)
def submit_reply_rule_review(
    rule_id: str,
    rule_version: int,
    payload: ReplyRuleTransition,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleProjection:
    return _service(session, principal).submit_review(
        rule_id, rule_version, payload.reason
    )


@router.post(
    "/{rule_id}/versions/{rule_version}/review",
    response_model=ReplyRuleProjection,
)
def review_reply_rule(
    rule_id: str,
    rule_version: int,
    payload: ReplyRuleReview,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleProjection:
    return _service(session, principal).review(
        rule_id, rule_version, payload.decision, payload.reason
    )


@router.post("/{rule_id}/versions", response_model=ReplyRuleProjection, status_code=201)
def create_reply_rule_revision(
    rule_id: str,
    payload: ReplyRuleRevisionCreate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleProjection:
    return _service(session, principal).create_revision(rule_id, payload.reason)


@router.post(
    "/{rule_id}/versions/{rule_version}/withdraw",
    response_model=ReplyRuleSnapshotPublicationResponse,
)
def withdraw_reply_rule(
    rule_id: str,
    rule_version: int,
    payload: ReplyRuleWithdrawalCommand,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleSnapshotPublicationResponse:
    result, replayed = _publication_service(session, principal).withdraw(
        rule_id, rule_version, payload.reason, idempotency_key
    )
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result


@router.get("/{rule_id}/events", response_model=ReplyRuleEventListResponse)
def list_reply_rule_events(
    rule_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(_require_knowledge_manage),
) -> ReplyRuleEventListResponse:
    return _service(session, principal).events(rule_id)
