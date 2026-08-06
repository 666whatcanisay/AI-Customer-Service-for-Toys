from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models.entities import new_id, utc_now

from .models import CredentialLease, CredentialReference


class CredentialUnavailable(PermissionError):
    pass


class CredentialReferenceStatus(BaseModel):
    """Secret-free metadata returned by a credential control plane."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    reference: CredentialReference
    available: bool
    expires_at: AwareDatetime | None = None
    rotation_version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )
    reason_code: str | None = Field(default=None, max_length=128)


@runtime_checkable
class CredentialReferenceResolver(Protocol):
    """Resolves reference metadata only, never secret material."""

    def inspect(self, reference: CredentialReference) -> CredentialReferenceStatus: ...


@runtime_checkable
class CredentialProvider(Protocol):
    """Returns only opaque lease references, never credential material."""

    def acquire(self, reference: CredentialReference) -> CredentialLease: ...

    def is_available(self, reference: CredentialReference) -> bool: ...


class ReferenceOnlyCredentialProvider:
    """Issues opaque leases without reading Cookie, Token or Password values."""

    reference_only = True
    exposes_credential_material = False

    def __init__(
        self,
        resolver: CredentialReferenceResolver,
        *,
        lease_ttl: timedelta = timedelta(minutes=5),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not isinstance(resolver, CredentialReferenceResolver):
            raise TypeError("credential resolver does not implement reference metadata")
        if lease_ttl <= timedelta(0):
            raise ValueError("credential lease_ttl must be positive")
        self._resolver = resolver
        self._lease_ttl = lease_ttl
        self._clock = clock

    def inspect(self, reference: CredentialReference) -> CredentialReferenceStatus:
        status = self._resolver.inspect(reference)
        if status.reference != reference:
            raise CredentialUnavailable("credential resolver returned another reference")
        return status

    def is_available(self, reference: CredentialReference) -> bool:
        status = self.inspect(reference)
        now = self._clock()
        return status.available and (
            status.expires_at is None or status.expires_at > now
        )

    def acquire(self, reference: CredentialReference) -> CredentialLease:
        status = self.inspect(reference)
        now = self._clock()
        if not status.available or (
            status.expires_at is not None and status.expires_at <= now
        ):
            raise CredentialUnavailable(
                status.reason_code or "credential reference is unavailable"
            )
        lease_expiry = now + self._lease_ttl
        if status.expires_at is not None:
            lease_expiry = min(lease_expiry, status.expires_at)
        return CredentialLease(
            credential_ref=reference,
            lease_ref=f"credential-lease-ref://{new_id('credential-lease')}",
            acquired_at=now,
            expires_at=lease_expiry,
        )


class FakeCredentialProvider:
    def __init__(
        self,
        references: tuple[CredentialReference, ...] = (),
        *,
        lease_ttl: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if lease_ttl <= timedelta(0):
            raise ValueError("credential lease_ttl must be positive")
        self._references = {
            item.credential_ref: item for item in references
        }
        self._lease_ttl = lease_ttl
        self._clock = clock
        self.acquire_count = 0

    def add_reference(self, reference: CredentialReference) -> None:
        self._references[reference.credential_ref] = reference

    def remove_reference(self, credential_ref: str) -> None:
        self._references.pop(credential_ref, None)

    def is_available(self, reference: CredentialReference) -> bool:
        registered = self._references.get(reference.credential_ref)
        return registered == reference

    def acquire(self, reference: CredentialReference) -> CredentialLease:
        self.acquire_count += 1
        if not self.is_available(reference):
            raise CredentialUnavailable("credential reference is unavailable")
        now = self._clock()
        return CredentialLease(
            credential_ref=reference,
            lease_ref=f"lease-ref://{new_id('credential-lease')}",
            acquired_at=now,
            expires_at=now + self._lease_ttl,
        )


__all__ = [
    "CredentialProvider",
    "CredentialReferenceResolver",
    "CredentialReferenceStatus",
    "CredentialUnavailable",
    "FakeCredentialProvider",
    "ReferenceOnlyCredentialProvider",
]
