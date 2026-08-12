from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def backup(source_value: str, target_value: str) -> dict[str, object]:
    source = Path(source_value).expanduser().resolve(strict=False)
    target = Path(target_value).expanduser().resolve(strict=False)
    if not source.is_file() or source.stat().st_size <= 16:
        raise ValueError("backup source is missing or empty")
    if target.exists():
        raise ValueError("backup target must not already exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro", uri=True
    ) as incoming, sqlite3.connect(target) as outgoing:
        incoming.backup(outgoing)
        integrity = outgoing.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError("SQLite backup integrity check failed")
    return {
        "status": "PASS",
        "source": str(source),
        "backup": str(target),
        "integrity": "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            backup(arguments.source, arguments.target),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
