from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.gateway.contract import (
    CONTRACT_VERSION,
    DECISION_PATH,
    GATEWAY_ACCEPTED_MEDIA_TYPES,
    GATEWAY_MEDIA_TYPE,
    GATEWAY_PREFIX,
    HEALTH_PATH,
    MAX_DECISION_BODY_BYTES,
    DecisionRequest,
    GatewayErrorCode,
    GatewayProblem,
)
from app.gateway.service import GatewayServer
from app.gateway.runtime import (
    ServerRuntimeConsoleSnapshot,
    server_runtime_console_snapshot,
)
from app.service.iam_authorization import require_operations_or_internal_identity


gateway_router = APIRouter(prefix=GATEWAY_PREFIX, tags=["channel-gateway"])
server_runtime_router = APIRouter(tags=["server-runtime-console"])
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@server_runtime_router.get(
    "/api/admin/server-runtime",
    response_model=ServerRuntimeConsoleSnapshot,
    dependencies=[Depends(require_operations_or_internal_identity)],
)
def server_runtime_console(request: Request) -> ServerRuntimeConsoleSnapshot:
    return server_runtime_console_snapshot(request.app)


def _safe_header_identifier(request: Request, name: str) -> str | None:
    value = request.headers.get(name)
    if value and _IDENTIFIER_PATTERN.fullmatch(value):
        return value
    return None


def gateway_problem_response(problem: GatewayProblem) -> JSONResponse:
    headers = {"X-AI-CS-Contract-Version": CONTRACT_VERSION}
    if problem.request_id:
        headers["X-Request-ID"] = problem.request_id
    if problem.correlation_id:
        headers["X-Correlation-ID"] = problem.correlation_id
    if problem.retry_after_seconds is not None:
        headers["Retry-After"] = str(problem.retry_after_seconds)
    return JSONResponse(
        status_code=problem.status_code,
        content=problem.envelope().model_dump(mode="json"),
        headers=headers,
        media_type=f"{GATEWAY_MEDIA_TYPE}; charset=utf-8",
    )


def gateway_http_problem(
    request: Request,
    *,
    status_code: int,
    code: GatewayErrorCode,
    message: str,
) -> JSONResponse:
    return gateway_problem_response(
        GatewayProblem(
            status_code=status_code,
            code=code,
            message=message,
            request_id=_safe_header_identifier(request, "X-Request-ID"),
            correlation_id=_safe_header_identifier(request, "X-Correlation-ID"),
        )
    )


def _gateway_server(request: Request) -> GatewayServer:
    server = getattr(request.app.state, "gateway_server", None)
    if server is None:
        raise GatewayProblem(
            status_code=503,
            code=GatewayErrorCode.SERVICE_UNAVAILABLE,
            message="Gateway Server is not configured.",
            request_id=_safe_header_identifier(request, "X-Request-ID"),
            correlation_id=_safe_header_identifier(request, "X-Correlation-ID"),
        )
    return server


def _success_headers(
    *,
    request_id: str,
    correlation_id: str,
    replayed: bool,
) -> dict[str, str]:
    return {
        "X-AI-CS-Contract-Version": CONTRACT_VERSION,
        "X-Request-ID": request_id,
        "X-Correlation-ID": correlation_id,
        "Idempotency-Replayed": str(replayed).lower(),
    }


def _json_response(
    content: dict[str, Any],
    *,
    headers: dict[str, str],
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content=content,
        headers=headers,
        media_type=f"{GATEWAY_MEDIA_TYPE}; charset=utf-8",
    )


@gateway_router.get("/health", response_model=None)
async def gateway_health(request: Request) -> JSONResponse:
    body = await request.body()
    try:
        if body:
            raise GatewayProblem(
                status_code=400,
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Gateway health request body must be empty.",
                request_id=_safe_header_identifier(request, "X-Request-ID"),
                correlation_id=_safe_header_identifier(
                    request, "X-Correlation-ID"
                ),
            )
        server = _gateway_server(request)
        identity = server.authenticator.verify(
            method="GET",
            path=HEALTH_PATH,
            body=body,
            headers=request.headers,
        )
        health = server.health()
        return _json_response(
            health.model_dump(mode="json"),
            headers=_success_headers(
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
                replayed=False,
            ),
        )
    except GatewayProblem as problem:
        return gateway_problem_response(problem)


@gateway_router.post("/decisions", response_model=None)
async def gateway_decision(request: Request) -> JSONResponse:
    body = await request.body()
    try:
        request_id = _safe_header_identifier(request, "X-Request-ID")
        correlation_id = _safe_header_identifier(request, "X-Correlation-ID")
        if len(body) > MAX_DECISION_BODY_BYTES:
            raise GatewayProblem(
                status_code=413,
                code=GatewayErrorCode.PAYLOAD_TOO_LARGE,
                message="Gateway decision payload is too large.",
                request_id=request_id,
                correlation_id=correlation_id,
            )
        media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if media_type not in GATEWAY_ACCEPTED_MEDIA_TYPES:
            raise GatewayProblem(
                status_code=415,
                code=GatewayErrorCode.UNSUPPORTED_MEDIA_TYPE,
                message="Gateway media type is not supported.",
                request_id=request_id,
                correlation_id=correlation_id,
            )

        server = _gateway_server(request)
        identity = server.authenticator.verify(
            method="POST",
            path=DECISION_PATH,
            body=body,
            headers=request.headers,
        )
        try:
            raw_payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayProblem(
                status_code=400,
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Gateway request body is not valid JSON.",
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
            ) from exc
        if not isinstance(raw_payload, dict):
            raise GatewayProblem(
                status_code=400,
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Gateway request body must be an object.",
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
            )
        if raw_payload.get("contract_version") != CONTRACT_VERSION:
            raise GatewayProblem(
                status_code=406,
                code=GatewayErrorCode.UNSUPPORTED_CONTRACT_VERSION,
                message="Gateway contract version is not supported.",
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
            )
        try:
            decision_request = DecisionRequest.model_validate_json(body)
        except ValidationError as exc:
            first = exc.errors(include_url=False)[0] if exc.errors() else {}
            location = ".".join(str(item) for item in first.get("loc", ()))
            raise GatewayProblem(
                status_code=422,
                code=GatewayErrorCode.SCHEMA_VALIDATION_FAILED,
                message="Gateway DecisionRequest failed schema validation.",
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
                details={"field": location or "request"},
            ) from exc
        if (
            decision_request.request_id != identity.request_id
            or decision_request.correlation_id != identity.correlation_id
            or decision_request.idempotency_key != identity.idempotency_key
        ):
            raise GatewayProblem(
                status_code=400,
                code=GatewayErrorCode.INVALID_REQUEST,
                message="Gateway header and body identity do not match.",
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
            )

        response, replayed = server.decide(identity, decision_request)
        return _json_response(
            response.model_dump(mode="json"),
            headers=_success_headers(
                request_id=identity.request_id,
                correlation_id=identity.correlation_id,
                replayed=replayed,
            ),
        )
    except GatewayProblem as problem:
        return gateway_problem_response(problem)
