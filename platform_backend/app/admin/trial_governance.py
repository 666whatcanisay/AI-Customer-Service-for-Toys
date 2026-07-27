"""Minimal C-internal trial-role context and content-free audit helpers.

The fixed actor mapping is deliberately not authentication.  It exists to
exercise least-privilege UI/API paths during the test-only pilot while formal
identity, authorization, retention, and production audit controls are absent.
"""

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.admin.trial_governance_models import TrialAuditEvent
from app.errors import AppError


class TrialRole(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    SUPPORT = "SUPPORT"


class TrialAuditReason(StrEnum):
    DAILY_OPERATIONS = "DAILY_OPERATIONS"
    CASE_REVIEW = "CASE_REVIEW"
    KNOWLEDGE_MAINTENANCE = "KNOWLEDGE_MAINTENANCE"
    GOVERNANCE_REVIEW = "GOVERNANCE_REVIEW"
    UNSPECIFIED = "UNSPECIFIED"


ROLE_CAPABILITIES: dict[TrialRole, tuple[str, ...]] = {
    TrialRole.ADMIN: (
        "operations.read",
        "sensitive-content.read",
        "store.write",
        "knowledge.import",
        "case.review",
        "feedback.confirm",
        "audit.read",
    ),
    TrialRole.OPERATOR: (
        "operations.read",
        "sensitive-content.read",
        "store.write",
        "knowledge.import",
        "case.review",
        "feedback.confirm",
    ),
    TrialRole.SUPPORT: ("operations.read",),
}


@dataclass(frozen=True, slots=True)
class TrialActor:
    actor_id: str
    role: TrialRole

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ROLE_CAPABILITIES[self.role]


_TRIAL_ACTORS = {
    "trial-admin": TrialActor("trial-admin", TrialRole.ADMIN),
    "trial-operator": TrialActor("trial-operator", TrialRole.OPERATOR),
    "trial-support": TrialActor("trial-support", TrialRole.SUPPORT),
}


def get_trial_actor(
    trial_actor_header: Annotated[
        str | None, Header(alias="X-Platform-Trial-Actor", max_length=64)
    ] = None,
) -> TrialActor:
    """Resolve one fixed pilot actor; a header is not proof of identity."""
    actor_id = (trial_actor_header or "trial-operator").strip().lower()
    actor = _TRIAL_ACTORS.get(actor_id)
    if actor is None:
        raise AppError(
            "TRIAL_ACTOR_UNKNOWN",
            "The requested trial actor is not available in this test-only environment.",
            status_code=403,
        )
    return actor


def require_trial_roles(*roles: TrialRole):
    """Return a FastAPI dependency for the small, server-enforced role matrix."""
    allowed = frozenset(roles)

    def dependency(actor: Annotated[TrialActor, Depends(get_trial_actor)]) -> TrialActor:
        if actor.role not in allowed:
            raise AppError(
                "TRIAL_ROLE_FORBIDDEN",
                "The selected trial role cannot perform this operation.",
                status_code=403,
            )
        return actor

    return dependency


def get_trial_reason(
    reason_header: Annotated[
        str | None, Header(alias="X-Platform-Reason", max_length=48)
    ] = None,
) -> TrialAuditReason:
    """Persist only controlled purpose codes so audit rows never store free text."""
    try:
        return TrialAuditReason((reason_header or TrialAuditReason.DAILY_OPERATIONS).strip().upper())
    except ValueError:
        return TrialAuditReason.UNSPECIFIED


def record_trial_audit_event(
    session: Session,
    *,
    actor: TrialActor,
    action: str,
    resource_type: str,
    resource_id: str,
    outcome: str,
    reason: TrialAuditReason,
    metadata: dict[str, int | str | bool] | None = None,
) -> TrialAuditEvent:
    """Append a bounded, content-free audit record to the caller's transaction."""
    event = TrialAuditEvent(
        actor_id=actor.actor_id,
        actor_role=actor.role.value,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason_code=reason.value,
        metadata_json=json.dumps(metadata or {}, sort_keys=True, separators=(",", ":")),
    )
    session.add(event)
    return event
