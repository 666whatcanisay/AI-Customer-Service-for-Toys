from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EnrollmentGrantRecord:
    grant_id: str
    code_digest: str
    agent_id: str
    device_id: str
    user_reference: str
    store_references: tuple[str, ...]
    authorized_by: str
    reason: str
    issued_at: datetime
    expires_at: datetime


class EnrollmentGrantRepositoryPort(Protocol):
    def replace_for_device(self, record: EnrollmentGrantRecord) -> None: ...

    def consume(self, code_digest: str, consumed_at: datetime) -> EnrollmentGrantRecord | None: ...


class InMemoryEnrollmentGrantRepository:
    def __init__(self) -> None:
        self._records: dict[str, EnrollmentGrantRecord] = {}
        self._lock = RLock()

    def replace_for_device(self, record: EnrollmentGrantRecord) -> None:
        with self._lock:
            self._records = {
                digest: existing
                for digest, existing in self._records.items()
                if not (
                    existing.agent_id == record.agent_id
                    and existing.device_id == record.device_id
                )
            }
            self._records[record.code_digest] = record

    def consume(self, code_digest: str, consumed_at: datetime) -> EnrollmentGrantRecord | None:
        del consumed_at
        with self._lock:
            return self._records.pop(code_digest, None)


__all__ = [
    "EnrollmentGrantRecord",
    "EnrollmentGrantRepositoryPort",
    "InMemoryEnrollmentGrantRepository",
]
