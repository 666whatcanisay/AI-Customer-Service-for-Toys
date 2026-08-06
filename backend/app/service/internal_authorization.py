"""Authenticate calls made by the platform service to loopback A APIs."""

import hmac

from fastapi import Header, HTTPException, Request, status


def require_internal_service_identity(
    request: Request,
    service_token: str | None = Header(default=None, alias="X-AI-CS-Service-Token"),
) -> str:
    try:
        expected = request.app.state.settings.internal_service_token()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_SERVICE_AUTH_UNAVAILABLE",
        ) from exc
    if service_token is None or not hmac.compare_digest(service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="INTERNAL_SERVICE_AUTHENTICATION_FAILED",
        )
    request.state.authenticated_user_id = "platform-backend"
    return "platform-backend"
