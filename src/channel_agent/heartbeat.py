from __future__ import annotations

from collections.abc import Callable
from threading import Event, RLock, Thread


class HeartbeatManager:
    """Small restartable scheduler; the callback owns network recovery policy."""

    def __init__(
        self,
        callback: Callable[[], object],
        interval_seconds: float,
        *,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._callback = callback
        self._interval_seconds = float(interval_seconds)
        self._on_error = on_error
        self._stop = Event()
        self._lock = RLock()
        self._thread: Thread | None = None

    @property
    def interval_seconds(self) -> float:
        with self._lock:
            return self._interval_seconds

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def set_interval(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        with self._lock:
            self._interval_seconds = float(interval_seconds)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(
                target=self._run,
                name="channel-agent-heartbeat",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout_seconds)
        with self._lock:
            if self._thread is thread and (thread is None or not thread.is_alive()):
                self._thread = None

    def run_once(self) -> None:
        try:
            self._callback()
        except Exception as exc:
            if self._on_error is not None:
                self._on_error(exc)

    def _run(self) -> None:
        while True:
            if self._stop.wait(self.interval_seconds):
                return
            self.run_once()


__all__ = ["HeartbeatManager"]
