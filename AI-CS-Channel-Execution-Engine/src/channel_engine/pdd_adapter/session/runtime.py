from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import AwareDatetime, Field

from channel_engine.channel.adapter_foundation import FakeChannelAdapter
from channel_engine.pdd_adapter._base import PDDPrototypeModel
from channel_engine.session.manager import ChannelInstanceManager
from channel_engine.session.models import (
    ChannelInstanceStatus,
    ChannelInstanceView,
    ChannelSessionStatus,
    CredentialReference,
)


class PDDSessionStatus(StrEnum):
    CREATED = "CREATED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    EXPIRED = "EXPIRED"


class PDDSession(PDDPrototypeModel):
    session_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    status: PDDSessionStatus
    last_seen: AwareDatetime
    instance_id: str = Field(min_length=1, max_length=128)
    failure_code: str | None = Field(default=None, max_length=128)


class _ReadOnlyPDDSessionAdapter(FakeChannelAdapter):
    """Internal lifecycle shim; no authorization verifier means writes deny closed."""

    adapter_name = "PDDPrototypeSessionLifecycleAdapter"

    def __init__(self, store_id: str) -> None:
        super().__init__(channel="pdd", store_id=store_id)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def project_pdd_session(view: ChannelInstanceView) -> PDDSession:
    instance = view.instance
    session = view.session
    if session is None:
        raise RuntimeError("PDD channel instance has no active session")

    if (
        instance.status is ChannelInstanceStatus.STOPPED
        or session.status is ChannelSessionStatus.EXPIRED
    ):
        status = PDDSessionStatus.EXPIRED
    elif instance.status in {
        ChannelInstanceStatus.DEGRADED,
        ChannelInstanceStatus.FAILED,
    } or session.status is ChannelSessionStatus.FAILED:
        status = PDDSessionStatus.DEGRADED
    elif (
        instance.status is ChannelInstanceStatus.AUTH_REQUIRED
        or session.status is ChannelSessionStatus.AUTH_REQUIRED
    ):
        status = PDDSessionStatus.AUTH_REQUIRED
    elif (
        instance.status is ChannelInstanceStatus.CONNECTED
        and session.status is ChannelSessionStatus.CONNECTED
    ):
        status = PDDSessionStatus.CONNECTED
    else:
        status = PDDSessionStatus.CREATED

    last_seen = session.heartbeat_time or session.updated_at or instance.updated_at
    return PDDSession(
        session_id=session.session_id,
        store_id=instance.store_id,
        status=status,
        last_seen=_aware(last_seen),
        instance_id=instance.instance_id,
        failure_code=session.failure_code or instance.failure_code,
    )


class PDDPrototypeSessionRuntime:
    """Thin PDD lifecycle facade over the durable ChannelSession Runtime."""

    def __init__(self, manager: ChannelInstanceManager) -> None:
        self._manager = manager
        self._lifecycle_adapters: dict[str, _ReadOnlyPDDSessionAdapter] = {}

    def create(
        self,
        *,
        store_id: str,
        credential_ref: CredentialReference,
        instance_id: str | None = None,
    ) -> PDDSession:
        adapter = _ReadOnlyPDDSessionAdapter(store_id)
        instance = self._manager.create_instance(
            platform="pdd",
            store_id=store_id,
            adapter_type=adapter.adapter_name,
            credential_ref=credential_ref,
            adapter=adapter,
            instance_id=instance_id,
        )
        self._lifecycle_adapters[instance.instance_id] = adapter
        return project_pdd_session(self._manager.view(instance.instance_id))

    def get(self, instance_id: str) -> PDDSession:
        return project_pdd_session(self._manager.view(instance_id))

    def start(self, instance_id: str) -> PDDSession:
        return project_pdd_session(self._manager.start_instance(instance_id))

    def heartbeat(self, instance_id: str) -> PDDSession:
        return project_pdd_session(self._manager.heartbeat_instance(instance_id))

    def recover(self, instance_id: str) -> PDDSession:
        return project_pdd_session(self._manager.recover_instance(instance_id))

    def stop(self, instance_id: str) -> PDDSession:
        return project_pdd_session(self._manager.stop_instance(instance_id))

    def simulate_adapter_degraded(
        self,
        instance_id: str,
        reason_code: str = "PDD_PROTOTYPE_PAGE_UNAVAILABLE",
    ) -> PDDSession:
        adapter = self._lifecycle_adapters[instance_id]
        adapter.simulate_degraded(reason_code)
        return self.heartbeat(instance_id)


__all__ = [
    "PDDPrototypeSessionRuntime",
    "PDDSession",
    "PDDSessionStatus",
    "project_pdd_session",
]
