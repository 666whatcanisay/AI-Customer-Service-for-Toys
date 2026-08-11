"""Audited management and projection services for platform identities."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.store_platform_bindings.models import StorePlatformBinding
from app.store_platform_bindings.schemas import (
    StorePlatformBindingCreateRequest,
    StorePlatformBindingListResponse,
    StorePlatformBindingProjection,
    StorePlatformBindingRevokeRequest,
    StorePlatformBindingStatus,
)
from app.test_catalog.models import TestStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def active_binding_projections_by_store(
    session: Session,
    store_ids: set[int],
) -> dict[int, list[StorePlatformBindingProjection]]:
    if not store_ids:
        return {}
    rows = session.execute(
        select(StorePlatformBinding, TestStore)
        .join(TestStore, TestStore.id == StorePlatformBinding.store_id)
        .where(
            StorePlatformBinding.store_id.in_(store_ids),
            StorePlatformBinding.status == StorePlatformBindingStatus.ACTIVE.value,
        )
        .order_by(
            StorePlatformBinding.store_id,
            StorePlatformBinding.platform,
            StorePlatformBinding.platform_store_id,
        )
    ).all()
    result: dict[int, list[StorePlatformBindingProjection]] = {
        store_id: [] for store_id in store_ids
    }
    for binding, store in rows:
        result[store.id].append(_projection(binding, store))
    return result


def _projection(
    binding: StorePlatformBinding,
    store: TestStore,
) -> StorePlatformBindingProjection:
    return StorePlatformBindingProjection(
        binding_id=binding.binding_id,
        store_id=store.id,
        store_code=store.store_code,
        store_name=store.store_name,
        platform=binding.platform,
        platform_store_id=binding.platform_store_id,
        status=StorePlatformBindingStatus(binding.status),
        verified_at=binding.verified_at,
        verified_by=binding.verified_by,
        created_at=binding.created_at,
        revoked_at=binding.revoked_at,
        revoked_by=binding.revoked_by,
        change_reason=binding.change_reason,
    )


class StorePlatformBindingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_store(
        self,
        store_ref: int,
        *,
        include_revoked: bool = True,
    ) -> StorePlatformBindingListResponse:
        store = self._store(store_ref)
        statement = select(StorePlatformBinding).where(
            StorePlatformBinding.store_id == store.id
        )
        if not include_revoked:
            statement = statement.where(
                StorePlatformBinding.status == StorePlatformBindingStatus.ACTIVE.value
            )
        bindings = self.session.scalars(
            statement.order_by(StorePlatformBinding.created_at.desc())
        ).all()
        items = [_projection(binding, store) for binding in bindings]
        return StorePlatformBindingListResponse(items=items, total=len(items))

    def create(
        self,
        store_ref: int,
        request: StorePlatformBindingCreateRequest,
        *,
        verified_by: str,
    ) -> StorePlatformBindingProjection:
        store = self._store(store_ref)
        existing = self.session.scalar(
            select(StorePlatformBinding).where(
                StorePlatformBinding.platform == request.platform,
                StorePlatformBinding.platform_store_id == request.platform_store_id,
                StorePlatformBinding.status == StorePlatformBindingStatus.ACTIVE.value,
            )
        )
        if existing is not None:
            if existing.store_id == store.id:
                return _projection(existing, store)
            raise AppError(
                "PLATFORM_STORE_ALREADY_BOUND",
                "该平台店铺账号已绑定到另一家AI-CS店铺",
                status_code=409,
            )
        now = _now()
        binding = StorePlatformBinding(
            binding_id=str(uuid4()),
            store_id=store.id,
            platform=request.platform,
            platform_store_id=request.platform_store_id,
            status=StorePlatformBindingStatus.ACTIVE.value,
            verified_at=now,
            verified_by=verified_by,
            created_at=now,
            change_reason=request.change_reason,
        )
        self.session.add(binding)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "PLATFORM_STORE_ALREADY_BOUND",
                "该平台店铺账号已被绑定，请刷新后重试",
                status_code=409,
            ) from None
        return _projection(binding, store)

    def revoke(
        self,
        store_ref: int,
        binding_id: str,
        request: StorePlatformBindingRevokeRequest,
        *,
        revoked_by: str,
    ) -> StorePlatformBindingProjection:
        store = self._store(store_ref)
        binding = self.session.get(StorePlatformBinding, binding_id)
        if binding is None or binding.store_id != store.id:
            raise AppError(
                "PLATFORM_STORE_BINDING_NOT_FOUND",
                "未找到平台店铺绑定",
                status_code=404,
            )
        if binding.status == StorePlatformBindingStatus.REVOKED.value:
            return _projection(binding, store)
        binding.status = StorePlatformBindingStatus.REVOKED.value
        binding.revoked_at = _now()
        binding.revoked_by = revoked_by
        binding.change_reason = request.change_reason
        self.session.commit()
        return _projection(binding, store)

    def _store(self, store_ref: int) -> TestStore:
        store = self.session.get(TestStore, store_ref)
        if store is None:
            raise AppError("OPERATION_STORE_NOT_FOUND", "未找到店铺", status_code=404)
        return store
