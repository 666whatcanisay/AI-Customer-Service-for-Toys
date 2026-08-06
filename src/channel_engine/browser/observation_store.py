from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from channel_engine.storage.orm import (
    BrowserObservationCheckpointRow,
    BrowserObservationIdentityRow,
)

from .observer import (
    BROWSER_OBSERVATION_CONTRACT_VERSION,
    BrowserObservationCheckpoint,
    BrowserObservationConflict,
    BrowserObservationSyncState,
    BrowserObservedIdentity,
)


class SqlAlchemyBrowserObservationStore:
    """Durable CAS cursor and dedup store containing no message plaintext."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _initial(stream_id: str) -> BrowserObservationCheckpoint:
        return BrowserObservationCheckpoint(stream_id=stream_id, revision=0)

    def load(self, stream_id: str) -> BrowserObservationCheckpoint:
        with self._session_factory() as session:
            row = session.get(BrowserObservationCheckpointRow, stream_id)
            if row is None:
                return self._initial(stream_id)
            self._assert_version(row.browser_observation_version)
            return self._checkpoint_from_row(row)

    def lookup_identities(
        self,
        stream_id: str,
        identity_digests: tuple[str, ...],
    ) -> Mapping[str, BrowserObservedIdentity]:
        if not identity_digests:
            return {}
        with self._session_factory() as session:
            rows = session.scalars(
                select(BrowserObservationIdentityRow).where(
                    BrowserObservationIdentityRow.stream_id == stream_id,
                    BrowserObservationIdentityRow.identity_digest.in_(
                        identity_digests
                    ),
                )
            ).all()
            result: dict[str, BrowserObservedIdentity] = {}
            for row in rows:
                self._assert_version(row.browser_observation_version)
                result[row.identity_digest] = BrowserObservedIdentity(
                    identity_digest=row.identity_digest,
                    payload_fingerprint=row.payload_fingerprint,
                    source_sequence=row.source_sequence,
                )
            return result

    def commit_capture(
        self,
        checkpoint: BrowserObservationCheckpoint,
        *,
        cursor: str | None,
        last_sequence: int,
        selector_contract_id: str,
        selector_fingerprint: str,
        page_generation: int,
        identities: Sequence[BrowserObservedIdentity],
        accepted_increment: int,
        duplicate_increment: int,
        captured_at: datetime,
    ) -> BrowserObservationCheckpoint:
        if last_sequence < checkpoint.last_sequence:
            raise BrowserObservationConflict("observation sequence moved backward")
        if accepted_increment < 0 or duplicate_increment < 0:
            raise ValueError("observation counters cannot decrement")
        updated = checkpoint.model_copy(
            update={
                "revision": checkpoint.revision + 1,
                "cursor": cursor,
                "last_sequence": last_sequence,
                "selector_contract_id": selector_contract_id,
                "selector_fingerprint": selector_fingerprint,
                "page_generation": page_generation,
                "accepted_count": checkpoint.accepted_count
                + accepted_increment,
                "duplicate_count": checkpoint.duplicate_count
                + duplicate_increment,
                "last_capture_at": captured_at,
                "sync_state": BrowserObservationSyncState.IN_SYNC,
                "last_error_code": None,
            }
        )
        try:
            with self._session_factory.begin() as session:
                self._cas_checkpoint(session, checkpoint, updated)
                for identity in identities:
                    key = (checkpoint.stream_id, identity.identity_digest)
                    row = session.get(BrowserObservationIdentityRow, key)
                    if row is not None:
                        self._assert_version(row.browser_observation_version)
                        if (
                            row.payload_fingerprint
                            != identity.payload_fingerprint
                            or row.source_sequence != identity.source_sequence
                        ):
                            raise BrowserObservationConflict(
                                "message identity is already bound to different evidence"
                            )
                        continue
                    session.add(
                        BrowserObservationIdentityRow(
                            stream_id=checkpoint.stream_id,
                            identity_digest=identity.identity_digest,
                            browser_observation_version=(
                                BROWSER_OBSERVATION_CONTRACT_VERSION
                            ),
                            payload_fingerprint=identity.payload_fingerprint,
                            source_sequence=identity.source_sequence,
                        )
                    )
        except IntegrityError as exc:
            raise BrowserObservationConflict(
                "browser observation commit conflicted with another writer"
            ) from exc
        return updated

    def record_failure(
        self,
        checkpoint: BrowserObservationCheckpoint,
        *,
        error_code: str,
        failed_at: datetime,
        terminal: bool,
    ) -> BrowserObservationCheckpoint:
        updated = checkpoint.model_copy(
            update={
                "revision": checkpoint.revision + 1,
                "last_capture_at": failed_at,
                "sync_state": (
                    BrowserObservationSyncState.FAILED
                    if terminal
                    else BrowserObservationSyncState.DEGRADED
                ),
                "last_error_code": error_code,
            }
        )
        try:
            with self._session_factory.begin() as session:
                self._cas_checkpoint(session, checkpoint, updated)
        except IntegrityError as exc:
            raise BrowserObservationConflict(
                "browser observation failure record conflicted"
            ) from exc
        return updated

    def _cas_checkpoint(
        self,
        session: Session,
        current: BrowserObservationCheckpoint,
        updated: BrowserObservationCheckpoint,
    ) -> None:
        existing = session.get(BrowserObservationCheckpointRow, current.stream_id)
        if existing is None:
            if current.revision != 0:
                raise BrowserObservationConflict(
                    "browser observation checkpoint disappeared"
                )
            session.add(self._row_from_checkpoint(updated))
            session.flush()
            return
        self._assert_version(existing.browser_observation_version)
        values = self._row_values(updated)
        result = session.execute(
            update(BrowserObservationCheckpointRow)
            .where(
                BrowserObservationCheckpointRow.stream_id == current.stream_id,
                BrowserObservationCheckpointRow.revision == current.revision,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise BrowserObservationConflict(
                "browser observation checkpoint revision changed concurrently"
            )

    @staticmethod
    def _row_values(checkpoint: BrowserObservationCheckpoint) -> dict[str, object]:
        return {
            "browser_observation_version": BROWSER_OBSERVATION_CONTRACT_VERSION,
            "revision": checkpoint.revision,
            "cursor": checkpoint.cursor,
            "last_sequence": checkpoint.last_sequence,
            "selector_contract_id": checkpoint.selector_contract_id,
            "selector_fingerprint": checkpoint.selector_fingerprint,
            "page_generation": checkpoint.page_generation,
            "accepted_count": checkpoint.accepted_count,
            "duplicate_count": checkpoint.duplicate_count,
            "last_capture_at": checkpoint.last_capture_at,
            "sync_state": checkpoint.sync_state.value,
            "last_error_code": checkpoint.last_error_code,
        }

    @classmethod
    def _row_from_checkpoint(
        cls,
        checkpoint: BrowserObservationCheckpoint,
    ) -> BrowserObservationCheckpointRow:
        return BrowserObservationCheckpointRow(
            stream_id=checkpoint.stream_id,
            **cls._row_values(checkpoint),
        )

    @staticmethod
    def _checkpoint_from_row(
        row: BrowserObservationCheckpointRow,
    ) -> BrowserObservationCheckpoint:
        captured_at = row.last_capture_at
        if captured_at is not None and captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        return BrowserObservationCheckpoint(
            stream_id=row.stream_id,
            revision=row.revision,
            cursor=row.cursor,
            last_sequence=row.last_sequence,
            selector_contract_id=row.selector_contract_id,
            selector_fingerprint=row.selector_fingerprint,
            page_generation=row.page_generation,
            accepted_count=row.accepted_count,
            duplicate_count=row.duplicate_count,
            last_capture_at=captured_at,
            sync_state=BrowserObservationSyncState(row.sync_state),
            last_error_code=row.last_error_code,
        )

    @staticmethod
    def _assert_version(version: str) -> None:
        if version != BROWSER_OBSERVATION_CONTRACT_VERSION:
            raise BrowserObservationConflict(
                f"unsupported browser observation version: {version}"
            )


__all__ = ["SqlAlchemyBrowserObservationStore"]
