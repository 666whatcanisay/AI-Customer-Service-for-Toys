"""Fail-closed identity binding for the Platform SQLite runtime database.

The internal row is the database's logical identity.  The adjacent sidecar binds
that identity to one canonical runtime path.  A mutable whole-file hash is
deliberately excluded from normal startup validation; it belongs in backup and
release evidence only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Literal
from uuid import UUID, uuid4


EXPECTED_REVISION = "0019_runtime_database_identity_v1"
DATABASE_ROLE = "PLATFORM"
BINDING_SCHEMA = "ai-cs.runtime-database-binding.v1"
IDENTITY_REVISION = 1
SQLITE_HEADER = b"SQLite format 3\x00"


class DatabaseIdentityError(RuntimeError):
    """Raised when a runtime database cannot be identified safely."""


@dataclass(frozen=True, slots=True)
class RuntimeDatabaseIdentity:
    database_instance_id: str
    database_role: str
    environment_id: str
    identity_revision: int
    schema_fingerprint: str
    created_by_source_commit: str
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
    expected_revision: str
    restore_generation: int
    restored_from_backup_epoch: str | None
    generated_at: str
    tool_version: str = "1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_database_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise DatabaseIdentityError("Platform database path must be absolute")
    return path.resolve(strict=False)


def validate_sqlite_file(path: Path) -> None:
    if not path.is_file():
        raise DatabaseIdentityError(f"Platform database does not exist: {path}")
    if path.stat().st_size <= len(SQLITE_HEADER):
        raise DatabaseIdentityError(f"Platform database is empty or truncated: {path}")
    with path.open("rb") as handle:
        if handle.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise DatabaseIdentityError(f"Platform database is not SQLite: {path}")


def _canonical_rows(connection: sqlite3.Connection, statement: str) -> list[list[Any]]:
    return [list(row) for row in connection.execute(statement).fetchall()]


def calculate_schema_fingerprint(connection: sqlite3.Connection) -> str:
    """Hash only stable schema structure, never mutable row contents."""

    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    schema: dict[str, Any] = {}
    for table in tables:
        escaped = table.replace('"', '""')
        schema[table] = {
            "columns": _canonical_rows(
                connection, f'PRAGMA table_info("{escaped}")'
            ),
            "foreign_keys": _canonical_rows(
                connection, f'PRAGMA foreign_key_list("{escaped}")'
            ),
            "indexes": [],
        }
        for index_row in connection.execute(
            f'PRAGMA index_list("{escaped}")'
        ).fetchall():
            index_name = str(index_row[1])
            index_escaped = index_name.replace('"', '""')
            schema[table]["indexes"].append(
                {
                    "definition": list(index_row),
                    "columns": _canonical_rows(
                        connection, f'PRAGMA index_info("{index_escaped}")'
                    ),
                }
            )
    canonical = json.dumps(
        schema, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _open_checked(path: Path) -> sqlite3.Connection:
    validate_sqlite_file(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        connection.close()
        raise DatabaseIdentityError(f"Platform database integrity check failed: {integrity}")
    return connection


def _revision(connection: sqlite3.Connection) -> str:
    try:
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    except sqlite3.DatabaseError as exc:
        raise DatabaseIdentityError("Platform database has no Alembic revision") from exc
    if len(rows) != 1:
        raise DatabaseIdentityError("Platform database must have exactly one Alembic head")
    return str(rows[0][0])


def _read_identity(connection: sqlite3.Connection) -> RuntimeDatabaseIdentity:
    try:
        rows = connection.execute(
            "SELECT database_instance_id, database_role, environment_id, "
            "identity_revision, schema_fingerprint, created_by_source_commit, "
            "created_at, restore_generation, restored_from_backup_epoch, "
            "last_restored_at FROM runtime_database_identity"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise DatabaseIdentityError("Platform database identity table is missing") from exc
    if len(rows) != 1:
        raise DatabaseIdentityError("Platform database must contain exactly one identity row")
    return RuntimeDatabaseIdentity(**dict(rows[0]))


def _load_binding(path: Path) -> RuntimeDatabaseBindingV1:
    if not path.is_file():
        raise DatabaseIdentityError(f"Platform database binding sidecar is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return RuntimeDatabaseBindingV1(**payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise DatabaseIdentityError("Platform database binding sidecar is invalid") from exc


def validate_runtime_database(
    database_path: str | Path,
    binding_path: str | Path,
    *,
    expected_environment_id: str,
    expected_role: str = DATABASE_ROLE,
) -> RuntimeDatabaseIdentity:
    database = canonical_database_path(database_path)
    binding_file = canonical_database_path(binding_path)
    connection = _open_checked(database)
    try:
        revision = _revision(connection)
        if revision != EXPECTED_REVISION:
            raise DatabaseIdentityError(
                f"Platform database revision is {revision}, expected {EXPECTED_REVISION}"
            )
        identity = _read_identity(connection)
        actual_fingerprint = calculate_schema_fingerprint(connection)
    finally:
        connection.close()
    binding = _load_binding(binding_file)
    if identity.database_role != expected_role or binding.database_role != expected_role:
        raise DatabaseIdentityError("Platform database role mismatch")
    if (
        identity.environment_id != expected_environment_id
        or binding.environment_id != expected_environment_id
    ):
        raise DatabaseIdentityError("Platform database environment mismatch")
    if binding.schema != BINDING_SCHEMA or binding.expected_revision != EXPECTED_REVISION:
        raise DatabaseIdentityError("Platform database binding schema or revision mismatch")
    if Path(binding.canonical_path).resolve(strict=False) != database:
        raise DatabaseIdentityError("Platform database canonical path mismatch")
    parity_fields = (
        "database_instance_id",
        "database_role",
        "environment_id",
        "identity_revision",
        "schema_fingerprint",
        "restore_generation",
        "restored_from_backup_epoch",
    )
    for field in parity_fields:
        if getattr(identity, field) != getattr(binding, field):
            raise DatabaseIdentityError(f"Platform database identity mismatch: {field}")
    if identity.identity_revision != IDENTITY_REVISION:
        raise DatabaseIdentityError("Platform database identity revision is unsupported")
    if identity.schema_fingerprint != actual_fingerprint:
        raise DatabaseIdentityError("Platform database schema fingerprint mismatch")
    try:
        UUID(identity.database_instance_id)
    except ValueError as exc:
        raise DatabaseIdentityError("Platform database instance ID is invalid") from exc
    return identity


def _write_binding(
    binding_path: Path,
    database_path: Path,
    identity: RuntimeDatabaseIdentity,
) -> None:
    binding = RuntimeDatabaseBindingV1(
        schema=BINDING_SCHEMA,
        database_instance_id=identity.database_instance_id,
        database_role=identity.database_role,
        environment_id=identity.environment_id,
        identity_revision=identity.identity_revision,
        schema_fingerprint=identity.schema_fingerprint,
        canonical_path=str(database_path),
        expected_revision=EXPECTED_REVISION,
        restore_generation=identity.restore_generation,
        restored_from_backup_epoch=identity.restored_from_backup_epoch,
        generated_at=utc_now(),
    )
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = binding_path.with_name(f".{binding_path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(asdict(binding), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(binding_path)


def bind_runtime_database(
    database_path: str | Path,
    binding_path: str | Path,
    *,
    environment_id: str,
    source_commit: str,
    mode: Literal["NEW_INSTANCE", "UPGRADE", "RESTORE"],
    backup_epoch: str | None = None,
) -> RuntimeDatabaseIdentity:
    database = canonical_database_path(database_path)
    binding_file = canonical_database_path(binding_path)
    if not environment_id.strip() or not source_commit.strip():
        raise DatabaseIdentityError("Environment ID and source commit are required")
    connection = _open_checked(database)
    try:
        if _revision(connection) != EXPECTED_REVISION:
            raise DatabaseIdentityError(
                f"Database must be migrated to {EXPECTED_REVISION} before binding"
            )
        fingerprint = calculate_schema_fingerprint(connection)
        existing: RuntimeDatabaseIdentity | None
        try:
            existing = _read_identity(connection)
        except DatabaseIdentityError:
            existing = None
        now = utc_now()
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
                raise DatabaseIdentityError("Restore requires an existing logical identity")
            if not backup_epoch or not backup_epoch.strip():
                raise DatabaseIdentityError("Restore requires a backup epoch")
            if existing.environment_id != environment_id.strip():
                raise DatabaseIdentityError(
                    "Restore cannot change the runtime environment"
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
                raise DatabaseIdentityError(
                    "Upgrade requires an existing logical identity"
                )
            if existing.environment_id != environment_id.strip():
                raise DatabaseIdentityError(
                    "Upgrade cannot change the runtime environment"
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
            "INSERT INTO runtime_database_identity (database_role, "
            "database_instance_id, environment_id, identity_revision, "
            "schema_fingerprint, created_by_source_commit, created_at, "
            "restore_generation, restored_from_backup_epoch, last_restored_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
    finally:
        connection.close()
    _write_binding(binding_file, database, identity)
    validate_runtime_database(
        database,
        binding_file,
        expected_environment_id=environment_id.strip(),
    )
    return identity


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "bind-new", "mark-upgraded", "mark-restored"):
        item = subparsers.add_parser(command)
        item.add_argument("--database", required=True)
        item.add_argument("--binding", required=True)
        item.add_argument("--environment-id", required=True)
        if command != "validate":
            item.add_argument("--source-commit", required=True)
        if command == "mark-restored":
            item.add_argument("--backup-epoch", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        identity = validate_runtime_database(
            args.database,
            args.binding,
            expected_environment_id=args.environment_id,
        )
    else:
        identity = bind_runtime_database(
            args.database,
            args.binding,
            environment_id=args.environment_id,
            source_commit=args.source_commit,
            mode=(
                "RESTORE"
                if args.command == "mark-restored"
                else "UPGRADE"
                if args.command == "mark-upgraded"
                else "NEW_INSTANCE"
            ),
            backup_epoch=getattr(args, "backup_epoch", None),
        )
    print(
        json.dumps(
            {
                "status": "PASS",
                "database_instance_id": identity.database_instance_id,
                "database_role": identity.database_role,
                "environment_id": identity.environment_id,
                "identity_revision": identity.identity_revision,
                "schema_fingerprint": identity.schema_fingerprint,
                "restore_generation": identity.restore_generation,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
