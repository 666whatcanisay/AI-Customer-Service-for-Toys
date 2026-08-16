from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PilotGovernanceError(RuntimeError):
    """A Pilot fact, runtime binding, or activation check failed closed."""


class GateStatus(StrEnum):
    PASS = "PASS"
    NOT_VERIFIED = "NOT_VERIFIED"
    BLOCKED = "BLOCKED"
    NOT_IN_SCOPE = "NOT_IN_SCOPE"


GATE_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("REAL_PDD_ADAPTER_READY", "REAL_PDD_READ_READY"),
    ("REAL_PDD_READ_READY", "REAL_PDD_AI_READY"),
    ("REAL_PDD_AI_READY", "REAL_PDD_CONFIRM_READY"),
    ("REAL_PDD_CONFIRM_READY", "REAL_PDD_SEND_READY"),
)


class GateFactsV1(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    schema_name: Literal["rc5-gate-facts.v1"] = Field(
        default="rc5-gate-facts.v1", alias="schema"
    )
    gates: dict[str, GateStatus]
    # Compatibility-only fields. Historical facts and Replay fixtures may still
    # contain them, but governance must derive every decision from live facts.
    ai_cs_production_ready: bool | None = Field(
        default=None, deprecated=True, exclude=True
    )
    may_enter_read_only_pilot: bool | None = Field(
        default=None, deprecated=True, exclude=True
    )
    real_send_enabled: bool | None = Field(
        default=None, deprecated=True, exclude=True
    )

    @model_validator(mode="after")
    def validate_dependencies(self) -> "GateFactsV1":
        required = {
            "RC5_OFFLINE_STABILITY_READY",
            "REAL_PDD_ADAPTER_READY",
            "REAL_PDD_READ_READY",
            "REAL_PDD_AI_READY",
            "REAL_PDD_CONFIRM_READY",
            "REAL_PDD_SEND_READY",
            "REAL_PDD_AUTO_SEND_READY",
        }
        if set(self.gates) != required:
            raise ValueError("RC5 Gate facts are incomplete or contain unknown Gates")
        if self.gates["RC5_OFFLINE_STABILITY_READY"] is not GateStatus.PASS:
            raise ValueError("read-only Pilot requires the offline stability Gate")
        if self.gates["REAL_PDD_AUTO_SEND_READY"] is not GateStatus.NOT_IN_SCOPE:
            raise ValueError("real PDD automatic sending remains out of scope")
        for prerequisite, dependent in GATE_DEPENDENCIES:
            if (
                self.gates[dependent] is GateStatus.PASS
                and self.gates[prerequisite] is not GateStatus.PASS
            ):
                raise ValueError(
                    f"{dependent} cannot PASS before {prerequisite}"
                )
        return self

    def derived_ai_cs_production_ready(self) -> bool:
        return all(
            self.gates[name] is GateStatus.PASS
            for name in (
                "RC5_OFFLINE_STABILITY_READY",
                "REAL_PDD_ADAPTER_READY",
                "REAL_PDD_READ_READY",
                "REAL_PDD_AI_READY",
                "REAL_PDD_CONFIRM_READY",
                "REAL_PDD_SEND_READY",
            )
        )


class RuntimeLifecycle(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVE = "ARCHIVE"
    DO_NOT_USE = "DO_NOT_USE"
    UNCLASSIFIED = "UNCLASSIFIED"


class RuntimeCatalogEntryV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str = Field(min_length=1, max_length=256)
    component: str = Field(min_length=1, max_length=160)
    environment_id: str = Field(min_length=1, max_length=160)
    database_role: str = Field(min_length=1, max_length=160)
    lifecycle: RuntimeLifecycle
    canonical_path: str = Field(min_length=1, max_length=2048)
    database_instance_id: str | None = Field(default=None, max_length=160)
    revision: str | None = Field(default=None, max_length=160)
    binding_valid: bool
    retention_class: Literal["ACTIVE", "FORMAL_90D", "TRANSIENT_14D", "MANUAL"]
    classification_reason: str = Field(min_length=1, max_length=512)


class RuntimeCatalogV1(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    schema_name: Literal["rc5-runtime-catalog.v1"] = Field(
        default="rc5-runtime-catalog.v1", alias="schema"
    )
    generated_at: AwareDatetime
    expected_active_roles: tuple[str, ...]
    entries: tuple[RuntimeCatalogEntryV1, ...]

    @model_validator(mode="after")
    def validate_active_uniqueness(self) -> "RuntimeCatalogV1":
        active = [
            item for item in self.entries if item.lifecycle is RuntimeLifecycle.ACTIVE
        ]
        for item in active:
            if (
                not item.binding_valid
                or not item.database_instance_id
                or not item.revision
            ):
                raise ValueError(
                    f"ACTIVE database identity is invalid: {item.canonical_path}"
                )
        keys = [f"{item.environment_id}|{item.database_role}" for item in active]
        for expected in self.expected_active_roles:
            if keys.count(expected) != 1:
                raise ValueError(
                    f"runtime role requires exactly one ACTIVE database: {expected}"
                )
        unexpected = sorted(set(keys) - set(self.expected_active_roles))
        if unexpected:
            raise ValueError(f"unexpected ACTIVE runtime roles: {unexpected}")
        return self


class RagRuntimeIdentityV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(min_length=1, max_length=256)
    vector_database_path: str = Field(min_length=1, max_length=2048)
    active_collection_name: str = Field(min_length=1, max_length=256)
    ready: bool
    model_configured: bool


class RagLiveSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    model_configured: bool


class RuntimeActivationV1(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    schema_name: Literal["rc5-runtime-activation.v1"] = Field(
        default="rc5-runtime-activation.v1", alias="schema"
    )
    activation_id: str = Field(min_length=1, max_length=256)
    component: str = Field(min_length=1, max_length=160)
    pid: int = Field(gt=0)
    executable_path: str = Field(min_length=1, max_length=2048)
    manifest_created_at: AwareDatetime
    service_started_at: AwareDatetime
    process_started_at: AwareDatetime
    config_source_path: str = Field(min_length=1, max_length=2048)
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    activation_kind: Literal["DATABASE", "RAG"] = "DATABASE"
    canonical_database_path: str | None = Field(default=None, max_length=2048)
    binding_sidecar_path: str | None = Field(default=None, max_length=2048)
    database_instance_id: str | None = Field(default=None, max_length=160)
    environment_id: str | None = Field(default=None, max_length=160)
    database_role: str | None = Field(default=None, max_length=160)
    revision: str | None = Field(default=None, max_length=160)
    binding_sidecar_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    source_repository_path: str | None = Field(default=None, max_length=2048)
    source_revision: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{40,64}$"
    )
    source_fingerprint: str | None = Field(default=None, max_length=256)
    rag_identity: RagRuntimeIdentityV1 | None = None
    ports: tuple[int, ...] = Field(min_length=1)
    runtime_data_paths: dict[str, str] = Field(default_factory=dict)
    safety_flags: dict[str, bool] = Field(default_factory=dict)
    diagnostics: dict[str, str | int | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_activation_kind(self) -> "RuntimeActivationV1":
        if self.activation_kind == "DATABASE":
            required = (
                self.canonical_database_path,
                self.binding_sidecar_path,
                self.database_instance_id,
                self.environment_id,
                self.database_role,
                self.revision,
                self.binding_sidecar_sha256,
            )
            if any(not value for value in required):
                raise ValueError("database activation identity is incomplete")
        elif not all(
            (
                self.source_repository_path,
                self.source_revision,
                self.source_fingerprint,
                self.rag_identity,
            )
        ):
            raise ValueError("RAG activation identity is incomplete")
        return self


class LiveProcessSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pid: int = Field(gt=0)
    executable_path: str
    process_started_at: AwareDatetime
    listening_ports: tuple[int, ...] = ()


class ActivationValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    status: Literal["PASS", "BLOCKED"]
    reason_codes: tuple[str, ...]


def validate_activation(
    activation: RuntimeActivationV1,
    catalog: RuntimeCatalogV1,
    live_process: LiveProcessSnapshot | None,
    *,
    current_config_sha256: str,
    current_binding_sha256: str | None = None,
    current_database_instance_id: str | None = None,
    current_source_revision: str | None = None,
    current_source_fingerprint: str | None = None,
    live_rag: RagLiveSnapshot | None = None,
) -> ActivationValidationResult:
    reasons: list[str] = []
    if live_process is None or live_process.pid != activation.pid:
        reasons.append("ACTIVATION_PID_NOT_RUNNING")
    else:
        if not _same_path(live_process.executable_path, activation.executable_path):
            reasons.append("ACTIVATION_EXECUTABLE_MISMATCH")
        delta = abs(
            (
                live_process.process_started_at.astimezone(UTC)
                - activation.process_started_at.astimezone(UTC)
            ).total_seconds()
        )
        if delta > 2:
            reasons.append("ACTIVATION_PROCESS_START_MISMATCH")
        if not set(activation.ports).issubset(live_process.listening_ports):
            reasons.append("ACTIVATION_PORT_OWNER_MISMATCH")
    if current_config_sha256 != activation.config_sha256:
        reasons.append("ACTIVATION_CONFIG_DIGEST_MISMATCH")
    if (
        activation.manifest_created_at.astimezone(UTC)
        < activation.process_started_at.astimezone(UTC)
    ):
        reasons.append("ACTIVATION_MANIFEST_PRECEDES_PROCESS")
    if activation.activation_kind == "DATABASE":
        if current_binding_sha256 != activation.binding_sidecar_sha256:
            reasons.append("ACTIVATION_BINDING_DIGEST_MISMATCH")
        if current_database_instance_id != activation.database_instance_id:
            reasons.append("ACTIVATION_DATABASE_INSTANCE_MISMATCH")
        matching = [
            item
            for item in catalog.entries
            if item.lifecycle is RuntimeLifecycle.ACTIVE
            and item.environment_id == activation.environment_id
            and item.database_role == activation.database_role
        ]
        if len(matching) != 1:
            reasons.append("ACTIVE_DATABASE_NOT_UNIQUE")
        elif (
            not _same_path(
                matching[0].canonical_path,
                str(activation.canonical_database_path),
            )
            or matching[0].database_instance_id != activation.database_instance_id
            or matching[0].revision != activation.revision
            or not matching[0].binding_valid
        ):
            reasons.append("ACTIVATION_CATALOG_MISMATCH")
        if (
            activation.source_revision
            and current_source_revision != activation.source_revision
        ):
            reasons.append("ACTIVATION_SOURCE_REVISION_MISMATCH")
        if (
            activation.source_fingerprint
            and current_source_fingerprint != activation.source_fingerprint
        ):
            reasons.append("ACTIVATION_SOURCE_FINGERPRINT_MISMATCH")
    else:
        if current_source_revision != activation.source_revision:
            reasons.append("ACTIVATION_SOURCE_REVISION_MISMATCH")
        if current_source_fingerprint != activation.source_fingerprint:
            reasons.append("ACTIVATION_SOURCE_FINGERPRINT_MISMATCH")
        if live_rag is None:
            reasons.append("ACTIVATION_RAG_STATUS_UNAVAILABLE")
        else:
            if not live_rag.ready:
                reasons.append("ACTIVATION_RAG_NOT_READY")
            if not live_rag.model_configured:
                reasons.append("ACTIVATION_RAG_MODEL_NOT_CONFIGURED")
        if activation.rag_identity and (
            not activation.rag_identity.ready
            or not activation.rag_identity.model_configured
        ):
            reasons.append("ACTIVATION_RAG_STARTUP_NOT_READY")
    return ActivationValidationResult(
        status="BLOCKED" if reasons else "PASS",
        reason_codes=tuple(reasons or ["ACTIVATION_CURRENT"]),
    )


def classify_runtime_path(path: str | Path) -> tuple[RuntimeLifecycle, str, str]:
    normalized = str(Path(path)).replace("\\", "/").casefold()
    if any(
        marker in normalized
        for marker in (
            "/shadow/",
            "/blackbox",
            "migration-preflight",
            "/preflight",
            "/clone",
            "/source-baseline/",
        )
    ):
        return RuntimeLifecycle.DO_NOT_USE, "TRANSIENT_14D", "NON_RUNTIME_TEST_OR_PREFLIGHT"
    if any(
        marker in normalized
        for marker in (
            "/backups/",
            "/backup-",
            "/gate0-backup/",
            "/cleanup-backup-",
            "/pilot-backups/",
            "pre-migration",
        )
    ):
        return RuntimeLifecycle.ARCHIVE, "FORMAL_90D", "RECOVERABLE_ARCHIVE"
    return RuntimeLifecycle.UNCLASSIFIED, "MANUAL", "REQUIRES_EXPLICIT_CLASSIFICATION"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def load_gate_facts(path: str | Path) -> GateFactsV1:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    derived = payload.get("derived") or {}
    return GateFactsV1.model_validate(
        {
            "gates": payload["gates"],
            "ai_cs_production_ready": derived.get("ai_cs_production_ready"),
            "may_enter_read_only_pilot": derived.get("may_enter_read_only_pilot"),
            "real_send_enabled": derived.get("real_send_enabled"),
        }
    )


def _same_path(left: str, right: str) -> bool:
    return str(Path(left).resolve(strict=False)).casefold() == str(
        Path(right).resolve(strict=False)
    ).casefold()


__all__ = [
    "ActivationValidationResult",
    "GATE_DEPENDENCIES",
    "GateFactsV1",
    "GateStatus",
    "LiveProcessSnapshot",
    "PilotGovernanceError",
    "RagLiveSnapshot",
    "RagRuntimeIdentityV1",
    "RuntimeActivationV1",
    "RuntimeCatalogEntryV1",
    "RuntimeCatalogV1",
    "RuntimeLifecycle",
    "canonical_json_sha256",
    "classify_runtime_path",
    "load_gate_facts",
    "sha256_file",
    "validate_activation",
]
