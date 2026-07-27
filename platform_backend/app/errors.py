"""Unified JSON error responses for the platform service."""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
        "request_id": _request_id(request),
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request,
            code=f"HTTP_{exc.status_code}",
            message=message,
        ),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    experience_case_path = request.url.path.startswith(
        (
            "/api/v1/customer-experience-cases",
            "/api/v1/admin/customer-experience-cases",
            "/api/v1/admin/ai-optimization",
        )
    )
    ai_feedback_path = request.url.path.startswith(
        (
            "/api/v1/ai-response-feedback",
            "/api/v1/admin/ai-response-feedback",
            "/api/v1/admin/ai-quality",
        )
    )
    customer_efficiency_path = request.url.path.startswith(
        (
            "/api/v1/customer-efficiency-events",
            "/api/v1/admin/ai-quality/customer-efficiency",
            "/api/v1/admin/customer-efficiency",
        )
    )
    analysis_output_invalid = (
        request.url.path == "/api/v1/admin/ai-quality/analysis-results"
        and any(
            len(error.get("loc", ())) > 1
            and error["loc"][1] in {"analysis", "suggestions"}
            for error in exc.errors()
        )
    )
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request,
            code=(
                "AI_RESPONSE_FEEDBACK_ANALYSIS_OUTPUT_INVALID"
                if analysis_output_invalid
                else "AI_RESPONSE_FEEDBACK_VALIDATION_FAILED"
                if ai_feedback_path
                else "CUSTOMER_EFFICIENCY_VALIDATION_FAILED"
                if customer_efficiency_path
                else "EXPERIENCE_CASE_VALIDATION_FAILED"
                if experience_case_path
                else "VALIDATION_ERROR"
            ),
            message="The request is invalid."
            if ai_feedback_path or customer_efficiency_path
            else "Request validation failed",
            details=exc.errors(),
        ),
    )


async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(request, code=exc.code, message=exc.message),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request,
            code="INTERNAL_ERROR",
            message="Internal server error",
        ),
    )
