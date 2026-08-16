from pathlib import Path

from scripts.support.manage_channel_engine_database import (
    backup,
    identity_count,
    upgrade,
)


def test_database_tool_creates_integrity_checked_clone_and_schema(tmp_path: Path) -> None:
    database = (tmp_path / "source.sqlite3").resolve()
    clone = (tmp_path / "clone.sqlite3").resolve()
    database.touch()

    # The explicit upgrade command owns all DDL; ordinary startup never calls it.
    upgrade(str(database))
    result = backup(str(database), str(clone))

    assert result["status"] == "PASS"
    assert clone.is_file()
    assert identity_count(str(clone))["identity_count"] == 0
