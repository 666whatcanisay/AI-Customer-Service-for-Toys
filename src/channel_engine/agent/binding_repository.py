from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from channel_agent.identity import (
    AgentConnectivityStatus,
    AgentIdentity,
    AgentIdentityStatus,
)
from channel_engine.storage.orm import (
    ChannelAgentEnrollmentGrantRow,
    ChannelAgentIdentityRow,
    ExecutionRow,
    PDDExecutionStoreBindingRow,
)

from .grants import EnrollmentGrantRecord


class SqlAlchemyAgentIdentityRepository:
    """Durable, credential-free Agent identity binding repository."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_identities(self) -> tuple[AgentIdentity, ...]:
        with self._session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(ChannelAgentIdentityRow).order_by(
                        ChannelAgentIdentityRow.agent_id
                    )
                )
            )
            return tuple(self._model(row) for row in rows)

    def save_identity(self, identity: AgentIdentity) -> None:
        with self._session_factory() as session:
            row = session.get(ChannelAgentIdentityRow, identity.agent_id)
            values = {
                "device_id": identity.device_id,
                "user_id": identity.user_id,
                "store_id": identity.store_id,
                "store_ids": list(identity.effective_store_ids),
                "active_store_id": identity.effective_active_store_id,
                "legacy_status": identity.status.value,
                "identity_status": identity.status.value,
                "binding_revision": identity.binding_revision,
                "created_at": identity.created_at,
                "updated_at": identity.updated_at,
            }
            if row is None:
                session.add(
                    ChannelAgentIdentityRow(
                        agent_id=identity.agent_id,
                        **values,
                    )
                )
            else:
                for field, value in values.items():
                    setattr(row, field, value)
            session.commit()

    @staticmethod
    def _model(row: ChannelAgentIdentityRow) -> AgentIdentity:
        return AgentIdentity(
            agent_id=row.agent_id,
            device_id=row.device_id,
            user_id=row.user_id,
            store_id=row.store_id,
            store_ids=tuple(row.store_ids or ()),
            authorized_store_ids=tuple(row.store_ids or ()),
            active_store_id=row.active_store_id,
            status=AgentIdentityStatus(row.identity_status or row.legacy_status),
            binding_revision=row.binding_revision,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    def list_runtime_agents(self):  # type: ignore[no-untyped-def]
        from .node_api import RegisteredChannelAgent

        with self._session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(ChannelAgentIdentityRow)
                    .where(ChannelAgentIdentityRow.last_heartbeat.is_not(None))
                    .order_by(ChannelAgentIdentityRow.agent_id)
                )
            )
        return tuple(
            RegisteredChannelAgent(
                registration_id=(
                    "agent-registration:"
                    f"{uuid5(NAMESPACE_URL, f'{row.agent_id}:{row.device_id}')}"
                ),
                agent_id=row.agent_id,
                device_id=row.device_id,
                version=row.agent_version or "unknown",
                hostname=row.hostname or "unknown",
                status=row.runtime_status or "STOPPED",
                registered_at=_aware(row.registered_at or row.created_at),
                last_heartbeat=_aware(row.last_heartbeat or row.updated_at),
                connectivity_status=AgentConnectivityStatus(
                    row.connectivity_status or "OFFLINE"
                ),
            )
            for row in rows
        )

    def save_runtime_agent(self, agent) -> None:  # type: ignore[no-untyped-def]
        with self._session_factory() as session:
            row = session.get(ChannelAgentIdentityRow, agent.agent_id)
            if row is None:
                raise KeyError(agent.agent_id)
            row.agent_version = agent.version
            row.hostname = agent.hostname
            row.runtime_status = agent.status
            row.registered_at = agent.registered_at
            row.last_heartbeat = agent.last_heartbeat
            row.connectivity_status = agent.connectivity_status.value
            session.commit()


class SqlAlchemyActiveStoreGuard:
    """Block store switches while the current store has unsafe executions."""

    _BLOCKING_STATES = ("PENDING", "RUNNING", "UNKNOWN")

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(
        self,
        _agent_id: str,
        current_store_id: str | None,
        target_store_id: str,
    ) -> tuple[str, ...]:
        if current_store_id is None or current_store_id == target_store_id:
            return ()
        with self._session_factory() as session:
            states = tuple(
                session.scalars(
                    select(ExecutionRow.state)
                    .join(
                        PDDExecutionStoreBindingRow,
                        PDDExecutionStoreBindingRow.execution_id
                        == ExecutionRow.execution_id,
                    )
                    .where(
                        PDDExecutionStoreBindingRow.store_id == current_store_id,
                        ExecutionRow.state.in_(self._BLOCKING_STATES),
                    )
                    .distinct()
                    .order_by(ExecutionRow.state)
                )
            )
        return tuple(f"{state}_EXECUTION" for state in states)


class SqlAlchemyEnrollmentGrantRepository:
    """Persistent one-time grant hashes; plaintext enrollment codes never enter storage."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def replace_for_device(self, record: EnrollmentGrantRecord) -> None:
        with self._session_factory() as session, session.begin():
            session.execute(
                delete(ChannelAgentEnrollmentGrantRow).where(
                    ChannelAgentEnrollmentGrantRow.agent_id == record.agent_id,
                    ChannelAgentEnrollmentGrantRow.device_id == record.device_id,
                    ChannelAgentEnrollmentGrantRow.consumed_at.is_(None),
                )
            )
            session.add(
                ChannelAgentEnrollmentGrantRow(
                    code_digest=record.code_digest,
                    grant_id=record.grant_id,
                    agent_id=record.agent_id,
                    device_id=record.device_id,
                    user_reference=record.user_reference,
                    store_references=list(record.store_references),
                    authorized_by=record.authorized_by,
                    reason=record.reason,
                    issued_at=record.issued_at,
                    expires_at=record.expires_at,
                    consumed_at=None,
                )
            )

    def consume(self, code_digest: str, consumed_at: datetime) -> EnrollmentGrantRecord | None:
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(ChannelAgentEnrollmentGrantRow).where(
                    ChannelAgentEnrollmentGrantRow.code_digest == code_digest,
                    ChannelAgentEnrollmentGrantRow.consumed_at.is_(None),
                )
            )
            if row is None:
                return None
            changed = session.execute(
                update(ChannelAgentEnrollmentGrantRow)
                .where(
                    ChannelAgentEnrollmentGrantRow.code_digest == code_digest,
                    ChannelAgentEnrollmentGrantRow.consumed_at.is_(None),
                )
                .values(consumed_at=consumed_at)
            )
            if changed.rowcount != 1:
                return None
            return EnrollmentGrantRecord(
                grant_id=row.grant_id,
                code_digest=row.code_digest,
                agent_id=row.agent_id,
                device_id=row.device_id,
                user_reference=row.user_reference,
                store_references=tuple(row.store_references),
                authorized_by=row.authorized_by,
                reason=row.reason,
                issued_at=_aware(row.issued_at),
                expires_at=_aware(row.expires_at),
            )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "SqlAlchemyActiveStoreGuard",
    "SqlAlchemyAgentIdentityRepository",
    "SqlAlchemyEnrollmentGrantRepository",
]
