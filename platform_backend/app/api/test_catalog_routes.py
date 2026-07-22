"""C-T02B test-package ingestion and frozen read-only integration routes."""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.test_catalog.repository import TestCatalogRepository
from app.test_catalog.schemas import (
    EvaluationResponse,
    ProductListResponse,
    RagExportResponse,
    SkuListResponse,
    StoreListResponse,
    TestPackageListResponse,
    TestPackagePreflightResponse,
    TestPackageSummary,
)
from app.test_catalog.service import TestPackageService

router = APIRouter(prefix="/api/v1", tags=["test-catalog"])


def _repository(session: Session) -> TestCatalogRepository:
    return TestCatalogRepository(session)


def _service(repository: TestCatalogRepository | None) -> TestPackageService:
    settings = get_settings()
    return TestPackageService(
        repository,
        max_upload_bytes=settings.max_test_package_upload_bytes,
        max_entries=settings.max_test_package_entries,
        max_uncompressed_bytes=settings.max_test_package_uncompressed_bytes,
        max_single_file_bytes=settings.max_test_package_single_file_bytes,
    )


@router.post(
    "/test-data-packages/preflight",
    response_model=TestPackagePreflightResponse,
)
async def preflight_test_package(
    file: UploadFile = File(...),
) -> TestPackagePreflightResponse:
    settings = get_settings()
    content = await file.read(settings.max_test_package_upload_bytes + 1)
    return _service(None).preflight(
        filename=file.filename or "test-package.zip",
        content_type=file.content_type,
        content=content,
    )


@router.post(
    "/test-data-packages",
    response_model=TestPackageSummary,
    status_code=201,
)
async def import_test_package(
    file: UploadFile = File(...),
    imported_by: str = Form("admin-test-import"),
    session: Session = Depends(get_db),
) -> TestPackageSummary:
    settings = get_settings()
    content = await file.read(settings.max_test_package_upload_bytes + 1)
    return _service(_repository(session)).import_package(
        filename=file.filename or "test-package.zip",
        content_type=file.content_type,
        content=content,
        imported_by=imported_by,
    )


@router.get("/test-data-packages", response_model=TestPackageListResponse)
def list_test_packages(session: Session = Depends(get_db)) -> TestPackageListResponse:
    repository = _repository(session)
    items = [repository.package_summary(item) for item in repository.list_packages()]
    return TestPackageListResponse(items=items, total=len(items))


@router.get("/test-catalog/stores", response_model=StoreListResponse)
def list_test_stores(session: Session = Depends(get_db)) -> StoreListResponse:
    items = _repository(session).list_stores()
    return StoreListResponse(items=items, total=len(items))


@router.get("/test-catalog/products", response_model=ProductListResponse)
def list_test_products(
    store_code: str | None = Query(None),
    session: Session = Depends(get_db),
) -> ProductListResponse:
    items = _repository(session).list_products(store_code)
    return ProductListResponse(items=items, total=len(items))


@router.get(
    "/test-catalog/products/{product_id}/skus",
    response_model=SkuListResponse,
)
def list_test_product_skus(
    product_id: str,
    session: Session = Depends(get_db),
) -> SkuListResponse:
    items = _repository(session).list_skus(product_id)
    return SkuListResponse(items=items, total=len(items))


@router.get(
    "/test-knowledge-packages/{package_id}/rag-export",
    response_model=RagExportResponse,
)
def export_test_rag_package(
    package_id: str,
    session: Session = Depends(get_db),
) -> RagExportResponse:
    return _repository(session).rag_export(package_id)


@router.get(
    "/test-knowledge-packages/{package_id}/evaluations",
    response_model=EvaluationResponse,
)
def export_test_evaluations(
    package_id: str,
    session: Session = Depends(get_db),
) -> EvaluationResponse:
    return _repository(session).evaluations(package_id)
