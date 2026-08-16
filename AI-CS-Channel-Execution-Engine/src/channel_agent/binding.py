from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from .identity import AgentIdentity, AgentIdentityStatus
from .version import AGENT_PROTOCOL_VERSION


_REFERENCE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$"
_BINDING_CODE_PATTERN = r"^[A-F0-9]{32}$"


def _canonical_store_references(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if value in seen:
            raise ValueError("store references must be unique")
        seen.add(value)
        result.append(value)
    return tuple(result)


class AgentBindingModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal["1.0"] = AGENT_PROTOCOL_VERSION


class AgentEnrollmentGrantRequest(AgentBindingModel):
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_reference: str = Field(pattern=_REFERENCE_PATTERN)
    store_references: tuple[str, ...] = Field(min_length=1, max_length=32)
    expires_in_seconds: int = Field(default=600, ge=60, le=3600)
    reason: str = Field(min_length=1, max_length=512)

    _canonicalize_stores = field_validator("store_references")(
        _canonical_store_references
    )


class AgentEnrollmentGrantResponse(AgentBindingModel):
    grant_id: str = Field(min_length=1, max_length=192)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_reference: str = Field(pattern=_REFERENCE_PATTERN)
    store_references: tuple[str, ...] = Field(min_length=1, max_length=32)
    binding_code: str = Field(pattern=_BINDING_CODE_PATTERN, repr=False)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    _canonicalize_stores = field_validator("store_references")(
        _canonical_store_references
    )


class AgentEnrollmentRequest(AgentBindingModel):
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    binding_code: str = Field(pattern=_BINDING_CODE_PATTERN, repr=False)

    @field_validator("binding_code")
    @classmethod
    def normalize_binding_code(cls, value: str) -> str:
        return value.strip().upper()


class AgentRuntimeBinding(AgentBindingModel):
    binding_id: str = Field(min_length=1, max_length=192)
    binding_revision: int = Field(ge=0)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    user_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    authorized_store_ids: tuple[str, ...] = Field(default=(), max_length=32)
    active_store_id: str | None = Field(default=None, pattern=_REFERENCE_PATTERN)
    identity_status: AgentIdentityStatus
    production_eligible: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    _canonicalize_stores = field_validator("store_ids")(
        _canonical_store_references
    )

    @classmethod
    def from_identity(cls, identity: AgentIdentity) -> "AgentRuntimeBinding":
        return cls(
            binding_id=f"agent-binding:{identity.agent_id}:{identity.device_id}",
            binding_revision=identity.binding_revision,
            agent_id=identity.agent_id,
            device_id=identity.device_id,
            user_id=identity.user_id,
            store_ids=identity.effective_store_ids,
            authorized_store_ids=identity.authorized_stores,
            active_store_id=identity.effective_active_store_id,
            identity_status=identity.status,
            production_eligible=identity.production_eligible,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
        )


class AgentEnrollmentResponse(AgentBindingModel):
    accepted: Literal[True] = True
    binding: AgentRuntimeBinding
    server_time: AwareDatetime


class AgentStoreBindingUpdateRequest(AgentBindingModel):
    store_references: tuple[str, ...] = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=512)

    _canonicalize_stores = field_validator("store_references")(
        _canonical_store_references
    )


class AgentActiveStoreSelectionRequest(AgentBindingModel):
    device_id: str = Field(min_length=1, max_length=128)
    store_reference: str = Field(pattern=_REFERENCE_PATTERN)
    observed_store_reference: str = Field(pattern=_REFERENCE_PATTERN)
    binding_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)


class AgentVerifiedActiveStoreSelectionRequest(AgentBindingModel):
    """AI-CS-authoritative store selection after platform binding verification.

    The device observes a platform identifier (for example a PDD shop number),
    while Channel Engine stores an internal AI-CS Store reference.  Only the
    signed AI-CS service surface may assert the verified mapping between them.
    """

    device_id: str = Field(min_length=1, max_length=128)
    user_reference: str = Field(pattern=_REFERENCE_PATTERN)
    store_reference: str = Field(pattern=_REFERENCE_PATTERN)
    platform: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    observed_platform_store_id: str = Field(min_length=1, max_length=96)
    platform_binding_id: str = Field(min_length=1, max_length=128)
    platform_binding_verified_at: AwareDatetime
    binding_revision: int = Field(ge=0)
    human_confirmed: Literal[True]
    reason: str = Field(min_length=1, max_length=512)


