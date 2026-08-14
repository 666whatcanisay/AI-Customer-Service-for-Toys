from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


REVISION = "0021_reply_rule_snapshot_publication_v1"
TABLES = {
    "reply_rule_snapshot_publications",
    "reply_rule_snapshot_publication_receipts",
    "reply_rule_snapshot_publication_idempotency",
}


def _config(database_path: Path) -> Config:
    os.environ.pop("DATABASE_URL", None)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _assert_revision_and_tables(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert TABLES.issubset(inspector.get_table_names())
    indexes = {
        item["name"]: item
        for item in inspector.get_indexes("reply_rule_snapshot_publications")
    }
    assert indexes["ix_reply_rule_snapshot_publications_scope"]["unique"] == 1
    assert {
        item["name"]
        for item in inspector.get_check_constraints(
            "reply_rule_snapshot_publications"
        )
    } == {
        "ck_reply_rule_snapshot_publication_status",
        "ck_reply_rule_snapshot_revision_non_negative",
        "ck_reply_rule_snapshot_rule_count_non_negative",
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
    engine.dispose()


def test_0021_upgrade_downgrade_upgrade_uses_isolated_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "reply-rule-publication.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0020_reply_rule_governance_v1")
    command.upgrade(config, REVISION)
    _assert_revision_and_tables(database_path)

    command.downgrade(config, "0020_reply_rule_governance_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert TABLES.isdisjoint(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0020_reply_rule_governance_v1"
        )
    engine.dispose()

    command.upgrade(config, REVISION)
    _assert_revision_and_tables(database_path)
