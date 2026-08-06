"""FastAPI entrypoint for the C Platform API and production IAM boundary."""

from fastapi import Depends, FastAPI, Request
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
from app.api.knowledge_material_routes import (
    admin_router as knowledge_material_admin_router,
    ai_quality_router as knowledge_quality_router,
    customer_router as customer_knowledge_status_router,
)
from app.api.import_routes import router as import_router
from app.api.test_catalog_routes import (
    internal_router as test_knowledge_internal_router,
    router as test_catalog_router,
)
from app.product_knowledge.routes import router as product_knowledge_router
from app.operation_management.routes import router as operation_management_router
from app.customer_feedback_loop.routes import (
    admin_router as customer_feedback_loop_admin_router,
    customer_router as customer_feedback_loop_customer_router,
)
from app.product_knowledge_import.routes import router as product_knowledge_import_router
from app.customer_catalog.routes import (
    admin_router as customer_catalog_admin_router,
    customer_router as customer_catalog_customer_router,
)
from app.knowledge_publishing.routes import router as knowledge_publishing_router
from app.errors import (
    AppError,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware import request_id_middleware
from app.internal_auth import require_internal_service_identity
from app.iam.dependencies import (
    require_feedback_submit,
    require_operations_access,
    require_workspace_access,
)
from app.iam.routes import admin_router as iam_admin_router, auth_router
from app.workspace.routes import admin_router as workspace_admin_router, router as workspace_router
from app.desktop_agent.routes import (
    admin_router as desktop_workflow_admin_router,
    router as desktop_agent_router,
)

def create_app(settings_override: Settings | None = None) -> FastAPI:
    settings = settings_override or get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url=None,
        redoc_url=None,
    )
    application.state.settings = settings
    application.middleware("http")(request_id_middleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        # B submits the frozen feedback v1 Idempotency-Key header from the
        # browser. Keep the CORS policy explicit; do not widen it to a
        # wildcard just to accommodate this preflight.
        allow_headers=[
            "Accept", "Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"
        ],
        expose_headers=["X-Request-ID", "Idempotency-Replayed"],
    )
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.add_exception_handler(AppError, app_exception_handler)

    operations_dependencies = [Depends(require_operations_access)]
    workspace_dependencies = [Depends(require_workspace_access)]
    feedback_dependencies = [Depends(require_feedback_submit)]

    application.include_router(auth_router)
    application.include_router(iam_admin_router)
    application.include_router(workspace_router)
    application.include_router(workspace_admin_router)
    application.include_router(desktop_agent_router)
    application.include_router(desktop_workflow_admin_router)
    application.include_router(import_router, dependencies=operations_dependencies)
    application.include_router(test_catalog_router, dependencies=operations_dependencies)
    # Frozen A RAG bootstrap reads these two loopback-only legacy projections.
    # They remain isolated from browser import/management routes so RAG logic is
    # not changed by R016.
    application.include_router(
        test_knowledge_internal_router,
        dependencies=[Depends(require_internal_service_identity)],
    )
    application.include_router(customer_suggestion_router, dependencies=feedback_dependencies)
    application.include_router(admin_suggestion_router, dependencies=operations_dependencies)
    application.include_router(customer_experience_case_router, dependencies=feedback_dependencies)
    application.include_router(customer_ai_feedback_router, dependencies=feedback_dependencies)
    application.include_router(customer_feedback_loop_customer_router, dependencies=feedback_dependencies)
    application.include_router(admin_experience_case_router, dependencies=operations_dependencies)
    application.include_router(ai_optimization_router, dependencies=operations_dependencies)
    application.include_router(admin_ai_feedback_router, dependencies=operations_dependencies)
    application.include_router(ai_quality_router, dependencies=operations_dependencies)
    application.include_router(knowledge_material_admin_router, dependencies=operations_dependencies)
    application.include_router(knowledge_quality_router, dependencies=operations_dependencies)
    application.include_router(customer_knowledge_status_router, dependencies=workspace_dependencies)
    application.include_router(product_knowledge_router, dependencies=operations_dependencies)
    application.include_router(knowledge_publishing_router, dependencies=operations_dependencies)
    application.include_router(product_knowledge_import_router, dependencies=operations_dependencies)
    application.include_router(operation_management_router, dependencies=operations_dependencies)
    application.include_router(customer_catalog_customer_router, dependencies=workspace_dependencies)
    application.include_router(customer_catalog_admin_router, dependencies=operations_dependencies)
    application.include_router(customer_feedback_loop_admin_router, dependencies=operations_dependencies)
    application.include_router(admin_router, dependencies=operations_dependencies)

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
