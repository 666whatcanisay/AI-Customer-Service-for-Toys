from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _assert_revision(database_path: Path, revision: str, tables: set[str]) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert tables.issubset(set(inspect(engine).get_table_names()))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == revision
    engine.dispose()


def test_0020_upgrade_downgrade_upgrade_uses_isolated_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "reply-rule-governance.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0019_runtime_database_identity_v1")
    command.upgrade(config, "0020_reply_rule_governance_v1")
    _assert_revision(
        database_path,
        "0020_reply_rule_governance_v1",
        {"reply_rules", "reply_rule_events"},
    )

    command.downgrade(config, "0019_runtime_database_identity_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    names = set(inspect(engine).get_table_names())
    assert "reply_rules" not in names
    assert "reply_rule_events" not in names
    engine.dispose()

    command.upgrade(config, "0020_reply_rule_governance_v1")
    _assert_revision(
        database_path,
        "0020_reply_rule_governance_v1",
        {"reply_rules", "reply_rule_events"},
    )
