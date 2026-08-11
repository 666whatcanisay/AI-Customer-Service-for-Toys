from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_0015_upgrade_downgrade_preserves_iam_and_store_context(tmp_path: Path) -> None:
    database_path = tmp_path / "desktop-workflow-v1.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0015_customer_desktop_workflow_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert "desktop_workflow_audit_events" in tables
    assert {"users", "user_sessions", "conversation_context_resolutions"}.issubset(tables)
    assert engine.connect().scalar(text("SELECT version_num FROM alembic_version")) == "0015_customer_desktop_workflow_v1"
    engine.dispose()

    command.downgrade(config, "0014_store_context_resolver_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    tables = set(inspect(engine).get_table_names())
    assert "desktop_workflow_audit_events" not in tables
    assert {"users", "user_sessions", "conversation_context_resolutions"}.issubset(tables)
    engine.dispose()


def test_0017_adds_only_non_secret_pairing_rotation_reason(tmp_path: Path) -> None:
    database_path = tmp_path / "host-pairing-rotation-audit.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0017_host_pairing_rotation_audit")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    columns = {
        item["name"]
        for item in inspect(engine).get_columns("desktop_workflow_audit_events")
    }
    assert "reason" in columns
    assert not {"pairing_code", "binding_code", "token", "secret"}.intersection(columns)
    assert engine.connect().scalar(text("SELECT version_num FROM alembic_version")) == (
        "0017_host_pairing_rotation_audit"
    )
    engine.dispose()

    command.downgrade(config, "0016_production_hardening_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    columns = {
        item["name"]
        for item in inspect(engine).get_columns("desktop_workflow_audit_events")
    }
    assert "reason" not in columns
    engine.dispose()
