from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


REVISION = "0022_reply_rule_source_evidence_v1"
PREVIOUS_REVISION = "0021_reply_rule_snapshot_publication_v1"


def _config(database_path: Path) -> Config:
    os.environ.pop("DATABASE_URL", None)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _revision(database_path: Path) -> str:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        value = connection.scalar(text("SELECT version_num FROM alembic_version"))
    engine.dispose()
    assert isinstance(value, str)
    return value


def test_0022_adds_and_removes_source_evidence_on_isolated_sqlite(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "reply-rule-source-evidence.sqlite3"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, REVISION)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    columns = {item["name"] for item in inspect(engine).get_columns("reply_rules")}
    engine.dispose()
    assert "source_material_evidence_json" in columns
    assert _revision(database_path) == REVISION

    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    columns = {item["name"] for item in inspect(engine).get_columns("reply_rules")}
    engine.dispose()
    assert "source_material_evidence_json" not in columns
    assert _revision(database_path) == PREVIOUS_REVISION

    command.upgrade(config, REVISION)
    assert _revision(database_path) == REVISION
