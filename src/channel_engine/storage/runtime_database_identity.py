from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from .database import create_engine_and_session, create_schema
from .versioning import RUNTIME_STORAGE_VERSION

DATABASE_ROLE = "HOST_CONTROL"
BINDING_SCHEMA = "channel-engine.runtime-database-binding.v1"
IDENTITY_REVISION = 1
SQLITE_HEADER = b"SQLite format 3\x00"


class RuntimeDatabaseIdentityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeDatabaseIdentity:
    database_instance_id: str
    database_role: str
    environment_id: str
    identity_revision: int
    schema_fingerprint: str
    created_by_source_commit: str | None
    created_at: str
    restore_generation: int
    restored_from_backup_epoch: str | None
    last_restored_at: str | None


@dataclass(frozen=True, slots=True)
class RuntimeDatabaseBindingV1:
    schema: str
    database_instance_id: str
    database_role: str
    environment_id: str
    identity_revision: int
    schema_fingerprint: str
    canonical_path: str
    runtime_storage_version: str
    restore_generation: int
    restored_from_backup_epoch: str | None
    generated_at: str


def validate_runtime_database(
    database_path: str | Path,
    binding_path: str | Path,
    *,
    expected_environment_id: str,
) -> RuntimeDatabaseIdentity:
    database = _absolute_path(database_path, "database")
    binding_file = _absolute_path(binding_path, "binding sidecar")
    with _open_checked(database) as connection:
        identity = _read_identity(connection)
        fingerprint = calculate_schema_fingerprint(connection)
        version = _runtime_version(connection)
    binding = _load_binding(binding_file)
    if identity.database_role != DATABASE_ROLE or binding.database_role != DATABASE_ROLE:
        raise RuntimeDatabaseIdentityError("runtime database role mismatch")
    if (
        identity.environment_id != expected_environment_id
        or binding.environment_id != expected_environment_id
    ):
        raise RuntimeDatabaseIdentityError("runtime database environment mismatch")
    if binding.schema != BINDING_SCHEMA:
        raise RuntimeDatabaseIdentityError("runtime database binding schema mismatch")
    if binding.runtime_storage_version != version:
        raise RuntimeDatabaseIdentityError("runtime storage version binding mismatch")
    if Path(binding.canonical_path).resolve(strict=False) != database:
        raise RuntimeDatabaseIdentityError("runtime database canonical path mismatch")
    for field in (
        "database_instance_id",
        "database_role",
        "environment_id",
        "identity_revision",
        "schema_fingerprint",
        "restore_generation",
        "restored_from_backup_epoch",
    ):
        if getattr(identity, field) != getattr(binding, field):
            raise RuntimeDatabaseIdentityError(
                f"runtime database identity mismatch: {field}"
            )
    if identity.schema_fingerprint != fingerprint:
        raise RuntimeDatabaseIdentityError("runtime database schema fingerprint mismatch")
    if identity.identity_revision != IDENTITY_REVISION:
        raise RuntimeDatabaseIdentityError("runtime database identity revision unsupported")
    try:
        UUID(identity.database_instance_id)
    except ValueError as exc:
        raise RuntimeDatabaseIdentityError("runtime database instance ID invalid") from exc
    return identity


