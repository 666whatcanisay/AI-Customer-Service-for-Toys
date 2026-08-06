from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_0014_upgrade_downgrade_preserves_iam_and_catalog_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "store-context-v1.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0014_store_context_resolver_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert "conversation_context_resolutions" in tables
    assert {"users", "user_store_bindings", "test_catalog_products", "test_catalog_skus"}.issubset(tables)
    assert engine.connect().scalar(text("SELECT version_num FROM alembic_version")) == "0014_store_context_resolver_v1"
    engine.dispose()

    command.downgrade(config, "0013_user_management_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert "conversation_context_resolutions" not in tables
    assert {"users", "user_store_bindings", "test_catalog_products", "test_catalog_skus"}.issubset(tables)
    engine.dispose()
