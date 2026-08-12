from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from channel_engine.storage import create_engine_and_session, create_schema


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("database paths must be absolute")
    return path.resolve(strict=False)


def backup(source_value: str, target_value: str) -> dict[str, object]:
    source = _path(source_value)
    target = _path(target_value)
    if not source.is_file() or target.exists():
        raise ValueError("backup requires an existing source and a new target")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro", uri=True
    ) as incoming, sqlite3.connect(target) as outgoing:
        incoming.backup(outgoing)
        integrity = outgoing.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError("database backup integrity check failed")
    return {"status": "PASS", "source": str(source), "backup": str(target)}


def upgrade(database_value: str) -> dict[str, object]:
    database = _path(database_value)
    if not database.is_file():
        raise ValueError("upgrade requires an existing database")
    engine, _sessions = create_engine_and_session(
        f"sqlite:///{database.as_posix()}"
    )
    try:
        create_schema(engine)
    finally:
        engine.dispose()
    return {"status": "PASS", "database": str(database)}


def identity_count(database_value: str) -> dict[str, object]:
    database = _path(database_value)
    with sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro", uri=True
    ) as connection:
        exists = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='runtime_database_identity'"
        ).fetchone()[0]
        count = (
            connection.execute(
                "SELECT COUNT(*) FROM runtime_database_identity"
            ).fetchone()[0]
            if exists
            else 0
        )
    return {"status": "PASS", "identity_count": int(count)}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--source", required=True)
    backup_parser.add_argument("--target", required=True)
    upgrade_parser = subparsers.add_parser("upgrade")
    upgrade_parser.add_argument("--database", required=True)
    count_parser = subparsers.add_parser("identity-count")
    count_parser.add_argument("--database", required=True)
    arguments = parser.parse_args()
    if arguments.command == "backup":
        result = backup(arguments.source, arguments.target)
    elif arguments.command == "upgrade":
        result = upgrade(arguments.database)
    else:
        result = identity_count(arguments.database)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
