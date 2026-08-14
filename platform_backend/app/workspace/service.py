"""C-owned Store context and deterministic Product/SKU resolver."""

import hashlib
import json
import unicodedata
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.customer_catalog.schemas import CustomerCatalogProduct, CustomerCatalogSku
from app.customer_catalog.service import CustomerAvailableCatalogService
from app.errors import AppError
from app.iam.dependencies import Principal, ensure_store_access
from app.iam.models import UserStoreBinding
from app.test_catalog.models import TestProduct, TestSku, TestStore
from app.workspace.models import ConversationContextResolution, utc_now
from app.workspace.schemas import (
    ChatContext,
    ContextResolutionRequest,
    ContextResolutionResponse,
    ProductCandidate,
    ResolutionAuditListResponse,
    ResolutionAuditProjection,
    ResolutionStatus,
    SkuCandidate,
    StoreContextProjection,
    WorkspaceContextResponse,
    WorkspaceContextState,
)


def _normalized(value: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value)
        if character.isalnum()
    )


def _conversation_digest(request: ContextResolutionRequest) -> tuple[str, str]:
    normalized_parts = [
        f"{message.role.value}:{_normalized(message.content)}"
        for message in request.conversation
    ]
    canonical = "\n".join(normalized_parts)
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _aliases_match(text: str, values: tuple[str | None, ...]) -> bool:
    aliases = {_normalized(value) for value in values if value}
    return any(alias and alias in text for alias in aliases)


def _product_projection(item: CustomerCatalogProduct) -> ProductCandidate:
    return ProductCandidate(
        product_id=item.product_id, display_name=item.product_name_display
    )


def _sku_projection(item: CustomerCatalogSku) -> SkuCandidate:
    return SkuCandidate(sku_id=item.sku_id, display_name=item.sku_name_display)


