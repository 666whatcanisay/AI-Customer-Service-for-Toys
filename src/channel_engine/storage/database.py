from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from channel_engine.models.entities import utc_now

from .versioning import ensure_runtime_storage_version, validate_runtime_storage_version


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    raw_path = database_url[len(prefix) :]
    if raw_path == ":memory:" or raw_path.startswith("file:"):
        return
    Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_engine_and_session(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    _ensure_sqlite_parent(database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(  # type: ignore[no-untyped-def]
            dbapi_connection, _connection_record
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    return engine, factory


def create_schema(engine: Engine) -> None:
    """Explicitly initialize or additively upgrade a development/test database."""

    from . import orm  # noqa: F401

    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        _upgrade_sqlite_runtime_columns(engine)
    ensure_runtime_storage_version(engine, utc_now())


def validate_schema(engine: Engine) -> None:
    """Validate production schema compatibility without executing DDL or UPDATE."""

    from . import orm  # noqa: F401

    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    missing_tables = sorted(expected_tables - actual_tables)
    if missing_tables:
        raise RuntimeError(
            "channel engine database schema is not initialized; missing tables: "
            + ", ".join(missing_tables)
        )
    for table_name, table in Base.metadata.tables.items():
        actual_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        missing_columns = sorted(set(table.columns.keys()) - actual_columns)
        if missing_columns:
            raise RuntimeError(
                f"channel engine database table {table_name} is missing columns: "
                + ", ".join(missing_columns)
            )
    validate_runtime_storage_version(engine, utc_now())


def _upgrade_sqlite_runtime_columns(engine: Engine) -> None:
    """Apply additive Foundation upgrades without connecting to external systems."""

    additions = {
        "executions": {
            "runtime_storage_version": "VARCHAR(16) NOT NULL DEFAULT '1.0'",
            "lease_owner": "VARCHAR(160)",
            "lease_token": "VARCHAR(100)",
            "lease_expires_at": "DATETIME",
        },
        "transactional_outbox": {
            "runtime_storage_version": "VARCHAR(16) NOT NULL DEFAULT '1.0'",
            "publish_key": "VARCHAR(160)",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "next_attempt_at": "DATETIME",
            "lease_owner": "VARCHAR(160)",
            "lease_token": "VARCHAR(100)",
            "lease_expires_at": "DATETIME",
        },
        "execution_receipts": {
            "runtime_storage_version": "VARCHAR(16) NOT NULL DEFAULT '1.0'",
        },
        "events": {
            "runtime_storage_version": "VARCHAR(16) NOT NULL DEFAULT '1.0'",
        },
        "runtime_heartbeats": {
            "available": "INTEGER NOT NULL DEFAULT 0",
            "process_running": "INTEGER",
            "page_available": "INTEGER",
        },
        "channel_agent_identities": {
            "active_store_id": "VARCHAR(160)",
            "identity_status": "VARCHAR(32) NOT NULL DEFAULT 'REGISTERED'",
            "connectivity_status": "VARCHAR(16) NOT NULL DEFAULT 'OFFLINE'",
            "agent_version": "VARCHAR(64)",
            "hostname": "VARCHAR(255)",
            "runtime_status": "VARCHAR(64)",
            "registered_at": "DATETIME",
            "last_heartbeat": "DATETIME",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, declaration in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(
                        f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {declaration}'
                    )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_executions_claim "
            "ON executions (state, created_at)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_transactional_outbox_claim "
            "ON transactional_outbox (status, next_attempt_at, created_at)"
        )
        connection.exec_driver_sql(
            "UPDATE transactional_outbox SET publish_key = event_id "
            "WHERE publish_key IS NULL"
        )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_transactional_outbox_publish_key "
            "ON transactional_outbox (publish_key)"
        )
        connection.exec_driver_sql(
            "UPDATE channel_agent_identities SET active_store_id = store_id "
            "WHERE active_store_id IS NULL AND store_id IS NOT NULL"
        )
        connection.exec_driver_sql(
            "UPDATE channel_agent_identities "
            "SET identity_status = CASE "
            "WHEN status = 'UNBOUND' THEN 'REGISTERED' "
            "WHEN status IN ('REGISTERED', 'BOUND', 'ACTIVE', 'DISABLED') THEN status "
            "ELSE 'REGISTERED' END"
        )
        connection.exec_driver_sql(
            "UPDATE channel_agent_identities SET status = identity_status"
        )
        connection.exec_driver_sql(
            "UPDATE channel_agent_identities SET connectivity_status = 'OFFLINE' "
            "WHERE connectivity_status NOT IN ('ONLINE', 'OFFLINE')"
        )
