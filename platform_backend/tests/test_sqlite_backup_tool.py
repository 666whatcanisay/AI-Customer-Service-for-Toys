from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sqlite3


def _backup_function():
    path = Path(__file__).resolve().parents[2] / "scripts" / "support" / "backup_sqlite_database.py"
    spec = spec_from_file_location("backup_sqlite_database", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.backup


def test_sqlite_backup_tool_creates_integrity_checked_new_file(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE facts(value TEXT NOT NULL)")
        connection.execute("INSERT INTO facts VALUES ('kept')")

    result = _backup_function()(str(source), str(target))

    assert result["integrity"] == "ok"
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT value FROM facts").fetchone()[0] == "kept"