class PDDStoreBindingV1(AgentBindingModel):
    """Public-identifier-only projection of the server-verified PDD binding."""

    schema_version: Literal["pdd-store-binding.v1"] = "pdd-store-binding.v1"
    ai_cs_store_reference: str = Field(pattern=_REFERENCE_PATTERN)
    observed_pdd_store_id: str = Field(min_length=1, max_length=96)
    platform_binding_id: str = Field(min_length=1, max_length=128)
    verified_at: AwareDatetime
    human_confirmed: Literal[True]

    @classmethod
    def from_verified_selection(
        cls, request: AgentVerifiedActiveStoreSelectionRequest
    ) -> "PDDStoreBindingV1":
        if request.platform != "pdd":
            raise ValueError("PDD store binding requires the pdd platform")
        return cls(
            ai_cs_store_reference=request.store_reference,
            observed_pdd_store_id=request.observed_platform_store_id,
            platform_binding_id=request.platform_binding_id,
            verified_at=request.platform_binding_verified_at,
            human_confirmed=request.human_confirmed,
        )

    def assert_current_page(
        self,
        *,
        observed_pdd_store_id: str,
        ai_cs_store_reference: str,
    ) -> None:
        if observed_pdd_store_id != self.observed_pdd_store_id:
            raise ValueError("current PDD page store does not match the verified binding")
        if ai_cs_store_reference != self.ai_cs_store_reference:
            raise ValueError("AI-CS store does not match the verified PDD binding")


class AgentBindingStore:
    """Atomic local storage for public binding references only."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> AgentRuntimeBinding | None:
        candidates = [self.path, *self._pending_paths()]
        existing = [path for path in candidates if path.exists()]
        if not existing:
            return None
        valid: list[tuple[AgentRuntimeBinding, Path]] = []
        first_error: Exception | None = None
        for candidate in existing:
            try:
                raw = candidate.read_bytes()
                if len(raw) > 1024 * 1024:
                    raise ValueError("Agent binding state exceeds one MiB")
                valid.append((AgentRuntimeBinding.model_validate_json(raw), candidate))
            except (OSError, ValueError) as exc:
                first_error = first_error or exc
        if not valid:
            if first_error is not None:
                raise ValueError("Agent binding state is invalid") from first_error
            return None
        binding, _source = max(
            valid,
            key=lambda item: (
                item[0].binding_revision,
                item[0].updated_at,
                item[1] == self.path,
            ),
        )
        return binding

    def save(self, binding: AgentRuntimeBinding) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = binding.model_dump_json(indent=2).encode("utf-8") + b"\n"
        temporary = _write_unique_temporary(self.path, payload)
        try:
            _replace_with_retry(temporary, self.path)
            self._clear_pending()
        except PermissionError:
            # Windows may briefly deny replacement while the runtime status
            # thread or endpoint scanner has the previous file open.  The
            # enrollment has already succeeded remotely at this point, so a
            # durable recovery candidate is safer than reporting UNBOUND and
            # encouraging the operator to consume another one-time grant.
            pending = self.path.parent / (
                f".{self.path.name}.{binding.binding_revision}."
                f"{os.getpid()}.{time.time_ns()}.pending"
            )
            try:
                temporary.rename(pending)
                self._clear_pending(except_path=pending)
            except OSError:
                temporary.unlink(missing_ok=True)
                raise
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def save_identity(self, identity: AgentIdentity) -> AgentRuntimeBinding:
        binding = AgentRuntimeBinding.from_identity(identity)
        self.save(binding)
        return binding

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self._clear_pending()

    def _pending_paths(self) -> tuple[Path, ...]:
        return tuple(sorted(self.path.parent.glob(f".{self.path.name}.*.pending")))

    def _clear_pending(self, except_path: Path | None = None) -> None:
        for pending in self._pending_paths():
            if except_path is None or pending != except_path:
                pending.unlink(missing_ok=True)


def atomic_write_bytes(path: str | Path, payload: bytes) -> None:
    """Write one local runtime file with bounded Windows sharing retries."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _write_unique_temporary(target, payload)
    try:
        _replace_with_retry(temporary, target)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _write_unique_temporary(target: Path, payload: bytes) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _replace_with_retry(source: Path, target: Path, attempts: int = 8) -> None:
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            _atomic_replace(source, target)
            return
        except PermissionError as exc:
            last_error = exc
            if target.exists():
                try:
                    target.chmod(0o600)
                except OSError:
                    pass
        except OSError as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(min(0.02 * (2**attempt), 0.25))
    if isinstance(last_error, PermissionError):
        raise PermissionError(
            f"Local runtime file is temporarily locked: {target.name}"
        ) from last_error
    raise OSError(f"Local runtime file cannot be replaced: {target.name}") from last_error


def _atomic_replace(source: Path, target: Path) -> None:
    """Narrow patch point for atomic replacement tests.

    Keeping this wrapper private prevents a test from replacing ``os.replace``
    process-wide while another runtime thread is still shutting down.
    """

    os.replace(source, target)


__all__ = [
    "AgentBindingStore",
    "AgentActiveStoreSelectionRequest",
    "AgentVerifiedActiveStoreSelectionRequest",
    "AgentEnrollmentGrantRequest",
    "AgentEnrollmentGrantResponse",
    "AgentEnrollmentRequest",
    "AgentEnrollmentResponse",
    "AgentRuntimeBinding",
    "AgentStoreBindingUpdateRequest",
    "PDDStoreBindingV1",
    "atomic_write_bytes",
]
