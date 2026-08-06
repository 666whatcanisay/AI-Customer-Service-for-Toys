"""Validate browser ADMIN credentials against the C-line IAM authority."""

from typing import Any

import httpx
from fastapi import Header, HTTPException, Request, status


OPERATIONS_PERMISSIONS = frozenset({
    "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
    "ai_quality.view", "store.view", "feedback.view", "user.manage",
})


def require_operations_identity(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Fail closed unless C confirms an active operations-capable session."""
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AUTHENTICATION_REQUIRED",
        )
    settings = request.app.state.settings
    if not settings.platform_api_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM_SERVICE_UNAVAILABLE",
        )
    try:
        response = httpx.get(
            f"{settings.platform_api_base_url}/api/v1/auth/me",
            headers={"Authorization": authorization},
            timeout=settings.platform_api_timeout_seconds,
            trust_env=False,
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM_SERVICE_UNAVAILABLE",
        ) from None
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="AUTHENTICATION_FAILED",
        )
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM_SERVICE_UNAVAILABLE",
        )
    try:
        payload = response.json()
        user = payload["user"]
        permissions = frozenset(user["permissions"])
        must_change_password = user["must_change_password"]
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM_SERVICE_UNAVAILABLE",
        ) from None
    if not isinstance(must_change_password, bool):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IAM_SERVICE_UNAVAILABLE",
        )
    if must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PASSWORD_CHANGE_REQUIRED",
        )
    if permissions.isdisjoint(OPERATIONS_PERMISSIONS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AUTHORIZATION_DENIED",
        )
    return user
