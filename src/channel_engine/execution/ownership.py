from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from channel_engine.models.entities import new_id, utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork, WorkerOwnership


class DuplicateWorkerOwnership(RuntimeError):
    """Raised when another live process owns the same logical worker id."""


class WorkerOwnershipRegistry:
    """Database-backed process ownership with heartbeat and expiry takeover."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        worker_id: str,
        *,
        lease_duration: timedelta = timedelta(seconds=90),
        clock: Callable[[], datetime] = utc_now,
        owner_token: str | None = None,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_duration <= timedelta(0):
            raise ValueError("worker ownership lease must be positive")
        self._uow_factory = uow_factory
        self.worker_id = worker_id.strip()
        self.lease_duration = lease_duration
        self._clock = clock
        self.owner_token = owner_token or new_id("worker-owner")
        self._owned = False

    def ensure_owned(self) -> WorkerOwnership:
        now = self._clock()
        with self._uow_factory() as uow:
            repo = uow.require_repository()
            if self._owned:
                ownership = repo.renew_worker_ownership(
                    self.worker_id,
                    self.owner_token,
                    now,
                    now + self.lease_duration,
                )
                if ownership is None:
                    self._owned = False
                    raise DuplicateWorkerOwnership(
                        f"worker ownership was lost: {self.worker_id}"
                    )
                return ownership

            ownership = repo.acquire_worker_ownership(
                self.worker_id,
                self.owner_token,
                now,
                now + self.lease_duration,
            )
            if ownership is None:
                raise DuplicateWorkerOwnership(
                    f"worker id is owned by another live process: {self.worker_id}"
                )
            self._owned = True
            return ownership

    def release(self) -> bool:
        if not self._owned:
            return False
        with self._uow_factory() as uow:
            released = uow.require_repository().release_worker_ownership(
                self.worker_id, self.owner_token
            )
        self._owned = False
        return released


__all__ = ["DuplicateWorkerOwnership", "WorkerOwnershipRegistry"]
