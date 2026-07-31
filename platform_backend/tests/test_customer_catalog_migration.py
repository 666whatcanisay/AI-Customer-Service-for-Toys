from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _seed_0009(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    now = "2026-07-31 00:00:00"
    with engine.begin() as connection:
        for package_id, store_code, import_status, schema_version in (
            ("PKG-TEST", "TEST", "IMPORTED_TEST_ONLY", "0.3.1-test"),
            ("PKG-PILOT", "PILOT", "MANUAL_CREATED", "c-operation-store.v1"),
            ("PKG-UNKNOWN", "UNKNOWN", "UNKNOWN", "unknown"),
        ):
            connection.execute(
                text(
                    """INSERT INTO test_knowledge_packages (
                    package_id, package_name, version, schema_version, tenant_id,
                    platform, store_code, response_mode, test_data_mode,
                    production_usable, allow_auto_send, import_status,
                    original_filename, zip_sha256, counts_json, imported_by, imported_at
                    ) VALUES (
                    :package_id, :package_name, '1', :schema_version, :tenant_id,
                    'pdd', :store_code, 'SUGGESTION_ONLY', 1, 0, 0, :import_status,
                    'synthetic.zip', :digest, '{}', 'pytest', :now
                    )"""
                ),
                {
                    "package_id": package_id,
                    "package_name": package_id,
                    "schema_version": schema_version,
                    "tenant_id": f"tenant-{store_code}",
                    "store_code": store_code,
                    "import_status": import_status,
                    "digest": (package_id + "0" * 64)[:64],
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO test_catalog_stores (
                    package_id, tenant_id, platform, store_code, store_name,
                    trial_enabled, knowledge_scope, response_mode, allow_auto_send,
                    test_data_mode, production_usable, raw_data_json
                    ) VALUES (
                    :package_id, :tenant_id, 'pdd', :store_code, :store_name,
                    1, 'STORE_PRODUCT_SKU', 'SUGGESTION_ONLY', 0, 1, 0, '{}'
                    )"""
                ),
                {
                    "package_id": package_id,
                    "tenant_id": f"tenant-{store_code}",
                    "store_code": store_code,
                    "store_name": f"{store_code} 店",
                },
            )
            connection.execute(
                text(
                    """INSERT INTO test_catalog_products (
                    product_id, package_id, tenant_id, platform, store_code,
                    product_name_official, product_name_display, sales_status,
                    age_min, age_max, safety_summary, review_status, publishable,
                    source_ids_json, raw_data_json
                    ) VALUES (
                    :product_id, :package_id, :tenant_id, 'pdd', :store_code,
                    :product_name, :product_name, 'ON_SALE', NULL, NULL, NULL,
                    'DRAFT', 0, '[]', '{}'
                    )"""
                ),
                {
                    "product_id": f"PRODUCT-{store_code}",
                    "package_id": package_id,
                    "tenant_id": f"tenant-{store_code}",
                    "store_code": store_code,
                    "product_name": f"{store_code} 商品",
                },
            )
    engine.dispose()


def _assert_0010(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        stores = {
            row.store_code: (row.data_source, row.customer_service_status)
            for row in connection.execute(
                text(
                    "SELECT store_code, data_source, customer_service_status "
                    "FROM test_catalog_stores"
                )
            )
        }
        products = {
            row.product_id: row.customer_service_status
            for row in connection.execute(
                text(
                    "SELECT product_id, customer_service_status "
                    "FROM test_catalog_products"
                )
            )
        }
        assert stores == {
            "TEST": ("TEST", "ENABLED"),
            "PILOT": ("PILOT", "DISABLED"),
            "UNKNOWN": (None, "DISABLED"),
        }
        assert products == {
            "PRODUCT-TEST": "ENABLED",
            "PRODUCT-PILOT": "DISABLED",
            "PRODUCT-UNKNOWN": "DISABLED",
        }
        assert connection.scalar(text("SELECT count(*) FROM catalog_activation_receipts")) == 4
        manifest = connection.scalar(
            text("SELECT manifest_json FROM catalog_activation_initializations")
        )
        assert '"quarantined_stores":1' in manifest
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0010_customer_available_catalog_v1"
        )
    engine.dispose()


def test_0010_upgrade_downgrade_upgrade_uses_isolated_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "r006-migration.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0009_product_knowledge_import_v1")
    _seed_0009(database_path)

    command.upgrade(config, "0010_customer_available_catalog_v1")
    _assert_0010(database_path)

    command.downgrade(config, "0009_product_knowledge_import_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert "catalog_activation_receipts" not in inspector.get_table_names()
    assert "customer_service_status" not in {
        column["name"] for column in inspector.get_columns("test_catalog_stores")
    }
    engine.dispose()

    command.upgrade(config, "0010_customer_available_catalog_v1")
    _assert_0010(database_path)
