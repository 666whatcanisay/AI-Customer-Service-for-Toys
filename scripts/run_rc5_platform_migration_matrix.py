#!/usr/bin/env python3
"""Validate RC5 Platform migrations against disposable SQLite clones only."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AI_CS_ROOT = ROOT.parent / "AI-CS"
HEAD = "0018_store_platform_bindings_v1"
ROLLBACK_REVISION = "0013_user_management_v1"
PROTECTED_TABLES = (
    "users",
    "roles",
    "stores",
    "user_store_bindings",
    "product_knowledge_publications",
)


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as target_db:
        source_db.backup(target_db)


def database_snapshot(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version LIMIT 1"
        ).fetchone()
        return {
            "revision": revision[0] if revision else None,
            "table_count": len(tables),
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "protected_row_counts": {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in PROTECTED_TABLES
                if table in tables
            },
        }


def alembic_config(ai_cs_root: Path, database: Path) -> Config:
    platform_root = ai_cs_root / "platform_backend"
    config = Config(str(platform_root / "alembic.ini"))
    config.set_main_option("script_location", str(platform_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(platform_root))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    return config


def assert_healthy(snapshot: dict[str, Any], revision: str) -> None:
    if snapshot["revision"] != revision:
        raise RuntimeError(f"expected revision {revision}, got {snapshot['revision']}")
    if snapshot["integrity"] != "ok" or snapshot["foreign_key_violations"] != 0:
        raise RuntimeError("SQLite integrity or foreign-key validation failed")


def assert_counts_preserved(before: dict[str, Any], after: dict[str, Any]) -> None:
    before_counts = before["protected_row_counts"]
    after_counts = after["protected_row_counts"]
    for table, count in before_counts.items():
        if after_counts.get(table) != count:
            raise RuntimeError(f"protected row count changed for {table}")


def exercise_database(
    *,
    ai_cs_root: Path,
    database: Path,
    expected_before: str,
    exercise_rollback: bool,
) -> dict[str, Any]:
    config = alembic_config(ai_cs_root, database)
    before = database_snapshot(database)
    assert_healthy(before, expected_before)
    command.upgrade(config, "head")
    after_upgrade = database_snapshot(database)
    assert_healthy(after_upgrade, HEAD)
    assert_counts_preserved(before, after_upgrade)
    result: dict[str, Any] = {"before": before, "after_upgrade": after_upgrade}
    if exercise_rollback:
        command.downgrade(config, ROLLBACK_REVISION)
        after_downgrade = database_snapshot(database)
        assert_healthy(after_downgrade, ROLLBACK_REVISION)
        assert_counts_preserved(before, after_downgrade)
        command.upgrade(config, "head")
        after_reupgrade = database_snapshot(database)
        assert_healthy(after_reupgrade, HEAD)
        assert_counts_preserved(before, after_reupgrade)
        result |= {
            "after_downgrade": after_downgrade,
            "after_reupgrade": after_reupgrade,
        }
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--ai-cs-root", type=Path, default=DEFAULT_AI_CS_ROOT)
    result.add_argument("--output-root", type=Path, required=True)
    result.add_argument("--historical-database", type=Path, required=True)
    result.add_argument("--current-database", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    output_root = args.output_root.resolve()
    allowed_root = (ROOT / ".runtime").resolve()
    if allowed_root not in output_root.parents:
        raise RuntimeError(f"output root must stay inside {allowed_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "schema_version": "rc5-platform-migration-matrix.v1",
        "started_at": datetime.now(UTC).isoformat(),
        "source_head": HEAD,
        "rollback_revision": ROLLBACK_REVISION,
        "production_database_mutations": 0,
        "cases": {},
        "status": "STARTED",
    }
    try:
        empty = output_root / "empty-to-head.sqlite3"
        config = alembic_config(args.ai_cs_root.resolve(), empty)
        command.upgrade(config, "head")
        empty_head = database_snapshot(empty)
        assert_healthy(empty_head, HEAD)
        command.downgrade(config, ROLLBACK_REVISION)
        empty_rollback = database_snapshot(empty)
        assert_healthy(empty_rollback, ROLLBACK_REVISION)
        command.upgrade(config, "head")
        empty_reupgrade = database_snapshot(empty)
        assert_healthy(empty_reupgrade, HEAD)
        result["cases"]["empty_database"] = {
            "after_upgrade": empty_head,
            "after_downgrade": empty_rollback,
            "after_reupgrade": empty_reupgrade,
        }

        historical_clone = output_root / "historical-0013-clone.sqlite3"
        sqlite_backup(args.historical_database.resolve(), historical_clone)
        result["cases"]["historical_0013_clone"] = exercise_database(
            ai_cs_root=args.ai_cs_root.resolve(),
            database=historical_clone,
            expected_before=ROLLBACK_REVISION,
            exercise_rollback=True,
        )

        current_clone = output_root / "current-0018-clone.sqlite3"
        sqlite_backup(args.current_database.resolve(), current_clone)
        result["cases"]["current_0018_clone"] = exercise_database(
            ai_cs_root=args.ai_cs_root.resolve(),
            database=current_clone,
            expected_before=HEAD,
            exercise_rollback=False,
        )
        result["status"] = "PASS"
    except Exception as exc:
        result["status"] = "FAIL"
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["completed_at"] = datetime.now(UTC).isoformat()
    report = output_root / "migration-matrix.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
