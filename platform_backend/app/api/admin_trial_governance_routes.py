"""C-internal governance visibility for the test-only operations pilot."""

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.trial_governance import (
    TrialActor,
    TrialAuditReason,
    TrialRole,
    get_trial_actor,
    get_trial_reason,
    record_trial_audit_event,
    require_trial_roles,
)
from app.admin.trial_governance_models import TrialAuditEvent
from app.admin.trial_governance_schemas import (
    TrialAuditEventItem,
    TrialAuditEventListResponse,
    TrialGovernanceStatus,
)
from app.database import get_db


router = APIRouter(prefix="/api/v1/admin/trial-governance", tags=["admin-trial-governance"])


def _metadata(value: str) -> dict[str, int | str | bool]:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {
        str(key): item
        for key, item in decoded.items()
        if isinstance(item, (str, int, bool))
    }


@router.get("", response_model=TrialGovernanceStatus)
def get_trial_governance_status(
    actor: TrialActor = Depends(get_trial_actor),
) -> TrialGovernanceStatus:
    """Describe the current pilot context without claiming production controls."""
    return TrialGovernanceStatus(
        actor_id=actor.actor_id,
        role=actor.role.value,
        capabilities=list(actor.capabilities),
    )


@router.get("/audit-events", response_model=TrialAuditEventListResponse)
def list_trial_audit_events(
    action: str | None = Query(default=None, max_length=64),
    outcome: str | None = Query(default=None, max_length=24),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    actor: TrialActor = Depends(require_trial_roles(TrialRole.ADMIN)),
    reason: TrialAuditReason = Depends(get_trial_reason),
    session: Session = Depends(get_db),
) -> TrialAuditEventListResponse:
    """Only the trial administrator may inspect content-free audit metadata."""
    statement = select(TrialAuditEvent)
    if action:
        statement = statement.where(TrialAuditEvent.action == action)
    if outcome:
        statement = statement.where(TrialAuditEvent.outcome == outcome)
    total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    items = session.scalars(
        statement.order_by(TrialAuditEvent.occurred_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    record_trial_audit_event(
        session,
        actor=actor,
        action="AUDIT_LOG_VIEW",
        resource_type="TRIAL_AUDIT_EVENT",
        resource_id="collection",
        outcome="SUCCESS",
        reason=reason,
        metadata={"returned_count": len(items)},
    )
    session.commit()
    return TrialAuditEventListResponse(
        items=[
            TrialAuditEventItem(
                id=item.id,
                occurred_at=item.occurred_at,
                actor_id=item.actor_id,
                actor_role=item.actor_role,
                action=item.action,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                outcome=item.outcome,
                reason_code=item.reason_code,
                metadata=_metadata(item.metadata_json),
            )
            for item in items
        ],
        total=total,
        page=page,
        size=size,
    )
