from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy import Engine, select


RUNTIME_STORAGE_VERSION = "1.0"
RUNTIME_STORAGE_SINGLETON_ID = "channel-engine-runtime"


class RuntimeStorageVersionError(RuntimeError):
    pass


class RuntimeStorageStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    runtime_storage_version: Literal["1.0"] = RUNTIME_STORAGE_VERSION
    initialized_at: AwareDatetime
    verified_at: AwareDatetime
    backend: str


def ensure_runtime_storage_version(engine: Engine, now: datetime) -> RuntimeStorageStatus:
    """Initialize and verify the durable store's compatibility manifest."""

    from .orm import RuntimeStorageMetadataRow

    table = RuntimeStorageMetadataRow.__table__
    with engine.begin() as connection:
        row = connection.execute(
            select(table).where(
                table.c.singleton_id == RUNTIME_STORAGE_SINGLETON_ID
            )
        ).mappings().one_or_none()
        if row is None:
            connection.execute(
                table.insert().values(
                    singleton_id=RUNTIME_STORAGE_SINGLETON_ID,
                    runtime_storage_version=RUNTIME_STORAGE_VERSION,
                    initialized_at=now,
                    verified_at=now,
                )
            )
            initialized_at = now
        else:
            persisted_version = row["runtime_storage_version"]
            if persisted_version != RUNTIME_STORAGE_VERSION:
                raise RuntimeStorageVersionError(
                    "unsupported runtime storage version: "
                    f"{persisted_version}; expected {RUNTIME_STORAGE_VERSION}"
                )
            initialized_at = row["initialized_at"]
            connection.execute(
                table.update()
                .where(table.c.singleton_id == RUNTIME_STORAGE_SINGLETON_ID)
                .values(verified_at=now)
            )

    if initialized_at.tzinfo is None:
        initialized_at = initialized_at.replace(tzinfo=now.tzinfo)
    return RuntimeStorageStatus(
        initialized_at=initialized_at,
        verified_at=now,
        backend=engine.dialect.name,
    )


__all__ = [
    "RUNTIME_STORAGE_SINGLETON_ID",
    "RUNTIME_STORAGE_VERSION",
    "RuntimeStorageStatus",
    "RuntimeStorageVersionError",
    "ensure_runtime_storage_version",
]
