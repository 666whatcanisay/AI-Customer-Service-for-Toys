from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import RLock

from channel_engine.channel import (
    AdapterHealth,
    AdapterHealthStatus,
    AdapterLifecycleState,
    ChannelAdapterV1,
    CursorAckChannelAdapterV1,
)
from channel_engine.models.entities import new_id, utc_now

from .credential import CredentialProvider, CredentialUnavailable
from .delivery import MessageReliabilityService
from .models import (
    ChannelInstance,
    ChannelInstanceStatus,
    ChannelInstanceView,
    ChannelSession,
    ChannelSessionStatus,
    CredentialReference,
    InboundEnvelope,
    MessageDelivery,
)
from .persistence import ChannelSessionStore, SessionRecordNotFound
from .state_machine import transition_instance, transition_session


class ChannelInstanceError(RuntimeError):
    pass


class ChannelInstanceManager:
    def __init__(
        self,
        store: ChannelSessionStore,
        credential_provider: CredentialProvider,
        delivery: MessageReliabilityService,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._credentials = credential_provider
        self._delivery = delivery
        self._clock = clock
        self._adapters: dict[str, ChannelAdapterV1] = {}
        self._lock = RLock()

    @property
    def delivery(self) -> MessageReliabilityService:
        return self._delivery

    def create_instance(
        self,
        *,
        platform: str,
        store_id: str,
        adapter_type: str,
        credential_ref: CredentialReference,
        adapter: ChannelAdapterV1,
        instance_id: str | None = None,
    ) -> ChannelInstance:
        self._assert_adapter_binding(adapter, platform, store_id)
        with self._lock:
            existing = self._store.find_instance(platform, store_id)
            if existing is not None:
                if existing.adapter_type != adapter_type:
                    raise ChannelInstanceError(
                        "existing store binding uses another adapter type"
                    )
                active = self._store.get_active_session(existing.instance_id)
                if active is None or active.credential_ref != credential_ref:
                    raise ChannelInstanceError(
                        "existing store binding uses another credential reference"
                    )
                self._adapters[existing.instance_id] = adapter
                self._resume_adapter(existing.instance_id, adapter)
                return existing
            now = self._clock()
            resolved_instance_id = instance_id or new_id("channel-instance")
            session_id = new_id("channel-session")
            instance = ChannelInstance(
                instance_id=resolved_instance_id,
                platform=platform,
                store_id=store_id,
                status=ChannelInstanceStatus.CREATED,
                adapter_type=adapter_type,
                active_session_id=session_id,
                created_at=now,
                updated_at=now,
            )
            session = ChannelSession(
                session_id=session_id,
                instance_id=resolved_instance_id,
                status=ChannelSessionStatus.CREATED,
                credential_ref=credential_ref,
                created_at=now,
                updated_at=now,
            )
            self._store.create_instance(instance, session)
            self._adapters[resolved_instance_id] = adapter
            self._resume_adapter(resolved_instance_id, adapter)
            return instance

    def attach_adapter(self, instance_id: str, adapter: ChannelAdapterV1) -> None:
        instance = self._store.get_instance(instance_id)
        self._assert_adapter_binding(adapter, instance.platform, instance.store_id)
        with self._lock:
            self._adapters[instance_id] = adapter
            self._resume_adapter(instance_id, adapter)

    def get_instance(self, instance_id: str) -> ChannelInstance:
        return self._store.get_instance(instance_id)

    def list_instances(self) -> tuple[ChannelInstance, ...]:
        return self._store.list_instances()

    def start_instance(self, instance_id: str) -> ChannelInstanceView:
        with self._lock:
            instance = self._store.get_instance(instance_id)
            adapter = self._require_adapter(instance_id)
            session = self._store.get_active_session(instance_id)
            if (
                instance.status is ChannelInstanceStatus.CONNECTED
                and session is not None
                and session.status is ChannelSessionStatus.CONNECTED
                and not self._expired(session)
                and adapter.lifecycle_state is AdapterLifecycleState.CONNECTED
            ):
                return self.view(instance_id)

            if session is None or session.status in {
                ChannelSessionStatus.EXPIRED,
                ChannelSessionStatus.FAILED,
            }:
                session = self._new_session(instance)
                instance = instance.model_copy(
                    update={"active_session_id": session.session_id}
                )

            instance = transition_instance(
                instance,
                ChannelInstanceStatus.STARTING,
                self._clock(),
                active_session_id=session.session_id,
            )
            self._store.save_instance(instance)
            try:
                lease = self._credentials.acquire(session.credential_ref)
            except CredentialUnavailable:
                if session.status is ChannelSessionStatus.CREATED:
                    session = transition_session(
                        session,
                        ChannelSessionStatus.AUTH_REQUIRED,
                        self._clock(),
                        failure_code="CREDENTIAL_REFERENCE_UNAVAILABLE",
                    )
                else:
                    session = session.model_copy(
                        update={
                            "failure_code": "CREDENTIAL_REFERENCE_UNAVAILABLE",
                            "updated_at": self._clock(),
                        }
                    )
                self._store.save_session(session)
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.AUTH_REQUIRED,
                    self._clock(),
                    failure_code="CREDENTIAL_REFERENCE_UNAVAILABLE",
                )
                self._store.save_instance(instance)
                return self.view(instance_id)

            try:
                adapter_status = adapter.connect()
                if adapter_status.lifecycle is not AdapterLifecycleState.CONNECTED:
                    raise ChannelInstanceError("adapter did not enter CONNECTED")
            except Exception:
                session = transition_session(
                    session,
                    ChannelSessionStatus.FAILED,
                    self._clock(),
                    failure_code="ADAPTER_CONNECT_FAILED",
                )
                self._store.save_session(session)
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.DEGRADED,
                    self._clock(),
                    failure_code="ADAPTER_CONNECT_FAILED",
                )
                self._store.save_instance(instance)
                return self.view(instance_id)

            now = self._clock()
            if session.status is ChannelSessionStatus.CONNECTED:
                session = session.model_copy(
                    update={
                        "credential_lease_ref": lease.lease_ref,
                        "heartbeat_time": now,
                        "expires_at": lease.expires_at,
                        "failure_code": None,
                        "updated_at": now,
                    }
                )
            else:
                session = transition_session(
                    session,
                    ChannelSessionStatus.CONNECTED,
                    now,
                    credential_lease_ref=lease.lease_ref,
                    heartbeat_time=now,
                    expires_at=lease.expires_at,
                )
            self._store.save_session(session)
            instance = transition_instance(
                instance,
                ChannelInstanceStatus.CONNECTED,
                now,
                active_session_id=session.session_id,
            )
            self._store.save_instance(instance)
            return self.view(instance_id)

    def stop_instance(self, instance_id: str) -> ChannelInstanceView:
        with self._lock:
            instance = self._store.get_instance(instance_id)
            if instance.status is ChannelInstanceStatus.STOPPED:
                return self.view(instance_id)
            adapter = self._require_adapter(instance_id)
            session = self._store.get_active_session(instance_id)
            try:
                adapter.disconnect()
            except Exception:
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.FAILED,
                    self._clock(),
                    failure_code="ADAPTER_DISCONNECT_FAILED",
                )
                self._store.save_instance(instance)
                return self.view(instance_id)
            now = self._clock()
            if session is not None and session.status in {
                ChannelSessionStatus.CONNECTED,
                ChannelSessionStatus.AUTH_REQUIRED,
            }:
                session = transition_session(
                    session,
                    ChannelSessionStatus.EXPIRED,
                    now,
                    failure_code="SESSION_STOPPED",
                )
                self._store.save_session(session)
            instance = transition_instance(
                instance,
                ChannelInstanceStatus.STOPPED,
                now,
            )
            self._store.save_instance(instance)
            return self.view(instance_id)

    def start_all(self) -> tuple[ChannelInstanceView, ...]:
        results: list[ChannelInstanceView] = []
        for instance in self._store.list_instances():
            try:
                results.append(self.start_instance(instance.instance_id))
            except Exception:
                results.append(self._fail_instance(instance.instance_id))
        return tuple(results)

    def stop_all(self) -> tuple[ChannelInstanceView, ...]:
        return tuple(
            self.stop_instance(instance.instance_id)
            for instance in reversed(self._store.list_instances())
        )

    def heartbeat_instance(self, instance_id: str) -> ChannelInstanceView:
        with self._lock:
            instance = self._store.get_instance(instance_id)
            session = self._store.get_active_session(instance_id)
            adapter = self._adapters.get(instance_id)
            if adapter is None:
                return self._degrade(instance, "ADAPTER_NOT_ATTACHED")
            if (
                session is not None
                and session.status is ChannelSessionStatus.CONNECTED
                and self._expired(session)
            ):
                now = self._clock()
                session = transition_session(
                    session,
                    ChannelSessionStatus.EXPIRED,
                    now,
                    failure_code="CREDENTIAL_LEASE_EXPIRED",
                )
                self._store.save_session(session)
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.AUTH_REQUIRED,
                    now,
                    failure_code="CREDENTIAL_LEASE_EXPIRED",
                )
                self._store.save_instance(instance)
                return self.view(instance_id)
            health = self._safe_health(adapter)
            if (
                instance.status is ChannelInstanceStatus.CONNECTED
                and health.status is not AdapterHealthStatus.HEALTHY
            ):
                now = self._clock()
                if session is not None and session.status is ChannelSessionStatus.CONNECTED:
                    session = transition_session(
                        session,
                        ChannelSessionStatus.FAILED,
                        now,
                        failure_code="ADAPTER_HEARTBEAT_FAILED",
                    )
                    self._store.save_session(session)
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.DEGRADED,
                    now,
                    failure_code="ADAPTER_HEARTBEAT_FAILED",
                )
                self._store.save_instance(instance)
            elif session is not None and session.status is ChannelSessionStatus.CONNECTED:
                session = session.model_copy(
                    update={"heartbeat_time": self._clock(), "updated_at": self._clock()}
                )
                self._store.save_session(session)
            return self.view(instance_id)

    def heartbeat_all(self) -> tuple[ChannelInstanceView, ...]:
        return tuple(
            self.heartbeat_instance(instance.instance_id)
            for instance in self._store.list_instances()
        )

    def recover_instance(self, instance_id: str) -> ChannelInstanceView:
        with self._lock:
            instance = self._store.get_instance(instance_id)
            adapter = self._require_adapter(instance_id)
            session = self._store.get_active_session(instance_id)
            if adapter.lifecycle_state is AdapterLifecycleState.DEGRADED:
                adapter_status = adapter.recover()
                if adapter_status.lifecycle is not AdapterLifecycleState.CONNECTED:
                    return self.view(instance_id)
            if (
                session is not None
                and session.status is ChannelSessionStatus.CONNECTED
                and not self._expired(session)
                and instance.status is ChannelInstanceStatus.DEGRADED
            ):
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.CONNECTED,
                    self._clock(),
                )
                self._store.save_instance(instance)
                return self.view(instance_id)
            return self.start_instance(instance_id)

    def recover_all(self) -> bool:
        results: list[ChannelInstanceView] = []
        for instance in self._store.list_instances():
            if instance.status in {
                ChannelInstanceStatus.DEGRADED,
                ChannelInstanceStatus.AUTH_REQUIRED,
                ChannelInstanceStatus.FAILED,
            }:
                try:
                    results.append(self.recover_instance(instance.instance_id))
                except Exception:
                    results.append(self.view(instance.instance_id))
            else:
                results.append(self.view(instance.instance_id))
        return bool(results) and all(
            item.instance.status is ChannelInstanceStatus.CONNECTED
            for item in results
        )

    def mark_degraded(self, instance_id: str, reason_code: str) -> None:
        with self._lock:
            instance = self._store.get_instance(instance_id)
            if instance.status is ChannelInstanceStatus.CONNECTED:
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.DEGRADED,
                    self._clock(),
                    failure_code=reason_code,
                )
                self._store.save_instance(instance)

    def poll_messages(
        self, instance_id: str, *, limit: int = 100
    ) -> tuple[MessageDelivery, ...]:
        instance = self._store.get_instance(instance_id)
        session = self._store.get_active_session(instance_id)
        if (
            instance.status is not ChannelInstanceStatus.CONNECTED
            or session is None
            or session.status is not ChannelSessionStatus.CONNECTED
        ):
            raise ChannelInstanceError("CONNECTED channel session is required")
        adapter = self._require_adapter(instance_id)
        if not isinstance(adapter, CursorAckChannelAdapterV1):
            raise ChannelInstanceError(
                "adapter does not implement cursor/ACK reliability protocol"
            )
        envelopes = adapter.receive_envelopes(limit=limit)
        if envelopes:
            self._delivery.persist(
                instance_id,
                tuple(
                    InboundEnvelope(
                        message=item.message,
                        source_cursor=item.source_cursor,
                        source_sequence=item.source_sequence,
                    )
                    for item in envelopes
                ),
            )
            adapter.acknowledge(envelopes[-1].source_cursor)
        return self._delivery.receive_pending(instance_id, limit=limit)

    def view(self, instance_id: str) -> ChannelInstanceView:
        instance = self._store.get_instance(instance_id)
        session = self._store.get_active_session(instance_id)
        adapter = self._adapters.get(instance_id)
        health = (
            self._safe_health(adapter)
            if adapter is not None
            else self._unhealthy(instance.platform, "AdapterNotAttached")
        )
        return ChannelInstanceView(
            instance=instance,
            session=session,
            adapter_health=health.status,
            real_platform_connected=health.real_platform_connected,
            checked_at=health.checked_at,
        )

    def list_views(self) -> tuple[ChannelInstanceView, ...]:
        return tuple(
            self.view(instance.instance_id)
            for instance in self._store.list_instances()
        )

    def _new_session(self, instance: ChannelInstance) -> ChannelSession:
        previous = self._store.get_active_session(instance.instance_id)
        if previous is None:
            raise ChannelInstanceError("instance has no credential reference")
        now = self._clock()
        session = ChannelSession(
            session_id=new_id("channel-session"),
            instance_id=instance.instance_id,
            status=ChannelSessionStatus.CREATED,
            credential_ref=previous.credential_ref,
            created_at=now,
            updated_at=now,
        )
        self._store.create_session(session)
        return session

    def _fail_instance(self, instance_id: str) -> ChannelInstanceView:
        instance = self._store.get_instance(instance_id)
        if instance.status is not ChannelInstanceStatus.FAILED:
            try:
                instance = transition_instance(
                    instance,
                    ChannelInstanceStatus.FAILED,
                    self._clock(),
                    failure_code="INSTANCE_START_EXCEPTION",
                )
                self._store.save_instance(instance)
            except Exception:
                pass
        return self.view(instance_id)

    def _degrade(self, instance: ChannelInstance, reason_code: str) -> ChannelInstanceView:
        if instance.status is ChannelInstanceStatus.CONNECTED:
            instance = transition_instance(
                instance,
                ChannelInstanceStatus.DEGRADED,
                self._clock(),
                failure_code=reason_code,
            )
            self._store.save_instance(instance)
        return self.view(instance.instance_id)

    def _require_adapter(self, instance_id: str) -> ChannelAdapterV1:
        adapter = self._adapters.get(instance_id)
        if adapter is None:
            raise ChannelInstanceError("channel instance has no attached adapter")
        return adapter

    def _resume_adapter(
        self, instance_id: str, adapter: ChannelAdapterV1
    ) -> None:
        if isinstance(adapter, CursorAckChannelAdapterV1):
            cursor = self._store.get_cursor(instance_id)
            adapter.resume_from(cursor.cursor_value, cursor.last_sequence)

    @staticmethod
    def _assert_adapter_binding(
        adapter: ChannelAdapterV1, platform: str, store_id: str
    ) -> None:
        if not isinstance(adapter, ChannelAdapterV1):
            raise TypeError("adapter does not implement ChannelAdapterV1")
        if adapter.channel != platform or adapter.store_id != store_id:
            raise ChannelInstanceError(
                "adapter platform/store binding does not match instance"
            )

    def _safe_health(self, adapter: ChannelAdapterV1) -> AdapterHealth:
        try:
            return adapter.health_check()
        except Exception as exc:
            return self._unhealthy(adapter.channel, type(exc).__name__)

    def _unhealthy(self, platform: str, error_type: str) -> AdapterHealth:
        return AdapterHealth(
            adapter_name="UnavailableAdapter",
            channel=platform,
            status=AdapterHealthStatus.UNHEALTHY,
            checked_at=self._clock(),
            real_platform_connected=False,
            details={"error_type": error_type},
        )

    def _expired(self, session: ChannelSession) -> bool:
        if session.expires_at is None:
            return True
        expires_at = session.expires_at
        now = self._clock()
        if expires_at.tzinfo is None and now.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None and expires_at.tzinfo is not None:
            now = now.replace(tzinfo=timezone.utc)
        return expires_at <= now


__all__ = ["ChannelInstanceError", "ChannelInstanceManager"]
