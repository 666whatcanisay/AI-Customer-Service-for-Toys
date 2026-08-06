from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from channel_engine.models.entities import new_id
from channel_engine.storage import SqlAlchemyUnitOfWork
from channel_engine.storage.orm import (
    PDDPilotEvidenceRow,
    PDDPilotExecutionReservationRow,
)

from .models import (
    PDD_PILOT_CONTRACT_VERSION,
    PilotEvidence,
    PilotEvidenceType,
    PilotExecutionReservation,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PilotPersistenceError(RuntimeError):
    error_code = "PILOT_PERSISTENCE_ERROR"


class PilotSendLimitExceeded(PilotPersistenceError):
    error_code = "PILOT_DAILY_SEND_LIMIT_REACHED"


class PilotReservationConflict(PilotPersistenceError):
    error_code = "PILOT_EXECUTION_BINDING_CONFLICT"


class PilotPersistenceRepository:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        if uow.session is None:
            raise RuntimeError("Pilot repository requires an active unit of work")
        self._session = uow.session

    def reserve_execution(
        self,
        *,
        execution_id: str,
        store_id: str,
        conversation_id: str,
        send_limit: int,
        now: datetime,
    ) -> tuple[PilotExecutionReservation, bool]:
        now = _as_utc(now)
        existing = self._session.get(PDDPilotExecutionReservationRow, execution_id)
        if existing is not None:
            reservation = self._reservation_from_row(existing)
            if (
                reservation.store_id != store_id
                or reservation.conversation_id != conversation_id
            ):
                raise PilotReservationConflict(
                    "Pilot Execution is already bound to another store/conversation"
                )
            return reservation, True

        send_day = now.date()
        count = self._session.scalar(
            select(func.count(PDDPilotExecutionReservationRow.execution_id)).where(
                PDDPilotExecutionReservationRow.store_id == store_id,
                PDDPilotExecutionReservationRow.send_day == send_day,
            )
        )
        if int(count or 0) >= send_limit:
            raise PilotSendLimitExceeded("Pilot daily send limit is exhausted")
        row = PDDPilotExecutionReservationRow(
            execution_id=execution_id,
            pilot_contract_version=PDD_PILOT_CONTRACT_VERSION,
            store_id=store_id,
            conversation_id=conversation_id,
            send_day=send_day,
            reserved_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return self._reservation_from_row(row), False

    def get_reservation(
        self, execution_id: str
    ) -> PilotExecutionReservation | None:
        row = self._session.get(PDDPilotExecutionReservationRow, execution_id)
        return self._reservation_from_row(row) if row is not None else None

    def list_reservations(self, store_id: str) -> list[PilotExecutionReservation]:
        rows = self._session.scalars(
            select(PDDPilotExecutionReservationRow)
            .where(PDDPilotExecutionReservationRow.store_id == store_id)
            .order_by(
                PDDPilotExecutionReservationRow.reserved_at,
                PDDPilotExecutionReservationRow.execution_id,
            )
        ).all()
        return [self._reservation_from_row(row) for row in rows]

    def today_count(self, store_id: str, today: date) -> int:
        value = self._session.scalar(
            select(func.count(PDDPilotExecutionReservationRow.execution_id)).where(
                PDDPilotExecutionReservationRow.store_id == store_id,
                PDDPilotExecutionReservationRow.send_day == today,
            )
        )
        return int(value or 0)

    def append_evidence(self, evidence: PilotEvidence) -> PilotEvidence:
        existing = self._session.scalar(
            select(PDDPilotEvidenceRow).where(
                PDDPilotEvidenceRow.idempotency_key == evidence.idempotency_key
            )
        )
        if existing is not None:
            original = self._evidence_from_row(existing)
            if (
                original.evidence_type != evidence.evidence_type
                or original.store_id != evidence.store_id
                or original.correlation_id != evidence.correlation_id
                or original.payload != evidence.payload
            ):
                raise PilotPersistenceError(
                    "Pilot evidence idempotency key was reused with different payload"
                )
            return original
        self._session.add(
            PDDPilotEvidenceRow(
                evidence_id=evidence.evidence_id,
                pilot_contract_version=PDD_PILOT_CONTRACT_VERSION,
                idempotency_key=evidence.idempotency_key,
                evidence_type=evidence.evidence_type.value,
                store_id=evidence.store_id,
                correlation_id=evidence.correlation_id,
                payload=evidence.payload,
                recorded_at=_as_utc(evidence.recorded_at),
            )
        )
        self._session.flush()
        return evidence

    def list_evidence(self, store_id: str, limit: int = 200) -> list[PilotEvidence]:
        if not 1 <= limit <= 1000:
            raise ValueError("Pilot evidence limit must be 1..1000")
        rows = self._session.scalars(
            select(PDDPilotEvidenceRow)
            .where(PDDPilotEvidenceRow.store_id == store_id)
            .order_by(
                PDDPilotEvidenceRow.recorded_at,
                PDDPilotEvidenceRow.evidence_id,
            )
            .limit(limit)
        ).all()
        return [self._evidence_from_row(row) for row in rows]

    def get_evidence(self, idempotency_key: str) -> PilotEvidence | None:
        row = self._session.scalar(
            select(PDDPilotEvidenceRow).where(
                PDDPilotEvidenceRow.idempotency_key == idempotency_key
            )
        )
        return self._evidence_from_row(row) if row is not None else None

    @staticmethod
    def _reservation_from_row(
        row: PDDPilotExecutionReservationRow,
    ) -> PilotExecutionReservation:
        if row.pilot_contract_version != PDD_PILOT_CONTRACT_VERSION:
            raise PilotPersistenceError("Unsupported Pilot reservation version")
        return PilotExecutionReservation(
            execution_id=row.execution_id,
            store_id=row.store_id,
            conversation_id=row.conversation_id,
            send_day=row.send_day.isoformat(),
            reserved_at=_as_utc(row.reserved_at),
        )

    @staticmethod
    def _evidence_from_row(row: PDDPilotEvidenceRow) -> PilotEvidence:
        if row.pilot_contract_version != PDD_PILOT_CONTRACT_VERSION:
            raise PilotPersistenceError("Unsupported Pilot evidence version")
        return PilotEvidence(
            evidence_id=row.evidence_id,
            idempotency_key=row.idempotency_key,
            evidence_type=PilotEvidenceType(row.evidence_type),
            store_id=row.store_id,
            correlation_id=row.correlation_id,
            payload=row.payload,
            recorded_at=_as_utc(row.recorded_at),
        )


class PilotPersistenceService:
    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    ) -> None:
        self.uow_factory = uow_factory

    def evidence(
        self,
        *,
        evidence_type: PilotEvidenceType,
        store_id: str,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, object],
        recorded_at: datetime,
    ) -> PilotEvidence:
        item = PilotEvidence(
            evidence_id=new_id("pilot-evidence"),
            idempotency_key=idempotency_key,
            evidence_type=evidence_type,
            store_id=store_id,
            correlation_id=correlation_id,
            payload=payload,
            recorded_at=_as_utc(recorded_at),
        )
        with self.uow_factory() as uow:
            return PilotPersistenceRepository(uow).append_evidence(item)

    def list_evidence(self, store_id: str, limit: int = 200) -> list[PilotEvidence]:
        with self.uow_factory() as uow:
            return PilotPersistenceRepository(uow).list_evidence(store_id, limit)

    def get_evidence(self, idempotency_key: str) -> PilotEvidence | None:
        with self.uow_factory() as uow:
            return PilotPersistenceRepository(uow).get_evidence(idempotency_key)

    def today_count(self, store_id: str, today: date) -> int:
        with self.uow_factory() as uow:
            return PilotPersistenceRepository(uow).today_count(store_id, today)

    def get_reservation(
        self, execution_id: str
    ) -> PilotExecutionReservation | None:
        with self.uow_factory() as uow:
            return PilotPersistenceRepository(uow).get_reservation(execution_id)

    def list_reservations(self, store_id: str) -> list[PilotExecutionReservation]:
        with self.uow_factory() as uow:
            return PilotPersistenceRepository(uow).list_reservations(store_id)


__all__ = [
    "PilotPersistenceError",
    "PilotPersistenceRepository",
    "PilotPersistenceService",
    "PilotReservationConflict",
    "PilotSendLimitExceeded",
]
