from __future__ import annotations

from threading import Lock

from channel_engine.models.entities import utc_now

from .protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelAdapter,
)


class AdapterAlreadyRegistered(ValueError):
    pass


class AdapterNotRegistered(LookupError):
    pass


class AdapterRegistry:
    """Thread-safe registry keyed by normalized channel name."""

    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}
        self._lock = Lock()

    def register(self, adapter: ChannelAdapter) -> bool:
        if not isinstance(adapter, ChannelAdapter):
            raise TypeError("adapter does not implement ChannelAdapter")
        channel = adapter.channel
        with self._lock:
            existing = self._adapters.get(channel)
            if existing is adapter:
                return False
            if existing is not None:
                raise AdapterAlreadyRegistered(
                    f"channel adapter already registered: {channel}"
                )
            self._adapters[channel] = adapter
            return True

    def get(self, channel: str) -> ChannelAdapter:
        with self._lock:
            adapter = self._adapters.get(channel)
        if adapter is None:
            raise AdapterNotRegistered(f"channel adapter is not registered: {channel}")
        return adapter

    def discover(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._adapters))

    def health_check(self) -> dict[str, AdapterHealth]:
        with self._lock:
            adapters = tuple(self._adapters.items())
        report: dict[str, AdapterHealth] = {}
        for channel, adapter in adapters:
            try:
                report[channel] = adapter.health_check()
            except Exception as exc:
                report[channel] = AdapterHealth(
                    adapter_name=type(adapter).__name__,
                    channel=channel,
                    status=AdapterHealthStatus.UNHEALTHY,
                    checked_at=utc_now(),
                    real_platform_connected=False,
                    details={"error_type": type(exc).__name__},
                )
        return report
