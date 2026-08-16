from __future__ import annotations

import sqlite3

from sqlalchemy import inspect

from channel_engine.storage import create_engine_and_session, create_schema


def test_foundation_sqlite_schema_is_upgraded_additively(tmp_path) -> None:
    database_path = tmp_path / "foundation-before-runtime.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE executions (
            execution_id VARCHAR(80) PRIMARY KEY,
            decision_id VARCHAR(80) NOT NULL UNIQUE,
            approval_id VARCHAR(80) NOT NULL UNIQUE,
            state VARCHAR(40) NOT NULL,
            idempotency_key VARCHAR(160) NOT NULL UNIQUE,
            attempt INTEGER NOT NULL,
            started_at DATETIME,
            completed_at DATETIME,
            error_code VARCHAR(120),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
        CREATE TABLE transactional_outbox (
            outbox_id VARCHAR(100) PRIMARY KEY,
            event_id VARCHAR(80) NOT NULL UNIQUE,
            topic VARCHAR(120) NOT NULL,
            payload JSON NOT NULL,
            status VARCHAR(40) NOT NULL,
            created_at DATETIME NOT NULL,
            published_at DATETIME,
            last_error TEXT
        );
        """
    )
    connection.close()

    engine, _session_factory = create_engine_and_session(
        f"sqlite:///{database_path.as_posix()}"
    )
    create_schema(engine)
    create_schema(engine)

    inspector = inspect(engine)
    execution_columns = {
        column["name"] for column in inspector.get_columns("executions")
    }
    outbox_columns = {
        column["name"]
        for column in inspector.get_columns("transactional_outbox")
    }
    index_names = {
        index["name"]
        for table_name in ("executions", "transactional_outbox")
        for index in inspector.get_indexes(table_name)
    }

    assert {"lease_owner", "lease_token", "lease_expires_at"} <= execution_columns
    assert "runtime_storage_version" in execution_columns
    assert {
        "attempt_count",
        "next_attempt_at",
        "lease_owner",
        "lease_token",
        "lease_expires_at",
        "runtime_storage_version",
        "publish_key",
    } <= outbox_columns
    assert "ix_executions_claim" in index_names
    assert "ix_transactional_outbox_claim" in index_names
    assert "ux_transactional_outbox_publish_key" in index_names
    engine.dispose()
