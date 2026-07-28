from collections.abc import Iterator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.customer_identity.models import CustomerUser, CustomerUserStoreBinding
from app.ingestion.parsers.product_sku_xlsx import DATA_SHEET, EXPECTED_HEADERS
from app.main import app
from app.test_catalog.models import TestKnowledgePackage, TestStore


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def customer_identity_catalog(session: Session) -> None:
    """A minimal catalog and selected trial identities for C API contract tests."""
    package = TestKnowledgePackage(
        package_id="identity-test-package",
        package_name="Identity API synthetic package",
        version="0.0.0",
        schema_version="test",
        tenant_id="identity-test-tenant",
        platform="test",
        store_code="STORE-ONE",
        response_mode="MANUAL",
        test_data_mode=True,
        production_usable=False,
        allow_auto_send=False,
        import_status="IMPORTED",
        original_filename="identity-test.zip",
        zip_sha256="0" * 64,
        counts_json="{}",
        imported_by="test",
    )
    session.add(package)
    for code in ("STORE-ONE", "STORE-TWO"):
        session.add(
            TestStore(
                package_id=package.package_id,
                tenant_id=package.tenant_id,
                platform="test",
                store_code=code,
                store_name=code,
                trial_enabled=True,
                knowledge_scope="TEST",
                response_mode="MANUAL",
                allow_auto_send=False,
                test_data_mode=True,
                production_usable=False,
                raw_data_json="{}",
            )
        )
    for user_id, stores in {
        "support-tester": ("STORE-ONE",),
        "support-other": ("STORE-ONE", "STORE-TWO"),
        "new-submitter": ("STORE-ONE",),
        "review-submitter": ("STORE-ONE",),
        "approved-submitter": ("STORE-ONE",),
    }.items():
        user = CustomerUser(
            user_id=user_id,
            display_name=f"Test {user_id}",
            role="CUSTOMER_SERVICE",
            status="ACTIVE",
            default_store_code=stores[0],
        )
        session.add(user)
        session.flush()
        for store_code in stores:
            session.add(CustomerUserStoreBinding(customer_user_id=user.id, store_code=store_code))
    session.commit()


def valid_row(index: int = 1) -> dict[str, object]:
    return {
        "tenant_id": "tenant-demo",
        "platform": "offline",
        "store_code": "demo-store",
        "product_code": f"DEMO-P{index:03d}",
        "platform_product_id": None,
        "product_name": f"虚构商品 {index}",
        "sku_code": f"DEMO-S{index:03d}",
        "platform_sku_id": None,
        "sku_name": f"虚构 SKU {index}",
        "specifications": '{"color":"blue","pieces":120}',
        "applicable_age_min": 6,
        "applicable_age_max": 12,
        "material": "虚构材质",
        "package_contents": "虚构包装内容",
        "source_name": "人工构造测试数据",
        "effective_from": "2026-07-01",
        "effective_to": "2026-12-31",
        "notes": "非真实公司数据",
    }


def workbook_bytes(
    rows: list[dict[str, object]],
    *,
    headers: list[str] | None = None,
    sheet_name: str = DATA_SHEET,
    formula_cells: dict[str, str] | None = None,
    hide_data_sheet: bool = False,
    hide_support_sheet: bool = False,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    actual_headers = headers or EXPECTED_HEADERS
    sheet.append(actual_headers)
    sheet.append(["description"] * len(actual_headers))
    for row in rows:
        sheet.append([row.get(header) for header in actual_headers])
    for coordinate, formula in (formula_cells or {}).items():
        sheet[coordinate] = formula
    if hide_data_sheet:
        workbook.create_sheet("说明")
        sheet.sheet_state = "hidden"
    if hide_support_sheet:
        support_sheet = workbook.create_sheet("隐藏说明")
        support_sheet.sheet_state = "hidden"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
