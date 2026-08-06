"""Store-scoped facade over the unchanged loopback A chat capability."""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import AppError
from app.iam.dependencies import Principal, ensure_store_access, require_ai_reply
from app.test_catalog.models import TestProduct, TestSku, TestStore


class ChatContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=96)
    platform: str = Field(min_length=1, max_length=32)
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str = Field(min_length=1, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)


class WorkspaceChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    context: ChatContext


router = APIRouter(prefix="/api/v1/workspace", tags=["authenticated-workspace"])


def _validate_scope(session: Session, principal: Principal, context: ChatContext) -> None:
    stores = list(session.scalars(select(TestStore).where(
        TestStore.tenant_id == context.tenant_id,
        TestStore.platform == context.platform,
        TestStore.store_code == context.store_code,
    )))
    permitted = [store for store in stores if principal.all_store_access or store.id in principal.store_ids]
    if len(permitted) != 1:
        raise AppError("AUTHORIZATION_DENIED", "The requested Store is not bound to this account.", status_code=403)
    store = permitted[0]
    ensure_store_access(principal, store.id)
    product = session.get(TestProduct, context.product_id)
    if product is None or product.package_id != store.package_id or product.store_code != store.store_code:
        raise AppError("AUTHORIZATION_DENIED", "The requested Product is outside the bound Store.", status_code=403)
    if context.sku_id is not None:
        sku = session.get(TestSku, context.sku_id)
        if sku is None or sku.package_id != product.package_id or sku.product_id != product.product_id:
            raise AppError("AUTHORIZATION_DENIED", "The requested SKU is outside the bound Store.", status_code=403)


def _proxy(method: str, path: str, payload: dict | None = None) -> JSONResponse:
    settings = get_settings()
    try:
        response = httpx.request(
            method, f"{settings.ai_service_base_url}{path}", json=payload,
            timeout=settings.ai_service_timeout_seconds,
        )
        content = response.json()
    except (httpx.HTTPError, ValueError):
        raise AppError("AI_SERVICE_UNAVAILABLE", "AI service is unavailable.", status_code=503) from None
    return JSONResponse(status_code=response.status_code, content=content)


@router.get("/ai-health")
def ai_health(_: Principal = Depends(require_ai_reply)) -> JSONResponse:
    return _proxy("GET", "/api/health")


@router.post("/ai-replies")
def ai_reply(
    request: WorkspaceChatRequest,
    principal: Principal = Depends(require_ai_reply),
    session: Session = Depends(get_db),
) -> JSONResponse:
    _validate_scope(session, principal, request.context)
    return _proxy("POST", "/api/chat", request.model_dump())
