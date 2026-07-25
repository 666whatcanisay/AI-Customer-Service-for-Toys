from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.service.rag_service import RAGService
from app.service.quality_observation import QualityObservationMetrics


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
        application.state.quality_observation_metrics = QualityObservationMetrics()
        application.state.initialization_error = None
        application.state.loading_message = "正在加载本地知识库..."

        def initialize_rag() -> None:
            try:
                service = factory(active_settings)
                service.warm_up()
                application.state.rag_service = service
                application.state.ready = True
                application.state.loading_message = "系统已就绪"
                logger.info("RAG 服务初始化完成")
            except Exception as exc:
                logger.exception("RAG 服务初始化失败")
                application.state.initialization_error = str(exc)
                application.state.loading_message = f"初始化失败：{exc}"

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
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "charset=" not in content_type:
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response

    application.include_router(router, prefix="/api")

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "message": "RAG AI 客服后端正在运行",
            "docs": "/docs",
            "health": "/api/health",
        }

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        first_error = exc.errors()[0] if exc.errors() else {}
        message = first_error.get("msg", "请求参数不正确")
        if "问题不能为空" in str(first_error):
            message = "问题不能为空"
        return JSONResponse(
            status_code=422,
            content={"success": False, "message": message, "data": None},
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        del request
        logger.exception("未处理的服务异常", exc_info=exc)
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
