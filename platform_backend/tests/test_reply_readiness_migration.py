from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


REVISION = "0023_reply_readiness_v1"
PREVIOUS_REVISION = "0022_reply_rule_source_evidence_v1"


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


def test_0023_uses_only_task_specific_tables_and_preserves_knowledge_materials(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "reply-readiness.sqlite3"
    config = _config(database_path)
    command.upgrade(config, PREVIOUS_REVISION)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    before = {item["name"] for item in inspect(engine).get_columns("knowledge_materials")}
    engine.dispose()

    command.upgrade(config, REVISION)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert {
        "reply_readiness_question_set_extensions",
        "reply_readiness_runs",
    }.issubset(inspector.get_table_names())
    after = {item["name"] for item in inspector.get_columns("knowledge_materials")}
    run_columns = {item["name"] for item in inspector.get_columns("reply_readiness_runs")}
    engine.dispose()

    assert after == before
    assert "reply_rule_snapshot_revision" in run_columns
    assert "reply_rule_snapshot_fingerprint" in run_columns
    assert _revision(database_path) == REVISION

    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert "reply_readiness_runs" not in inspector.get_table_names()
    assert {item["name"] for item in inspector.get_columns("knowledge_materials")} == before
    engine.dispose()
    assert _revision(database_path) == PREVIOUS_REVISION