class StoreContextService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog = CustomerAvailableCatalogService(session)

    def _available_store_rows(self, principal: Principal) -> list[TestStore]:
        query = select(TestStore).order_by(TestStore.store_name, TestStore.id)
        if not principal.all_store_access:
            if not principal.store_ids:
                return []
            query = query.where(TestStore.id.in_(principal.store_ids))
        rows: list[TestStore] = []
        for store in self.session.scalars(query):
            projection = self.catalog.list_stores(frozenset({store.id}))
            if len(projection.items) == 1:
                rows.append(store)
        return rows

    def _default_store_id(self, user_id: str) -> int | None:
        return self.session.scalar(
            select(UserStoreBinding.store_id).where(
                UserStoreBinding.user_id == user_id,
                UserStoreBinding.is_default.is_(True),
            )
        )

    def _store_projection(
        self, store: TestStore, default_store_id: int | None
    ) -> StoreContextProjection:
        return StoreContextProjection(
            store_id=store.id,
            tenant_id=store.tenant_id,
            platform=store.platform,
            store_code=store.store_code,
            store_name=store.store_name,
            is_default=store.id == default_store_id,
        )

    def workspace_context(self, principal: Principal) -> WorkspaceContextResponse:
        rows = self._available_store_rows(principal)
        default_store_id = self._default_store_id(principal.user_id)
        projections = [self._store_projection(row, default_store_id) for row in rows]
        effective = next((item for item in projections if item.is_default), None)
        if effective is None and principal.all_store_access and len(projections) == 1:
            effective = projections[0]
        return WorkspaceContextResponse(
            user_id=principal.user_id,
            roles=sorted(principal.roles, key=lambda role: role.value),
            all_store_access=principal.all_store_access,
            state=(
                WorkspaceContextState.READY
                if effective is not None
                else WorkspaceContextState.STORE_SELECTION_REQUIRED
            ),
            stores=projections,
            effective_store=effective,
        )

    def _resolve_store(
        self, principal: Principal, requested_store_id: int | None
    ) -> TestStore | None:
        rows = self._available_store_rows(principal)
        by_id = {row.id: row for row in rows}
        if requested_store_id is not None:
            ensure_store_access(principal, requested_store_id)
            store = by_id.get(requested_store_id)
            if store is None:
                raise AppError(
                    "STORE_CONTEXT_UNAVAILABLE",
                    "The requested Store is not customer-service available.",
                    status_code=422,
                )
            return store
        default = by_id.get(self._default_store_id(principal.user_id))
        if default is not None:
            return default
        if principal.all_store_access and len(rows) == 1:
            return rows[0]
        return None

    def _persist(
        self,
        *,
        principal: Principal,
        digest: str,
        status: ResolutionStatus,
        store: TestStore | None,
        product_id: str | None,
        sku_id: str | None,
        product_candidates: list[ProductCandidate],
        sku_candidates: list[SkuCandidate],
        reason_code: str,
    ) -> ConversationContextResolution:
        row = ConversationContextResolution(
            id=str(uuid4()),
            user_id=principal.user_id,
            store_id=store.id if store is not None else None,
            conversation_hash=digest,
            status=status.value,
            product_id=product_id,
            sku_id=sku_id,
            product_candidate_ids_json=json.dumps(
                [item.product_id for item in product_candidates], ensure_ascii=True
            ),
            sku_candidate_ids_json=json.dumps(
                [item.sku_id for item in sku_candidates], ensure_ascii=True
            ),
            reason_code=reason_code,
            created_at=utc_now(),
        )
        self.session.add(row)
        self.session.commit()
        return row

    def _response(
        self,
        row: ConversationContextResolution,
        store: TestStore | None,
        product: ProductCandidate | None,
        sku: SkuCandidate | None,
        product_candidates: list[ProductCandidate],
        sku_candidates: list[SkuCandidate],
        default_store_id: int | None,
    ) -> ContextResolutionResponse:
        return ContextResolutionResponse(
            resolution_id=row.id,
            status=ResolutionStatus(row.status),
            store=(self._store_projection(store, default_store_id) if store else None),
            product=product,
            sku=sku,
            product_candidates=product_candidates,
            sku_candidates=sku_candidates,
            reason_code=row.reason_code,
            created_at=row.created_at,
        )

    def resolve(
        self, principal: Principal, request: ContextResolutionRequest
    ) -> ContextResolutionResponse:
        text, digest = _conversation_digest(request)
        default_store_id = self._default_store_id(principal.user_id)
        store = self._resolve_store(principal, request.store_id)
        if store is None:
            row = self._persist(
                principal=principal, digest=digest,
                status=ResolutionStatus.STORE_SELECTION_REQUIRED, store=None,
                product_id=None, sku_id=None, product_candidates=[], sku_candidates=[],
                reason_code="DEFAULT_STORE_MISSING",
            )
            return self._response(row, None, None, None, [], [], default_store_id)

        product_items = self.catalog.list_products(store.store_code).items
        product_by_id = {item.product_id: item for item in product_items}
        selected_product: CustomerCatalogProduct | None = None
        matched_products: list[CustomerCatalogProduct] = []
        if request.confirmed_product_id is not None:
            selected_product = product_by_id.get(request.confirmed_product_id)
            if selected_product is None:
                raise AppError(
                    "PRODUCT_CONFIRMATION_INVALID",
                    "The confirmed Product is outside the customer-service catalog.",
                    status_code=422,
                )
        else:
            matched_products = [
                item for item in product_items
                if _aliases_match(
                    text,
                    (item.product_id, item.product_name_official, item.product_name_display),
                )
            ]
            if len(matched_products) == 1:
                selected_product = matched_products[0]
            elif not matched_products and len(product_items) == 1:
                selected_product = product_items[0]

        if selected_product is None:
            candidates = [_product_projection(item) for item in matched_products]
            status = (
                ResolutionStatus.PRODUCT_CONFIRMATION_REQUIRED
                if len(candidates) > 1
                else ResolutionStatus.UNKNOWN
            )
            reason = "MULTIPLE_PRODUCT_MATCHES" if candidates else "PRODUCT_NOT_MATCHED"
            row = self._persist(
                principal=principal, digest=digest, status=status, store=store,
                product_id=None, sku_id=None, product_candidates=candidates,
                sku_candidates=[], reason_code=reason,
            )
            return self._response(row, store, None, None, candidates, [], default_store_id)

        product_projection = _product_projection(selected_product)
        sku_items = self.catalog.list_skus(selected_product.product_id).items
        sku_by_id = {item.sku_id: item for item in sku_items}
        selected_sku: CustomerCatalogSku | None = None
        matched_skus: list[CustomerCatalogSku] = []
        if request.confirmed_sku_id is not None:
            selected_sku = sku_by_id.get(request.confirmed_sku_id)
            if selected_sku is None:
                raise AppError(
                    "SKU_CONFIRMATION_INVALID",
                    "The confirmed SKU is outside the resolved Product.",
                    status_code=422,
                )
        else:
            matched_skus = [
                item for item in sku_items
                if _aliases_match(
                    text,
                    (item.sku_id, item.sku_code, item.sku_name_official, item.sku_name_display),
                )
            ]
            if len(matched_skus) == 1:
                selected_sku = matched_skus[0]
            elif not matched_skus and len(sku_items) == 1:
                selected_sku = sku_items[0]

        if selected_sku is None and sku_items:
            candidates = [
                _sku_projection(item)
                for item in (matched_skus if len(matched_skus) > 1 else sku_items)
            ]
            if len(sku_items) > 1 or len(matched_skus) > 1:
                row = self._persist(
                    principal=principal, digest=digest,
                    status=ResolutionStatus.SKU_CONFIRMATION_REQUIRED, store=store,
                    product_id=selected_product.product_id, sku_id=None,
                    product_candidates=[product_projection], sku_candidates=candidates,
                    reason_code="MULTIPLE_SKU_OPTIONS",
                )
                return self._response(
                    row, store, product_projection, None,
                    [product_projection], candidates, default_store_id,
                )

        sku_projection = _sku_projection(selected_sku) if selected_sku else None
        reason = "PRODUCT_AND_SKU_RESOLVED" if selected_sku else "PRODUCT_RESOLVED_NO_SKU"
        row = self._persist(
            principal=principal, digest=digest, status=ResolutionStatus.RESOLVED,
            store=store, product_id=selected_product.product_id,
            sku_id=selected_sku.sku_id if selected_sku else None,
            product_candidates=[product_projection],
            sku_candidates=[sku_projection] if sku_projection else [],
            reason_code=reason,
        )
        return self._response(
            row, store, product_projection, sku_projection,
            [product_projection], [sku_projection] if sku_projection else [],
            default_store_id,
        )

    def chat_context_for_resolution(
        self, principal: Principal, resolution_id: str
    ) -> ChatContext:
        row = self.session.get(ConversationContextResolution, resolution_id)
        if row is None or row.user_id != principal.user_id:
            raise AppError("RESOLUTION_NOT_FOUND", "Context resolution not found.", status_code=404)
        if row.status != ResolutionStatus.RESOLVED.value or row.store_id is None or row.product_id is None:
            raise AppError(
                "RESOLUTION_NOT_READY",
                "Product/SKU confirmation must finish before AI generation.",
                status_code=409,
            )
        store = self.session.get(TestStore, row.store_id)
        if store is None:
            raise AppError("RESOLUTION_NOT_READY", "Resolved catalog context is no longer available.", status_code=409)
        return self._validated_chat_context(
            principal,
            store_code=store.store_code,
            product_id=row.product_id,
            sku_id=row.sku_id,
            error_code="RESOLUTION_NOT_READY",
        )

    def chat_context_for_explicit_scope(
        self,
        principal: Principal,
        *,
        store_code: str,
        product_id: str,
        sku_id: str | None,
    ) -> ChatContext:
        """Resolve an operator-selected scope without persisting a resolution row."""
        return self._validated_chat_context(
            principal,
            store_code=store_code,
            product_id=product_id,
            sku_id=sku_id,
            error_code="REPLY_DEBUG_SCOPE_INVALID",
        )

    def _validated_chat_context(
        self,
        principal: Principal,
        *,
        store_code: str,
        product_id: str,
        sku_id: str | None,
        error_code: str,
    ) -> ChatContext:
        product = self.session.get(TestProduct, product_id)
        invalid_status = 409 if error_code == "RESOLUTION_NOT_READY" else 422
        if product is None:
            raise AppError(
                error_code,
                "Selected Product does not belong to the Store.",
                status_code=invalid_status,
            )
        store = self.session.scalar(
            select(TestStore).where(
                TestStore.store_code == store_code,
                TestStore.package_id == product.package_id,
            )
        )
        if (
            store is None
            or product is None
            or product.package_id != store.package_id
            or product.store_code != store.store_code
        ):
            raise AppError(
                error_code,
                "Selected Product does not belong to the Store.",
                status_code=invalid_status,
            )
        ensure_store_access(principal, store.id)
        if sku_id is not None:
            sku = self.session.get(TestSku, sku_id)
            if sku is None or sku.product_id != product.product_id or sku.package_id != product.package_id:
                raise AppError(
                    error_code,
                    "Selected SKU does not belong to the Product.",
                    status_code=invalid_status,
                )
        available_products = {
            item.product_id for item in self.catalog.list_products(store.store_code).items
        }
        if product.product_id not in available_products:
            raise AppError(error_code, "Selected Product is not customer-service available.", status_code=409)
        if sku_id is not None:
            available_skus = {
                item.sku_id for item in self.catalog.list_skus(product.product_id).items
            }
            if sku_id not in available_skus:
                raise AppError(error_code, "Selected SKU is not customer-service available.", status_code=409)
        return ChatContext(
            tenant_id=store.tenant_id, platform=store.platform,
            store_code=store.store_code, product_id=product.product_id, sku_id=sku_id,
        )

    def list_audits(
        self, *, user_id: str | None, status: ResolutionStatus | None, limit: int
    ) -> ResolutionAuditListResponse:
        conditions = []
        if user_id is not None:
            conditions.append(ConversationContextResolution.user_id == user_id)
        if status is not None:
            conditions.append(ConversationContextResolution.status == status.value)
        total = self.session.scalar(
            select(func.count()).select_from(ConversationContextResolution).where(*conditions)
        ) or 0
        rows = self.session.scalars(
            select(ConversationContextResolution).where(*conditions)
            .order_by(ConversationContextResolution.created_at.desc())
            .limit(limit)
        ).all()
        return ResolutionAuditListResponse(
            items=[
                ResolutionAuditProjection(
                    resolution_id=row.id, user_id=row.user_id, store_id=row.store_id,
                    status=ResolutionStatus(row.status), product_id=row.product_id,
                    sku_id=row.sku_id,
                    product_candidate_ids=json.loads(row.product_candidate_ids_json),
                    sku_candidate_ids=json.loads(row.sku_candidate_ids_json),
                    reason_code=row.reason_code, created_at=row.created_at,
                )
                for row in rows
            ],
            total=total,
        )
