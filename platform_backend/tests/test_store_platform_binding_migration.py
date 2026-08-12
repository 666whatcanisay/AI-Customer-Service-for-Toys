import json
from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def _config(database_path: Path) -> Config:
    os.environ.pop("DATABASE_URL", None)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_existing_reliable_external_store_identity_is_backfilled(tmp_path: Path) -> None:
    database_path = tmp_path / "store-platform-binding.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0017_host_pairing_rotation_audit")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO test_knowledge_packages (
                package_id, package_name, version, schema_version, tenant_id,
                platform, store_code, response_mode, test_data_mode,
                production_usable, allow_auto_send, import_status,
                original_filename, zip_sha256, counts_json, imported_by, imported_at
            ) VALUES (
                'PKG-BINDING', '平台绑定迁移', '1', 'test', 'tenant-binding',
                'pdd', 'STORE-BINDING', 'SUGGEST_ONLY', 1, 0, 0,
                'IMPORTED', 'synthetic', :sha, '{}', 'pytest', CURRENT_TIMESTAMP
            )
        """), {"sha": "a" * 64})
        connection.execute(text("""
            INSERT INTO test_catalog_stores (
                package_id, tenant_id, platform, store_code, store_name,
                trial_enabled, knowledge_scope, response_mode, allow_auto_send,
                test_data_mode, production_usable, data_source,
                customer_service_status, raw_data_json
            ) VALUES (
                'PKG-BINDING', 'tenant-binding', 'pdd', 'STORE-BINDING',
                '迁移测试店', 1, 'TEST', 'SUGGEST_ONLY', 0, 1, 0, 'TEST',
                'ENABLED', :raw
            )
        """), {"raw": json.dumps({"platform_store_id": "328616090"})})
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        row = connection.execute(text("""
            SELECT b.platform, b.platform_store_id, b.status, s.store_code
            FROM store_platform_bindings b
            JOIN test_catalog_stores s ON s.id = b.store_id
        """)).mappings().one()
        assert row == {
            "platform": "pinduoduo",
            "platform_store_id": "328616090",
            "status": "ACTIVE",
            "store_code": "STORE-BINDING",
        }
    engine.dispose()
