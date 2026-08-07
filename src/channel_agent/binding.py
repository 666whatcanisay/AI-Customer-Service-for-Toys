from __future__ import annotations

import os
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


class AgentBindingStore:
    """Atomic local storage for public binding references only."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> AgentRuntimeBinding | None:
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("Agent binding state exceeds one MiB")
        return AgentRuntimeBinding.model_validate_json(raw)

    def save(self, binding: AgentRuntimeBinding) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = binding.model_dump_json(indent=2).encode("utf-8") + b"\n"
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    def save_identity(self, identity: AgentIdentity) -> AgentRuntimeBinding:
        binding = AgentRuntimeBinding.from_identity(identity)
        self.save(binding)
        return binding

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


__all__ = [
    "AgentBindingStore",
    "AgentEnrollmentGrantRequest",
    "AgentEnrollmentGrantResponse",
    "AgentEnrollmentRequest",
    "AgentEnrollmentResponse",
    "AgentRuntimeBinding",
    "AgentStoreBindingUpdateRequest",
]
