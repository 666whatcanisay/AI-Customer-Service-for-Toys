"""Trial identity selection and C Admin user-management routes.

These routes deliberately do not authenticate callers.  They support a local
internal pilot identity selector and must not be represented as production
authorization.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customer_identity.models import CustomerUser, CustomerUserStoreBinding
from app.customer_identity.schemas import (
    CustomerUserListResponse,
    CustomerUserResponse,
    CustomerUserStatus,
    CustomerUserStatusUpdate,
    CustomerUserStoreBindingResponse,
    CustomerUserWrite,
)
from app.customer_identity.service import bindings_for, validate_store_codes
from app.database import get_db
from app.errors import AppError


customer_router = APIRouter(prefix="/api/v1/customer-identities", tags=["customer-identities"])
admin_router = APIRouter(prefix="/api/v1/admin/customer-users", tags=["admin-customer-users"])


def _response(session: Session, user: CustomerUser) -> CustomerUserResponse:
    bindings = bindings_for(session, user)
    return CustomerUserResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        default_store_code=user.default_store_code,
        store_bindings=[
            CustomerUserStoreBindingResponse(
                store_code=binding.store_code, is_default=binding.store_code == user.default_store_code
            )
            for binding in bindings
        ],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _user_or_404(session: Session, user_id: str) -> CustomerUser:
    user = session.scalar(select(CustomerUser).where(CustomerUser.user_id == user_id))
    if user is None:
        raise AppError("CUSTOMER_USER_NOT_FOUND", "Customer-service user was not found.", status_code=404)
    return user


def _replace_bindings(session: Session, user: CustomerUser, payload: CustomerUserWrite) -> None:
    validate_store_codes(session, payload.store_codes)
    session.query(CustomerUserStoreBinding).filter(
        CustomerUserStoreBinding.customer_user_id == user.id
    ).delete(synchronize_session=False)
    for store_code in payload.store_codes:
        session.add(CustomerUserStoreBinding(customer_user_id=user.id, store_code=store_code))
    user.display_name = payload.display_name
    user.role = payload.role
    user.default_store_code = payload.default_store_code


@customer_router.get("", response_model=CustomerUserListResponse)
def list_selectable_customer_identities(
    session: Session = Depends(get_db),
) -> CustomerUserListResponse:
    """Return active identities only; B must never create identities locally."""
    users = session.scalars(
        select(CustomerUser)
        .where(CustomerUser.status == CustomerUserStatus.ACTIVE)
        .order_by(CustomerUser.display_name, CustomerUser.user_id)
    ).all()
    return CustomerUserListResponse(items=[_response(session, user) for user in users], total=len(users))


@customer_router.get("/{user_id}", response_model=CustomerUserResponse)
def get_selectable_customer_identity(
    user_id: str,
    session: Session = Depends(get_db),
) -> CustomerUserResponse:
    user = _user_or_404(session, user_id)
    if user.status != CustomerUserStatus.ACTIVE:
        raise AppError("CUSTOMER_USER_DISABLED", "Customer-service user is disabled.", status_code=409)
    return _response(session, user)


@admin_router.get("", response_model=CustomerUserListResponse)
def list_admin_customer_users(
    status: CustomerUserStatus | None = Query(default=None),
    session: Session = Depends(get_db),
) -> CustomerUserListResponse:
    statement = select(CustomerUser).order_by(CustomerUser.updated_at.desc(), CustomerUser.user_id)
    if status is not None:
        statement = statement.where(CustomerUser.status == status)
    users = session.scalars(statement).all()
    return CustomerUserListResponse(items=[_response(session, user) for user in users], total=len(users))


@admin_router.post("", response_model=CustomerUserResponse, status_code=201)
def create_customer_user(
    payload: CustomerUserWrite,
    session: Session = Depends(get_db),
) -> CustomerUserResponse:
    validate_store_codes(session, payload.store_codes)
    user = CustomerUser(
        display_name=payload.display_name,
        role=payload.role,
        status=CustomerUserStatus.ACTIVE,
        default_store_code=payload.default_store_code,
    )
    session.add(user)
    session.flush()
    for store_code in payload.store_codes:
        session.add(CustomerUserStoreBinding(customer_user_id=user.id, store_code=store_code))
    session.commit()
    session.refresh(user)
    return _response(session, user)


@admin_router.put("/{user_id}", response_model=CustomerUserResponse)
def update_customer_user(
    user_id: str,
    payload: CustomerUserWrite,
    session: Session = Depends(get_db),
) -> CustomerUserResponse:
    user = _user_or_404(session, user_id)
    _replace_bindings(session, user, payload)
    session.commit()
    session.refresh(user)
    return _response(session, user)


@admin_router.post("/{user_id}/status", response_model=CustomerUserResponse)
def update_customer_user_status(
    user_id: str,
    payload: CustomerUserStatusUpdate,
    session: Session = Depends(get_db),
) -> CustomerUserResponse:
    user = _user_or_404(session, user_id)
    user.status = payload.status
    session.commit()
    session.refresh(user)
    return _response(session, user)
