from __future__ import annotations

import logging
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.gateway.contract import GatewayErrorCode, GatewayProblem
from app.gateway.routes import (
    gateway_http_problem,
    gateway_problem_response,
    gateway_router,
    server_runtime_router,
)
from app.gateway.service import GatewayRuntimeConfig, GatewayServer
from app.models.chat import FrozenChatContext
from app.service.ai_capability import INITIALIZATION_FAILED_CODE
from app.service.rag_service import RAGService


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def configure_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                settings.log_dir / "backend-app.log", encoding="utf-8"
            ),
        ],
        force=True,
    )


def create_app(
    settings: Settings | None = None,
    rag_factory: Callable[[Settings], RAGService] | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    factory = rag_factory or RAGService
    configure_logging(active_settings)
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.settings = active_settings
        application.state.ready = False
        application.state.rag_service = None
        application.state.initialization_error = None
        application.state.loading_message = "正在加载本地知识库..."
        application.state.gateway_server = None
        application.state.gateway_initialization_error = None

        if active_settings.gateway_enabled:
            try:
                def gateway_decision_provider(
                    question: str, context: FrozenChatContext
                ) -> dict:
                    if not getattr(application.state, "ready", False):
                        raise GatewayProblem(
                            status_code=503,
                            code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                            message="AI decision capability is unavailable.",
                        )
                    return application.state.rag_service.query(
                        question, context=context
                    )

                def gateway_readiness() -> tuple[bool, bool]:
                    ready = bool(getattr(application.state, "ready", False))
                    rag = getattr(application.state, "rag_service", None)
                    return ready, bool(rag and rag.model_configured)

                application.state.gateway_server = GatewayServer(
                    GatewayRuntimeConfig(
                        client_id=active_settings.gateway_client_id,
                        key_id=active_settings.gateway_key_id,
                        hmac_secret=active_settings.gateway_secret_bytes(),
                        state_path=active_settings.gateway_state_path,
                        clock_skew_seconds=active_settings.gateway_clock_skew_seconds,
                        nonce_ttl_seconds=active_settings.gateway_nonce_ttl_seconds,
                        decision_retention_seconds=(
                            active_settings.gateway_decision_retention_seconds
                        ),
                        decision_lease_seconds=(
                            active_settings.gateway_decision_lease_seconds
                        ),
                    ),
                    decision_provider=gateway_decision_provider,
                    readiness_provider=gateway_readiness,
                )
            except Exception as exc:
                application.state.gateway_initialization_error = (
                    "GATEWAY_CONFIGURATION_INVALID"
                )
                logger.error(
                    "Gateway Server initialization failed category=%s",
                    type(exc).__name__,
                )

        def initialize_rag() -> None:
            try:
                service = factory(active_settings)
                service.warm_up()
                application.state.rag_service = service
                application.state.ready = True
                application.state.loading_message = "系统已就绪"
                logger.info("RAG 服务初始化完成")
            except Exception as exc:
                logger.error(
                    "RAG service initialization failed error_type=%s",
                    type(exc).__name__,
                )
                application.state.initialization_error = INITIALIZATION_FAILED_CODE
                application.state.loading_message = (
                    "AI service initialization failed. Check service logs."
                )

        init_thread = threading.Thread(
            target=initialize_rag,
            name="rag-initializer",
            daemon=True,
        )
        init_thread.start()
        yield

        service = getattr(application.state, "rag_service", None)
        if service is not None:
            service.close()
        gateway_server = getattr(application.state, "gateway_server", None)
        if gateway_server is not None:
            gateway_server.close()

    application = FastAPI(
        title="独立 RAG AI 客服原型",
        description="普通文本 PDF 本地检索与 Qwen 生成式问答验证服务",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def add_json_charset(request: Request, call_next):
        submitted_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            submitted_request_id
            if _REQUEST_ID_PATTERN.fullmatch(submitted_request_id)
            else str(uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset=" not in content_type:
            response.headers["content-type"] = "application/json; charset=utf-8"
        response.headers["X-Request-ID"] = request_id
        return response

    application.include_router(router, prefix="/api")
    application.include_router(gateway_router)
    application.include_router(server_runtime_router)

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "title": "AI 能力中心服务接口",
            "service_type": "AI_SERVICE_API",
            "usage_note": "这是 AI 服务接口，不是运营后台。",
            "operations_console": "http://127.0.0.1:5174",
            "operations_console_note": "运营请前往 5174 的 AI 控制中心。",
            "product_overview": "/api/admin/ai/control-center/product-overview",
            "message": "RAG AI 客服后端正在运行",
            "docs": "/docs",
            "health": "/api/health",
        }

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if request.url.path.startswith("/gateway/v1"):
            return gateway_http_problem(
                request,
                status_code=422,
                code=GatewayErrorCode.SCHEMA_VALIDATION_FAILED,
                message="Gateway request failed schema validation.",
            )
        del request
        first_error = exc.errors()[0] if exc.errors() else {}
        message = first_error.get("msg", "请求参数不正确")
        if "问题不能为空" in str(first_error):
            message = "问题不能为空"
        return JSONResponse(
            status_code=422,
            content={"success": False, "message": message, "data": None},
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if request.url.path.startswith("/gateway/v1"):
            code = (
                GatewayErrorCode.METHOD_NOT_ALLOWED
                if exc.status_code == 405
                else GatewayErrorCode.RESOURCE_NOT_FOUND
                if exc.status_code == 404
                else GatewayErrorCode.INVALID_REQUEST
            )
            return gateway_http_problem(
                request,
                status_code=exc.status_code,
                code=code,
                message=(
                    "Gateway method is not allowed."
                    if exc.status_code == 405
                    else "Gateway resource was not found."
                    if exc.status_code == 404
                    else "Gateway request was rejected."
                ),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        if request.url.path.startswith("/gateway/v1"):
            logger.error(
                "Unhandled Gateway failure category=%s", type(exc).__name__
            )
            return gateway_problem_response(
                GatewayProblem(
                    status_code=500,
                    code=GatewayErrorCode.INTERNAL_ERROR,
                    message="Gateway Server encountered an internal error.",
                )
            )
        logger.error(
            "Unhandled request failure request_id=%s method=%s path=%s user_id=%s error_type=%s",
            getattr(request.state, "request_id", "unknown"),
            request.method,
            request.url.path,
            getattr(request.state, "authenticated_user_id", "anonymous"),
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "服务暂时不可用，请查看后端日志或稍后重试。",
                "data": None,
            },
        )

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    current = get_settings()
    uvicorn.run("app.main:app", host=current.host, port=current.port, reload=False)
