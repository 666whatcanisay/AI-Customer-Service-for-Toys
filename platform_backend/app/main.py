"""FastAPI entrypoint for the minimal C-line platform baseline."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
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

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url=None,
    redoc_url=None,
)
app.middleware("http")(request_id_middleware)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.add_exception_handler(AppError, app_exception_handler)
app.include_router(import_router)
app.include_router(test_catalog_router)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
        "request_id": request.state.request_id,
    }
