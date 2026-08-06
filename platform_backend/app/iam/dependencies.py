"""FastAPI authentication and server-side authorization dependencies."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Callable

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.iam.models import User, UserSession
from app.iam.schemas import RoleName, UserStatus
from app.iam.security import hash_session_token
from app.iam.service import permissions_for_roles, role_names
from app.iam.models import UserStoreBinding
from app.test_catalog.models import TestStore


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    username: str
    display_name: str
    roles: frozenset[RoleName]
    permissions: frozenset[str]
    store_ids: frozenset[int]
    all_store_access: bool = False
    must_change_password: bool = False


def bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise AppError("AUTHENTICATION_REQUIRED", "Bearer authentication is required.", status_code=401)
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise AppError("AUTHENTICATION_REQUIRED", "Bearer authentication is required.", status_code=401)
    return token.strip()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_db),
) -> Principal:
    token = bearer_token(authorization)
    session_row = session.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )
    if session_row is None:
        raise AppError("AUTHENTICATION_FAILED", "Bearer credential is invalid.", status_code=401)
    if session_row.revoked_at is not None or _as_utc(session_row.expires_at) <= datetime.now(timezone.utc):
        raise AppError("SESSION_EXPIRED", "The session is expired or revoked.", status_code=401)
    user = session.get(User, session_row.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        raise AppError("SESSION_EXPIRED", "The session is expired or revoked.", status_code=401)
    roles = role_names(session, user.id)
    store_ids = frozenset(session.scalars(
        select(UserStoreBinding.store_id).where(UserStoreBinding.user_id == user.id)
    ).all())
    return Principal(
        user_id=user.id, username=user.username, display_name=user.display_name,
        roles=frozenset(roles), permissions=frozenset(permissions_for_roles(roles)),
        store_ids=store_ids,
        all_store_access=bool({RoleName.ADMIN, RoleName.OPERATOR}.intersection(roles)),
        must_change_password=user.must_change_password,
    )


def require_permission(permission: str) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.must_change_password:
            raise AppError(
                "PASSWORD_CHANGE_REQUIRED",
                "The initialization password must be replaced before using business APIs.",
                status_code=403,
            )
        if permission not in principal.permissions:
            raise AppError("AUTHORIZATION_DENIED", "This account lacks the required permission.", status_code=403)
        return principal
    return dependency


def require_any_permission(*permissions: str) -> Callable[..., Principal]:
    required = frozenset(permissions)
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.must_change_password:
            raise AppError(
                "PASSWORD_CHANGE_REQUIRED",
                "The initialization password must be replaced before using business APIs.",
                status_code=403,
            )
        if principal.permissions.isdisjoint(required):
            raise AppError("AUTHORIZATION_DENIED", "This account lacks the required permission.", status_code=403)
        return principal
    return dependency


require_workspace_access = require_permission("workspace.access")
require_ai_reply = require_permission("ai.reply")
require_feedback_submit = require_permission("feedback.submit")
require_user_manage = require_permission("user.manage")
require_customer_service_manage = require_permission("customer_service.manage")
require_operations_access = require_any_permission(
    "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
    "ai_quality.view", "store.view", "feedback.view"
)


def ensure_store_access(principal: Principal, store_id: int) -> None:
    if not principal.all_store_access and store_id not in principal.store_ids:
        raise AppError("AUTHORIZATION_DENIED", "This account is not bound to the requested Store.", status_code=403)


def ensure_store_code_access(session: Session, principal: Principal, store_code: str) -> None:
    if principal.all_store_access:
        return
    matching = set(session.scalars(
        select(TestStore.id).where(TestStore.store_code == store_code.strip())
    ).all())
    if not matching.intersection(principal.store_ids):
        raise AppError(
            "AUTHORIZATION_DENIED",
            "This account is not bound to the requested Store.",
            status_code=403,
        )


def effective_user_reference(principal: Principal, submitted: str) -> str:
    """Keep ADMIN fixture/import compatibility; user traffic is server-derived."""
    return submitted if principal.all_store_access else principal.user_id
