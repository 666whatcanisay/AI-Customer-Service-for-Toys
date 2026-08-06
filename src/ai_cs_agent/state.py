from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock

from .models import AgentStatus, RuntimeState, utc_now_text


class RuntimeStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def load(self) -> RuntimeState:
        with self._lock:
            if not self.path.exists():
                return RuntimeState()
            try:
                value = json.loads(self._read_text_with_retry())
                if not isinstance(value, dict):
                    raise ValueError
                return RuntimeState.from_dict(value)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                return RuntimeState(
                    agent_status=AgentStatus.FAILED,
                    last_error={
                        "code": "STATE_CORRUPT",
                        "message": "运行状态文件不可读，需要人工恢复。",
                    },
                )

    def save(self, state: RuntimeState) -> None:
        state.updated_at = utc_now_text()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        data = json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n"
        with self._lock:
            temporary.write_text(data, encoding="utf-8")
            self._replace_with_retry(temporary)

    def _read_text_with_retry(self) -> str:
        for attempt in range(5):
            try:
                return self.path.read_text(encoding="utf-8")
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
        raise AssertionError("state read retry loop exited unexpectedly")

    def _replace_with_retry(self, temporary: Path) -> None:
        for attempt in range(5):
            try:
                os.replace(temporary, self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
