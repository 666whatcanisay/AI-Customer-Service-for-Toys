from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from channel_agent.identity import AgentIdentity, AgentIdentityStatus
from channel_engine.storage.orm import ChannelAgentIdentityRow


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
                "status": identity.status.value,
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
            status=AgentIdentityStatus(row.status),
            binding_revision=row.binding_revision,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = ["SqlAlchemyAgentIdentityRepository"]
