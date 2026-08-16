from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import datetime

from sqlalchemy import select

from channel_engine.channel import AdapterHealthStatus, ChannelMessageV1
from channel_engine.models.entities import new_id
from channel_engine.reliability import ComponentHealth
from channel_engine.storage import SqlAlchemyUnitOfWork
from channel_engine.storage.orm import (
    ChannelInstanceRow,
    ChannelMessageCursorRow,
    ChannelMessageInboxRow,
    ChannelRuntimeSessionRow,
    ChannelSessionHeartbeatRow,
)

from .models import (
    CHANNEL_SESSION_RUNTIME_VERSION,
    ChannelInstance,
    ChannelSession,
    ChannelSessionStatus,
    CredentialReference,
    InboxMessageState,
    MessageCursor,
    SessionHeartbeat,
)


class SessionRecordNotFound(LookupError):
    pass


class ChannelSessionStore:
    def __init__(
        self, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    ) -> None:
        self._uow_factory = uow_factory

    def create_instance(
        self, instance: ChannelInstance, session: ChannelSession
    ) -> ChannelInstance:
        with self._uow_factory() as uow:
            assert uow.session is not None
            existing = uow.session.scalar(
                select(ChannelInstanceRow).where(
                    ChannelInstanceRow.platform == instance.platform,
                    ChannelInstanceRow.store_id == instance.store_id,
                )
            )
            if existing is not None:
                if (
                    existing.instance_id == instance.instance_id
                    and existing.adapter_type == instance.adapter_type
                ):
                    return self._instance(existing)
                raise ValueError(
                    "platform/store already belongs to another channel instance"
                )
            uow.session.add(self._instance_row(instance))
            uow.session.add(self._session_row(session))
            uow.session.add(
                ChannelMessageCursorRow(
                    instance_id=instance.instance_id,
                    session_runtime_version=CHANNEL_SESSION_RUNTIME_VERSION,
                    cursor_value=None,
                    last_sequence=0,
                    last_acked_sequence=0,
                    revision=0,
                    updated_at=instance.created_at,
                )
            )
            return instance

    def get_instance(self, instance_id: str) -> ChannelInstance:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(ChannelInstanceRow, instance_id)
            if row is None:
                raise SessionRecordNotFound(
                    f"channel instance not found: {instance_id}"
                )
            self._assert_version(row.session_runtime_version)
            return self._instance(row)

    def find_instance(self, platform: str, store_id: str) -> ChannelInstance | None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.scalar(
                select(ChannelInstanceRow).where(
                    ChannelInstanceRow.platform == platform,
                    ChannelInstanceRow.store_id == store_id,
                )
            )
            return self._instance(row) if row is not None else None

    def list_instances(self) -> tuple[ChannelInstance, ...]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            rows = uow.session.scalars(
                select(ChannelInstanceRow).order_by(
                    ChannelInstanceRow.platform,
                    ChannelInstanceRow.store_id,
                    ChannelInstanceRow.instance_id,
                )
            ).all()
            return tuple(self._instance(row) for row in rows)

    def save_instance(self, instance: ChannelInstance) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(ChannelInstanceRow, instance.instance_id)
            if row is None:
                raise SessionRecordNotFound(instance.instance_id)
            self._assert_version(row.session_runtime_version)
            row.status = instance.status.value
            row.active_session_id = instance.active_session_id
            row.failure_code = instance.failure_code
            row.updated_at = instance.updated_at

    def create_session(self, session: ChannelSession) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            if uow.session.get(ChannelRuntimeSessionRow, session.session_id) is not None:
                raise ValueError("channel session already exists")
            uow.session.add(self._session_row(session))

    def get_session(self, session_id: str) -> ChannelSession:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(ChannelRuntimeSessionRow, session_id)
            if row is None:
                raise SessionRecordNotFound(
                    f"channel session not found: {session_id}"
                )
            self._assert_version(row.session_runtime_version)
            return self._session(row)

    def get_active_session(self, instance_id: str) -> ChannelSession | None:
        instance = self.get_instance(instance_id)
        if instance.active_session_id is None:
            return None
        return self.get_session(instance.active_session_id)

    def list_sessions(self, instance_id: str) -> tuple[ChannelSession, ...]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            rows = uow.session.scalars(
                select(ChannelRuntimeSessionRow)
                .where(ChannelRuntimeSessionRow.instance_id == instance_id)
                .order_by(
                    ChannelRuntimeSessionRow.created_at,
                    ChannelRuntimeSessionRow.session_id,
                )
            ).all()
            return tuple(self._session(row) for row in rows)

    def save_session(self, session: ChannelSession) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(ChannelRuntimeSessionRow, session.session_id)
            if row is None:
                raise SessionRecordNotFound(session.session_id)
            self._assert_version(row.session_runtime_version)
            row.status = session.status.value
            row.credential_lease_ref = session.credential_lease_ref
            row.heartbeat_time = session.heartbeat_time
            row.expires_at = session.expires_at
            row.failure_code = session.failure_code
            row.updated_at = session.updated_at

    def get_cursor(self, instance_id: str) -> MessageCursor:
        with self._uow_factory() as uow:
            assert uow.session is not None
            row = uow.session.get(ChannelMessageCursorRow, instance_id)
            if row is None:
                raise SessionRecordNotFound(
                    f"message cursor not found: {instance_id}"
                )
            self._assert_version(row.session_runtime_version)
            return self._cursor(row)

    def append_heartbeats(self, heartbeats: Iterable[SessionHeartbeat]) -> None:
        with self._uow_factory() as uow:
            assert uow.session is not None
            for item in heartbeats:
                uow.session.add(
                    ChannelSessionHeartbeatRow(
                        heartbeat_id=item.heartbeat_id,
                        session_runtime_version=CHANNEL_SESSION_RUNTIME_VERSION,
                        cycle_id=item.cycle_id,
                        instance_id=item.instance_id,
                        session_id=item.session_id,
                        session_status=(
                            item.session_status.value
                            if item.session_status is not None
                            else None
                        ),
                        adapter_health=item.adapter_health.value,
                        browser_health=item.browser_health.value,
                        gateway_health=item.gateway_health.value,
                        overall=item.overall.value,
                        reason_code=item.reason_code,
                        checked_at=item.checked_at,
                    )
                )

    def latest_heartbeats(self) -> tuple[SessionHeartbeat, ...]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            latest = uow.session.scalar(
                select(ChannelSessionHeartbeatRow)
                .order_by(
                    ChannelSessionHeartbeatRow.checked_at.desc(),
                    ChannelSessionHeartbeatRow.heartbeat_id.desc(),
                )
                .limit(1)
            )
            if latest is None:
                return ()
            rows = uow.session.scalars(
                select(ChannelSessionHeartbeatRow)
                .where(ChannelSessionHeartbeatRow.cycle_id == latest.cycle_id)
                .order_by(ChannelSessionHeartbeatRow.instance_id)
            ).all()
            return tuple(self._heartbeat(row) for row in rows)

    @staticmethod
    def _instance_row(item: ChannelInstance) -> ChannelInstanceRow:
        return ChannelInstanceRow(
            instance_id=item.instance_id,
            session_runtime_version=CHANNEL_SESSION_RUNTIME_VERSION,
            platform=item.platform,
            store_id=item.store_id,
            status=item.status.value,
            adapter_type=item.adapter_type,
            active_session_id=item.active_session_id,
            failure_code=item.failure_code,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _session_row(item: ChannelSession) -> ChannelRuntimeSessionRow:
        return ChannelRuntimeSessionRow(
            session_id=item.session_id,
            session_runtime_version=CHANNEL_SESSION_RUNTIME_VERSION,
            instance_id=item.instance_id,
            status=item.status.value,
            credential_ref=item.credential_ref.credential_ref,
            credential_provider=item.credential_ref.provider,
            credential_version=item.credential_ref.version,
            credential_lease_ref=item.credential_lease_ref,
            heartbeat_time=item.heartbeat_time,
            expires_at=item.expires_at,
            failure_code=item.failure_code,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _instance(row: ChannelInstanceRow) -> ChannelInstance:
        return ChannelInstance(
            instance_id=row.instance_id,
            platform=row.platform,
            store_id=row.store_id,
            status=row.status,
            adapter_type=row.adapter_type,
            active_session_id=row.active_session_id,
            failure_code=row.failure_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _session(row: ChannelRuntimeSessionRow) -> ChannelSession:
        return ChannelSession(
            session_id=row.session_id,
            instance_id=row.instance_id,
            status=row.status,
            credential_ref=CredentialReference(
                credential_ref=row.credential_ref,
                provider=row.credential_provider,
                version=row.credential_version,
            ),
            credential_lease_ref=row.credential_lease_ref,
            heartbeat_time=row.heartbeat_time,
            expires_at=row.expires_at,
            failure_code=row.failure_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _cursor(row: ChannelMessageCursorRow) -> MessageCursor:
        return MessageCursor(
            instance_id=row.instance_id,
            cursor_value=row.cursor_value,
            last_sequence=row.last_sequence,
            last_acked_sequence=row.last_acked_sequence,
            revision=row.revision,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _heartbeat(row: ChannelSessionHeartbeatRow) -> SessionHeartbeat:
        return SessionHeartbeat(
            heartbeat_id=row.heartbeat_id,
            cycle_id=row.cycle_id,
            instance_id=row.instance_id,
            session_id=row.session_id,
            session_status=(
                ChannelSessionStatus(row.session_status)
                if row.session_status is not None
                else None
            ),
            adapter_health=AdapterHealthStatus(row.adapter_health),
            browser_health=ComponentHealth(row.browser_health),
            gateway_health=ComponentHealth(row.gateway_health),
            overall=ComponentHealth(row.overall),
            reason_code=row.reason_code,
            checked_at=row.checked_at,
        )

    @staticmethod
    def _assert_version(version: str) -> None:
        if version != CHANNEL_SESSION_RUNTIME_VERSION:
            raise RuntimeError(
                f"unsupported channel session storage version: {version}"
            )


def message_fingerprint(message: ChannelMessageV1) -> str:
    return hashlib.sha256(
        json.dumps(
            message.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "ChannelSessionStore",
    "SessionRecordNotFound",
    "message_fingerprint",
]
