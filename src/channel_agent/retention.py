from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class TransientBusinessDataPolicy:
    """Bounded client cache policy; AI-CS remains the business system of record."""

    maximum_age: timedelta = timedelta(minutes=30)
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    _TRANSIENT_NAMES = (
        "assistant-feed.json",
        "assistant-feed-before-send.json",
        "conversation-buffer.sqlite3",
        "conversation-buffer.sqlite3-wal",
        "conversation-buffer.sqlite3-shm",
    )

    def purge_expired(self, data_root: str | Path) -> tuple[str, ...]:
        root = Path(data_root).resolve() / "runtime" / "real-pdd-assistant"
        cutoff = self.clock().astimezone(UTC).timestamp() - self.maximum_age.total_seconds()
        removed: list[str] = []
        for name in self._TRANSIENT_NAMES:
            target = root / name
            try:
                if target.is_file() and target.stat().st_mtime < cutoff:
                    target.unlink()
                    removed.append(name)
            except OSError:
                continue
        return tuple(removed)

    def purge_on_safe_stop(self, data_root: str | Path) -> tuple[str, ...]:
        root = Path(data_root).resolve() / "runtime" / "real-pdd-assistant"
        removed: list[str] = []
        for name in self._TRANSIENT_NAMES:
            target = root / name
            try:
                target.unlink(missing_ok=True)
                if not target.exists():
                    removed.append(name)
            except OSError:
                continue
        return tuple(removed)


__all__ = ["TransientBusinessDataPolicy"]
