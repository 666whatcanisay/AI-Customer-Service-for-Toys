from __future__ import annotations

import json
import logging
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Mapping


_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
}
_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|cookie|credential|password|secret|token)\s*[:=]\s*[^\s,;]+"
)
_URL_USERINFO = re.compile(r"(?i)(https?://)[^/@\s]+@")


def sanitize(value: object) -> object:
    if isinstance(value, Mapping):
        output: dict[str, object] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            lowered = key.casefold()
            output[key] = (
                "[REDACTED]"
                if any(part in lowered for part in _SENSITIVE_KEYS)
                else sanitize(child)
            )
        return output
    if isinstance(value, (list, tuple)):
        return [sanitize(child) for child in value]
    if isinstance(value, str):
        text = _URL_USERINFO.sub(r"\1[REDACTED]@", value)
        text = _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
        return text[:2048]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2048]


class _JsonFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "event": getattr(record, "event", "AGENT_LOG"),
            "status": getattr(record, "event_status", "INFO"),
            "metadata": sanitize(getattr(record, "metadata", {})),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class SafeAgentLogger:
    """Structured local logger that never records exception text or credentials."""

    def __init__(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.path = target
        self._logger = logging.getLogger(f"channel_agent.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = RotatingFileHandler(
            target,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(_JsonFormatter())
        self._logger.addHandler(handler)

    def event(
        self,
        event: str,
        status: str,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self._logger.info(
            "channel-agent-event",
            extra={
                "event": event,
                "event_status": status,
                "metadata": sanitize(dict(metadata or {})),
            },
        )

    def error(self, event: str, error: BaseException) -> None:
        self.event(
            event,
            "ERROR",
            {"error_code": type(error).__name__.upper()},
        )

    def close(self) -> None:
        handlers = list(self._logger.handlers)
        for handler in handlers:
            handler.flush()
            handler.close()
            self._logger.removeHandler(handler)


__all__ = ["SafeAgentLogger", "sanitize"]