def bind_runtime_database(
    database_path: str | Path,
    binding_path: str | Path,
    *,
    environment_id: str,
    source_commit: str,
    mode: Literal["NEW_INSTANCE", "UPGRADE", "RESTORE"],
    backup_epoch: str | None = None,
) -> RuntimeDatabaseIdentity:
    database = _absolute_path(database_path, "database")
    binding_file = _absolute_path(binding_path, "binding sidecar")
    if not environment_id.strip() or not source_commit.strip():
        raise RuntimeDatabaseIdentityError(
            "environment ID and source commit are required"
        )
    with _open_checked(database) as connection:
        fingerprint = calculate_schema_fingerprint(connection)
        _runtime_version(connection)
        try:
            existing = _read_identity(connection)
        except RuntimeDatabaseIdentityError:
            existing = None
        now = datetime.now(UTC).isoformat()
        if mode == "NEW_INSTANCE":
            identity = RuntimeDatabaseIdentity(
                database_instance_id=str(uuid4()),
                database_role=DATABASE_ROLE,
                environment_id=environment_id.strip(),
                identity_revision=IDENTITY_REVISION,
                schema_fingerprint=fingerprint,
                created_by_source_commit=source_commit.strip(),
                created_at=now,
                restore_generation=0,
                restored_from_backup_epoch=None,
                last_restored_at=None,
            )
        elif mode == "RESTORE":
            if existing is None:
                raise RuntimeDatabaseIdentityError(
                    "disaster recovery requires an existing logical identity"
                )
            if not backup_epoch or not backup_epoch.strip():
                raise RuntimeDatabaseIdentityError(
                    "disaster recovery requires a backup epoch"
                )
            if existing.environment_id != environment_id.strip():
                raise RuntimeDatabaseIdentityError(
                    "disaster recovery cannot change the runtime environment"
                )
            identity = RuntimeDatabaseIdentity(
                database_instance_id=existing.database_instance_id,
                database_role=existing.database_role,
                environment_id=existing.environment_id,
                identity_revision=existing.identity_revision,
                schema_fingerprint=fingerprint,
                created_by_source_commit=existing.created_by_source_commit,
                created_at=existing.created_at,
                restore_generation=existing.restore_generation + 1,
                restored_from_backup_epoch=backup_epoch.strip(),
                last_restored_at=now,
            )
        else:
            if existing is None:
                raise RuntimeDatabaseIdentityError(
                    "schema upgrade requires an existing logical identity"
                )
            if existing.environment_id != environment_id.strip():
                raise RuntimeDatabaseIdentityError(
                    "schema upgrade cannot change the runtime environment"
                )
            identity = RuntimeDatabaseIdentity(
                database_instance_id=existing.database_instance_id,
                database_role=existing.database_role,
                environment_id=existing.environment_id,
                identity_revision=existing.identity_revision,
                schema_fingerprint=fingerprint,
                created_by_source_commit=existing.created_by_source_commit,
                created_at=existing.created_at,
                restore_generation=existing.restore_generation,
                restored_from_backup_epoch=existing.restored_from_backup_epoch,
                last_restored_at=existing.last_restored_at,
            )
        connection.execute("DELETE FROM runtime_database_identity")
        connection.execute(
            """
            INSERT INTO runtime_database_identity(
                database_role,database_instance_id,environment_id,identity_revision,
                schema_fingerprint,created_by_source_commit,created_at,
                restore_generation,restored_from_backup_epoch,last_restored_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                identity.database_role,
                identity.database_instance_id,
                identity.environment_id,
                identity.identity_revision,
                identity.schema_fingerprint,
                identity.created_by_source_commit,
                identity.created_at,
                identity.restore_generation,
                identity.restored_from_backup_epoch,
                identity.last_restored_at,
            ),
        )
        connection.commit()
    _write_binding(binding_file, database, identity)
    return validate_runtime_database(
        database,
        binding_file,
        expected_environment_id=environment_id.strip(),
    )


def initialize_runtime_database(
    database_path: str | Path,
    binding_path: str | Path,
    *,
    environment_id: str,
    source_commit: str,
) -> RuntimeDatabaseIdentity:
    database = _absolute_path(database_path, "database")
    if database.exists():
        raise RuntimeDatabaseIdentityError(
            "initialization refuses to overwrite an existing database"
        )
    database.parent.mkdir(parents=True, exist_ok=True)
    engine, _sessions = create_engine_and_session(
        f"sqlite:///{database.as_posix()}"
    )
    try:
        create_schema(engine)
    finally:
        engine.dispose()
    return bind_runtime_database(
        database,
        binding_path,
        environment_id=environment_id,
        source_commit=source_commit,
        mode="NEW_INSTANCE",
    )


def calculate_schema_fingerprint(connection: sqlite3.Connection) -> str:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    schema: dict[str, Any] = {}
    for table in tables:
        escaped = str(table).replace('"', '""')
        schema[table] = {
            "columns": [
                list(row)
                for row in connection.execute(
                    f'PRAGMA table_info("{escaped}")'
                ).fetchall()
            ],
            "foreign_keys": [
                list(row)
                for row in connection.execute(
                    f'PRAGMA foreign_key_list("{escaped}")'
                ).fetchall()
            ],
            "indexes": [],
        }
        for index in connection.execute(f'PRAGMA index_list("{escaped}")'):
            index_name = str(index[1]).replace('"', '""')
            schema[table]["indexes"].append(
                {
                    "definition": list(index),
                    "columns": [
                        list(row)
                        for row in connection.execute(
                            f'PRAGMA index_info("{index_name}")'
                        )
                    ],
                }
            )
    canonical = json.dumps(
        schema, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _read_identity(connection: sqlite3.Connection) -> RuntimeDatabaseIdentity:
    try:
        rows = connection.execute(
            """
            SELECT database_instance_id,database_role,environment_id,
                   identity_revision,schema_fingerprint,created_by_source_commit,
                   created_at,restore_generation,restored_from_backup_epoch,
                   last_restored_at FROM runtime_database_identity
            """
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise RuntimeDatabaseIdentityError(
            "runtime database identity table missing"
        ) from exc
    if len(rows) != 1:
        raise RuntimeDatabaseIdentityError(
            "runtime database must contain exactly one identity row"
        )
    return RuntimeDatabaseIdentity(**dict(rows[0]))


def _runtime_version(connection: sqlite3.Connection) -> str:
    try:
        rows = connection.execute(
            "SELECT runtime_storage_version FROM runtime_storage_metadata"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise RuntimeDatabaseIdentityError("runtime storage manifest missing") from exc
    if len(rows) != 1 or rows[0][0] != RUNTIME_STORAGE_VERSION:
        raise RuntimeDatabaseIdentityError("runtime storage version unsupported")
    return str(rows[0][0])


def _open_checked(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.stat().st_size <= len(SQLITE_HEADER):
        raise RuntimeDatabaseIdentityError("runtime database is missing or empty")
    with path.open("rb") as stream:
        if stream.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise RuntimeDatabaseIdentityError("runtime database is not SQLite")
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    result = connection.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        connection.close()
        raise RuntimeDatabaseIdentityError("runtime database integrity check failed")
    return connection


def _load_binding(path: Path) -> RuntimeDatabaseBindingV1:
    if not path.is_file():
        raise RuntimeDatabaseIdentityError("runtime database binding sidecar missing")
    try:
        return RuntimeDatabaseBindingV1(
            **json.loads(path.read_text(encoding="utf-8-sig"))
        )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeDatabaseIdentityError(
            "runtime database binding sidecar invalid"
        ) from exc


def _write_binding(
    path: Path, database: Path, identity: RuntimeDatabaseIdentity
) -> None:
    value = RuntimeDatabaseBindingV1(
        schema=BINDING_SCHEMA,
        database_instance_id=identity.database_instance_id,
        database_role=identity.database_role,
        environment_id=identity.environment_id,
        identity_revision=identity.identity_revision,
        schema_fingerprint=identity.schema_fingerprint,
        canonical_path=str(database),
        runtime_storage_version=RUNTIME_STORAGE_VERSION,
        restore_generation=identity.restore_generation,
        restored_from_backup_epoch=identity.restored_from_backup_epoch,
        generated_at=datetime.now(UTC).isoformat(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(asdict(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _absolute_path(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RuntimeDatabaseIdentityError(f"runtime {label} path must be absolute")
    return path.resolve(strict=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Engine runtime DB identity")
    parser.add_argument(
        "command", choices=("initialize", "bind-new", "upgrade", "restore", "validate")
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--backup-epoch")
    arguments = parser.parse_args(argv)
    if arguments.command == "initialize":
        identity = initialize_runtime_database(
            arguments.database,
            arguments.binding,
            environment_id=arguments.environment_id,
            source_commit=arguments.source_commit,
        )
    elif arguments.command == "validate":
        identity = validate_runtime_database(
            arguments.database,
            arguments.binding,
            expected_environment_id=arguments.environment_id,
        )
    else:
        identity = bind_runtime_database(
            arguments.database,
            arguments.binding,
            environment_id=arguments.environment_id,
            source_commit=arguments.source_commit,
            mode=(
                "RESTORE"
                if arguments.command == "restore"
                else "UPGRADE"
                if arguments.command == "upgrade"
                else "NEW_INSTANCE"
            ),
            backup_epoch=arguments.backup_epoch,
        )
    print(json.dumps(asdict(identity), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "RuntimeDatabaseBindingV1",
    "RuntimeDatabaseIdentity",
    "RuntimeDatabaseIdentityError",
    "bind_runtime_database",
    "calculate_schema_fingerprint",
    "initialize_runtime_database",
    "validate_runtime_database",
]
