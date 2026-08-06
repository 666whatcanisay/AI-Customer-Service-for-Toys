from collections.abc import Iterator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.ingestion.parsers.product_sku_xlsx import DATA_SHEET, EXPECTED_HEADERS
from app.main import app
from app.iam.dependencies import Principal, get_current_principal
from app.iam.schemas import RoleName


LEGACY_TEST_ADMIN = Principal(
    user_id="00000000-0000-0000-0000-000000000001",
    username="pytest-admin",
    display_name="Pytest Admin",
    roles=frozenset({RoleName.ADMIN}),
    permissions=frozenset({
        "workspace.access", "ai.reply", "feedback.submit", "customer_service.manage",
        "product.manage", "sku.manage", "knowledge.manage", "faq.manage",
        "ai_quality.view", "store.view", "feedback.view", "user.manage",
    }),
    store_ids=frozenset(),
    all_store_access=True,
    must_change_password=False,
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    # Match the production SessionLocal behavior so integration-only flush
    # ordering defects are visible in the test suite.
    with Session(engine, autoflush=False, expire_on_commit=False) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_principal] = lambda: LEGACY_TEST_ADMIN
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
