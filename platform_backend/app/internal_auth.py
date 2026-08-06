"""Authentication boundary for loopback service-to-service APIs."""

import hmac

from fastapi import Header, Request

from app.config import Settings
from app.errors import AppError


def require_internal_service_identity(
    request: Request,
    service_token: str | None = Header(default=None, alias="X-AI-CS-Service-Token"),
) -> str:
    settings: Settings = request.app.state.settings
    try:
        expected = settings.internal_service_token()
    except ValueError as exc:
        raise AppError(
            "INTERNAL_SERVICE_AUTH_UNAVAILABLE",
            "Internal service authentication is unavailable.",
            status_code=503,
        ) from exc
    if service_token is None or not hmac.compare_digest(service_token, expected):
        raise AppError(
            "INTERNAL_SERVICE_AUTHENTICATION_FAILED",
            "Internal service authentication failed.",
            status_code=401,
        )
    return "ai-cs-core"
