"""Validation helpers shared by B-facing C routes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customer_identity.models import CustomerUser, CustomerUserStoreBinding
from app.customer_identity.schemas import CustomerUserStatus
from app.errors import AppError
from app.test_catalog.models import TestStore


def bindings_for(session: Session, user: CustomerUser) -> list[CustomerUserStoreBinding]:
    return list(
        session.scalars(
            select(CustomerUserStoreBinding)
            .where(CustomerUserStoreBinding.customer_user_id == user.id)
            .order_by(CustomerUserStoreBinding.store_code)
        ).all()
    )


def validate_store_codes(session: Session, store_codes: list[str]) -> None:
    existing = set(
        session.scalars(select(TestStore.store_code).where(TestStore.store_code.in_(store_codes))).all()
    )
    missing = sorted(set(store_codes) - existing)
    if missing:
        raise AppError(
            "CUSTOMER_USER_STORE_BINDING_INVALID",
            "One or more selected stores do not exist in the current catalog.",
            status_code=422,
        )


def require_active_bound_user(session: Session, *, user_id: str, store_code: str) -> CustomerUser:
    user = session.scalar(select(CustomerUser).where(CustomerUser.user_id == user_id))
    if user is None:
        raise AppError("CUSTOMER_USER_NOT_FOUND", "The selected customer-service user was not found.", status_code=404)
    if user.status != CustomerUserStatus.ACTIVE:
        raise AppError("CUSTOMER_USER_DISABLED", "The selected customer-service user is disabled.", status_code=409)
    binding = session.scalar(
        select(CustomerUserStoreBinding).where(
            CustomerUserStoreBinding.customer_user_id == user.id,
            CustomerUserStoreBinding.store_code == store_code,
        )
    )
    if binding is None:
        raise AppError(
            "CUSTOMER_USER_STORE_FORBIDDEN",
            "The selected customer-service user is not bound to this store.",
            status_code=403,
        )
    return user
