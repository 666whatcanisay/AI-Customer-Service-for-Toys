from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _assert_0011(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    assert {
        "product_knowledge_publications",
        "product_knowledge_publication_receipts",
        "product_knowledge_publication_idempotency",
    }.issubset(names)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0011_product_knowledge_publishing_v1"
        )
    engine.dispose()


def test_0011_upgrade_downgrade_upgrade_uses_isolated_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "r006-1-migration.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0010_customer_available_catalog_v1")
    command.upgrade(config, "0011_product_knowledge_publishing_v1")
    _assert_0011(database_path)

    command.downgrade(config, "0010_customer_available_catalog_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    names = set(inspect(engine).get_table_names())
    assert "product_knowledge_publications" not in names
    assert "product_knowledge_publication_receipts" not in names
    assert "product_knowledge_publication_idempotency" not in names
    engine.dispose()

    command.upgrade(config, "0011_product_knowledge_publishing_v1")
    _assert_0011(database_path)
