from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Condition, RLock


class RuntimeMaintenanceError(RuntimeError):
    pass


class RuntimeMaintenanceBarrier:
    """A process-local barrier that establishes a quiet backup boundary."""

    def __init__(self) -> None:
        self._condition = Condition(RLock())
        self._quiescing = False
        self._in_flight = 0

    @contextmanager
    def operation(self) -> Iterator[None]:
        with self._condition:
            if self._quiescing:
                raise RuntimeMaintenanceError(
                    "runtime is quiesced for a consistent backup"
                )
            self._in_flight += 1
        try:
            yield
        finally:
            with self._condition:
                self._in_flight -= 1
                self._condition.notify_all()

    @contextmanager
    def quiesce(self, *, timeout_seconds: float = 30.0) -> Iterator[None]:
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        with self._condition:
            if self._quiescing:
                raise RuntimeMaintenanceError("runtime is already quiescing")
            self._quiescing = True
            while self._in_flight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._quiescing = False
                    self._condition.notify_all()
                    raise RuntimeMaintenanceError(
                        "in-flight runtime work did not drain before backup"
                    )
                self._condition.wait(remaining)
        try:
            yield
        finally:
            with self._condition:
                self._quiescing = False
                self._condition.notify_all()

    @property
    def in_flight(self) -> int:
        with self._condition:
            return self._in_flight


@dataclass(frozen=True, slots=True)
class RuntimeBackupManifest:
    backup_epoch: str
    created_at: datetime
    destination: Path
    projection_reconciliation: Mapping[str, int]
    high_water_marks: Mapping[str, int]
    artifacts: tuple[Mapping[str, object], ...]


class RuntimeBackupSet:
    """Create one auditable backup set after the caller establishes quiescence."""

    def __init__(
        self,
        databases: Mapping[str, str | Path],
        *,
        assets: Mapping[str, str | Path] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._databases = {
            role: Path(value).resolve() for role, value in databases.items()
        }
        self._assets = {
            role: Path(value).resolve() for role, value in (assets or {}).items()
        }
        self._clock = clock

    def create(
        self,
        destination: str | Path,
        *,
        projection_reconciliation: Mapping[str, int],
        high_water_marks: Mapping[str, int],
    ) -> RuntimeBackupManifest:
        target = Path(destination).resolve()
        if target.exists() and any(target.iterdir()):
            raise RuntimeMaintenanceError("backup destination must be empty")
        target.mkdir(parents=True, exist_ok=True)
        for role, source in (*self._databases.items(), *self._assets.items()):
            if not source.is_file():
                raise RuntimeMaintenanceError(f"backup source is missing: {role}")

        now = self._clock().astimezone(UTC)
        epoch = f"backup:{now.strftime('%Y%m%dT%H%M%S%fZ')}:{uuid.uuid4()}"
        artifacts: list[Mapping[str, object]] = []
        for role, source in sorted(self._databases.items()):
            output = target / f"{_safe_name(role)}.sqlite3"
            _backup_sqlite(source, output)
            artifacts.append(_artifact(role, source, output, "SQLITE_BACKUP"))
        for role, source in sorted(self._assets.items()):
            output = target / f"{_safe_name(role)}{source.suffix}"
            shutil.copy2(source, output)
            artifacts.append(_artifact(role, source, output, "FILE_COPY"))

        payload = {
            "schema": "runtime-backup-set.v1",
            "backup_epoch": epoch,
            "created_at": now.isoformat(),
            "projection_reconciliation": dict(projection_reconciliation),
            "high_water_marks": dict(high_water_marks),
            "artifacts": list(artifacts),
            "whole_file_sha_usage": "BACKUP_EVIDENCE_ONLY",
        }
        (target / "manifest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return RuntimeBackupManifest(
            backup_epoch=epoch,
            created_at=now,
            destination=target,
            projection_reconciliation=dict(projection_reconciliation),
            high_water_marks=dict(high_water_marks),
            artifacts=tuple(artifacts),
        )


def sqlite_high_water(path: str | Path) -> int:
    """Return a deterministic logical row high-water mark for backup evidence."""

    source = Path(path).resolve()
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as connection:
        tables = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        total = 0
        for (table_name,) in tables:
            quoted = str(table_name).replace('"', '""')
            total += int(
                connection.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
            )
        return total


def _backup_sqlite(source: Path, output: Path) -> None:
    with sqlite3.connect(
        f"file:{source.as_posix()}?mode=ro", uri=True
    ) as source_connection, sqlite3.connect(output) as target_connection:
        source_connection.backup(target_connection)
        result = target_connection.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeMaintenanceError(f"backup integrity failed: {source.name}")


def _artifact(
    role: str, source: Path, output: Path, copy_kind: str
) -> Mapping[str, object]:
    return {
        "role": role,
        "copy_kind": copy_kind,
        "source_name": source.name,
        "backup_name": output.name,
        "bytes": output.stat().st_size,
        "sha256": _sha256(output),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    result = "".join(character if character.isalnum() else "-" for character in value)
    return result.strip("-").casefold() or "runtime-artifact"


__all__ = [
    "RuntimeBackupManifest",
    "RuntimeBackupSet",
    "RuntimeMaintenanceBarrier",
    "RuntimeMaintenanceError",
    "sqlite_high_water",
]
