from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from .models import utc_now_text


_SENSITIVE_KEYS = (
    "cookie",
    "token",
    "password",
    "secret",
    "authorization",
    "customer_message",
    "content",
    "payload",
)
_SENSITIVE_VALUES = ("bearer ", "cookie=", "token=", "password=", "secret=")


class UnsafeEvent(ValueError):
    pass


def _validate_safe(value: object, depth: int = 0) -> None:
    if depth > 6:
        raise UnsafeEvent("event metadata is too deeply nested")
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold()
            if any(marker in normalized for marker in _SENSITIVE_KEYS):
                raise UnsafeEvent("event metadata contains a sensitive field")
            _validate_safe(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 100:
            raise UnsafeEvent("event metadata collection is too large")
        for item in value:
            _validate_safe(item, depth + 1)
    elif isinstance(value, str):
        normalized = value.casefold()
        if len(value) > 512 or any(marker in normalized for marker in _SENSITIVE_VALUES):
            raise UnsafeEvent("event metadata contains sensitive material")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise UnsafeEvent("event metadata type is unsupported")


class EventLog:
    """Append-only structured JSONL lifecycle evidence."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def append(self, event_type: str, status: str, metadata: dict[str, Any]) -> None:
        _validate_safe(metadata)
        event = {
            "schema_version": "1.0",
            "event_type": event_type,
            "status": status,
            "timestamp": utc_now_text(),
            "metadata": metadata,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
