"""FastAPI entrypoint for the minimal C-line platform baseline."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.api.admin_routes import router as admin_router
from app.api.admin_suggestion_routes import router as admin_suggestion_router
from app.api.customer_suggestion_routes import router as customer_suggestion_router
from app.api.customer_experience_case_routes import router as customer_experience_case_router
from app.api.customer_ai_feedback_routes import router as customer_ai_feedback_router
from app.api.admin_experience_case_routes import (
    admin_router as admin_experience_case_router,
    ai_optimization_router,
)
from app.api.admin_ai_feedback_routes import (
    admin_router as admin_ai_feedback_router,
    ai_quality_router,
)
from app.api.import_routes import router as import_router
from app.api.test_catalog_routes import router as test_catalog_router
from app.errors import (
    AppError,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware import request_id_middleware

def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url=None,
        redoc_url=None,
    )
    application.middleware("http")(request_id_middleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.add_exception_handler(AppError, app_exception_handler)
    application.include_router(import_router)
    application.include_router(test_catalog_router)
    application.include_router(customer_suggestion_router)
    application.include_router(admin_suggestion_router)
    application.include_router(customer_experience_case_router)
    application.include_router(customer_ai_feedback_router)
    application.include_router(admin_experience_case_router)
    application.include_router(ai_optimization_router)
    application.include_router(admin_ai_feedback_router)
    application.include_router(ai_quality_router)
    application.include_router(admin_router)

    @application.get("/health")
    async def health(request: Request) -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.service_name,
            "version": settings.version,
            "request_id": request.state.request_id,
        }

    return application


app = create_app()
