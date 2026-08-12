from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _config(database_path: Path) -> Config:
    os.environ.pop("DATABASE_URL", None)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_0013_to_head_to_0013_and_back_to_head_is_reversible(tmp_path: Path) -> None:
    database_path = tmp_path / "production-hardening.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0013_user_management_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0013_user_management_v1"
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert "login_attempt_buckets" in inspector.get_table_names()
    publication_columns = {
        item["name"] for item in inspector.get_columns("product_knowledge_publications")
    }
    assert {"generation_token", "generation_started_at"}.issubset(publication_columns)
    binding_indexes = {
        item["name"] for item in inspector.get_indexes("user_store_bindings")
    }
    assert "uq_user_store_bindings_single_default" in binding_indexes
    assert "store_platform_bindings" in inspector.get_table_names()
    assert "runtime_database_identity" in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0019_runtime_database_identity_v1"
        )
    engine.dispose()

    command.downgrade(config, "0013_user_management_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    downgraded = inspect(engine)
    assert {
        "login_attempt_buckets",
        "conversation_context_resolutions",
        "desktop_workflow_audit_events",
        "store_platform_bindings",
        "runtime_database_identity",
    }.isdisjoint(downgraded.get_table_names())
    assert {"generation_token", "generation_started_at"}.isdisjoint(
        item["name"] for item in downgraded.get_columns("product_knowledge_publications")
    )
    assert "uq_user_store_bindings_single_default" not in {
        item["name"] for item in downgraded.get_indexes("user_store_bindings")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0013_user_management_v1"
        )
    engine.dispose()
    command.upgrade(config, "head")
